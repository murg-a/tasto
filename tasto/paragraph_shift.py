"""Horizontal paragraph alternatives, anchored by native GtkTextMarks.

Only the active alternative lives in the Markdown buffer. Inactive alternatives
and recovery data live in a document-local JSON sidecar in the XDG config dir.
"""
import copy
import hashlib
import json
import os
import uuid
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from .paragraphs import blocks
from .footnotes import notes as footnotes, references, definition


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class ParagraphShift:
    def init_shift(self):
        self.shift_groups = []
        self._shift_open = None
        self._shift_busy = False
        self._shift_destroyed = False
        self._shift_idle = 0
        self._shift_base = digest('')
        self._shift_saved = []
        self._shift_history = []
        self._shift_redo = []
        self._shift_failed = False
        self._shift_corrupt = False
        self._shift_warning = ''
        self._shift_sides = None
        self._shift_layout_key = None

    def shift_path(self, path=None):
        from .app import CONFIG_DIR
        key = os.path.realpath(path or self.path) if path or self.path else 'untitled'
        return os.path.join(CONFIG_DIR, 'variants', digest(key) + '.json')

    def shift_snapshot(self):
        result = []
        text = self.get_text()
        all_notes = footnotes(text)
        ordered = sorted(self.shift_groups, key=lambda g: self.buf.get_iter_at_mark(g['start']).get_offset())
        for index, group in enumerate(ordered):
            if index+1 < len(ordered):
                boundary = self.buf.get_iter_at_mark(ordered[index+1]['start'])
                if self.buf.get_iter_at_mark(group['end']).compare(boundary) > 0:
                    self.buf.move_mark(group['end'], boundary)
            a = self.buf.get_iter_at_mark(group['start']).get_offset()
            b = self.buf.get_iter_at_mark(group['end']).get_offset()
            versions = list(group['versions'])
            versions[group['active']] = text[a:b]
            version_notes = copy.deepcopy(group.get('notes', [{} for _ in versions]))
            linked = {r.number for r in references(versions[group['active']])}
            version_notes[group['active']] = {n.number: n.content for n in all_notes if n.number in linked}
            result.append({'id': group['id'], 'start': a, 'end': b,
                           'active': group['active'], 'versions': versions, 'notes': version_notes,
                           'padding': group.get('padding', False)})
        return result

    def shift_install(self, records):
        for group in self.shift_groups:
            self.buf.delete_mark(group['start'])
            self.buf.delete_mark(group['end'])
        self.shift_groups = []
        limit = self.buf.get_char_count()
        for record in records:
            group = copy.deepcopy(record)
            group['start'] = self.buf.create_mark(None, self.buf.get_iter_at_offset(min(limit, record['start'])), True)
            group['end'] = self.buf.create_mark(None, self.buf.get_iter_at_offset(min(limit, record['end'])), False)
            self.shift_groups.append(group)
        self._shift_open = None

    def persist_shift(self, path=None, document=None, records=None):
        from .app import save_json
        if self._shift_corrupt:
            return False
        text = self.get_text() if document is None else document
        records = self.shift_snapshot() if records is None else records
        base = self._shift_base
        if path is not None:
            try:
                with open(path, encoding='utf-8') as stream:
                    base = digest(stream.read())
            except FileNotFoundError:
                base = digest('')
            except (OSError, UnicodeError) as exc:
                self.error(f'Impossibile preparare il salvataggio delle varianti:\n{exc}')
                return False
        payload = {'version': 1, 'base': base, 'document': text,
                   'groups': records, 'saved': self._shift_saved}
        if save_json(self.shift_path(path), payload):
            self._shift_failed = False
            return True
        if not self._shift_failed:
            self.error('Impossibile salvare le varianti. Il testo resta aperto; riprova il salvataggio prima di chiudere.')
        self._shift_failed = True
        return False

    @staticmethod
    def validate_shift(records, text):
        if not isinstance(records, list):
            raise ValueError('Elenco varianti non valido')
        seen = set()
        ranges = []
        for record in records:
            if not (isinstance(record, dict) and isinstance(record.get('id'), str)
                    and record['id'] not in seen and isinstance(record.get('versions'), list)
                    and record['versions'] and all(isinstance(t, str) for t in record['versions'])
                    and type(record.get('active')) is int and 0 <= record['active'] < len(record['versions'])
                    and type(record.get('start')) is int and type(record.get('end')) is int
                    and 0 <= record['start'] <= record['end'] <= len(text)):
                raise ValueError('Paragrafo o variante non valido')
            notes = record.get('notes', [{} for _ in record['versions']])
            if not (isinstance(notes, list) and len(notes) == len(record['versions'])
                    and all(isinstance(item, dict) and all(isinstance(k,str) and k.isdigit() and isinstance(v,str)
                            for k,v in item.items()) for item in notes)):
                raise ValueError('Note delle varianti non valide')
            if text[record['start']:record['end']] != record['versions'][record['active']]:
                raise ValueError('Il testo della variante non corrisponde al documento')
            seen.add(record['id'])
            ranges.append((record['start'], record['end']))
        ranges.sort()
        if any(b > c for (_, b), (c, _) in zip(ranges, ranges[1:])):
            raise ValueError('Paragrafi sovrapposti')

    def load_shift(self, recover=True):
        self.close_shift()
        self.shift_install([])
        self._shift_history = []
        self._shift_redo = []
        self._shift_saved = []
        self._shift_corrupt = self._shift_failed = False
        self._shift_warning = ''
        self._shift_base = digest(self.get_text())
        if not recover:
            self.persist_shift()
            return
        try:
            with open(self.shift_path(), encoding='utf-8') as stream:
                data = json.load(stream)
            if data.get('version') != 1 or not isinstance(data.get('document'), str):
                raise ValueError('Formato delle varianti non riconosciuto')
            text = data['document']
            records = data['groups']
            self.validate_shift(records, text)
            if not records and not data.get('saved'):
                return
            self._shift_saved = data.get('saved', [])
            if text != self.get_text():
                if data.get('base') == self._shift_base:
                    self._shift_busy = self._mutating_notes = True
                    self.buf.begin_not_undoable_action()
                    self.buf.set_text(text)
                    self.buf.end_not_undoable_action()
                    self._shift_busy = self._mutating_notes = False
                    self.buf.set_modified(True)
                else:
                    # Keep the original sidecar intact; never guess an ambiguous anchor.
                    self._shift_warning = 'File modificato esternamente: varianti conservate nel file di recupero.'
                    self._shift_corrupt = True
                    self.error(self._shift_warning + '\nRiapri la versione originale del documento per recuperarle.')
                    return
            self.shift_install(records)
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self._shift_corrupt = True
            self.error(f'Impossibile caricare le varianti. Il file di recupero resta intatto.\n{exc}')
        self.queue_shift()

    def shift_saved(self):
        self._shift_base = digest(self.get_text())
        self._shift_saved = self.shift_snapshot()
        return self.persist_shift()

    def discard_shift(self):
        if self._shift_corrupt:
            return True
        try:
            with open(self.path, encoding='utf-8') as stream:
                text = stream.read()
        except (OSError, TypeError, UnicodeError):
            text = ''
        self._shift_base = digest(text)
        if not self.persist_shift(document=text, records=self._shift_saved):
            return False
        if self.path is None:
            self.remove_draft()
        return True

    def setup_shift_editor(self):
        self.editor_overlay = Gtk.Overlay()
        self.editor_overlay.add(self.editor_sw)
        self._shift_positions = {}
        self.editor_overlay.connect('get-child-position', self.position_shift_child)
        self.shift_margin = self.buf.create_tag('shift-margin')
        self.shift_header = self.buf.create_tag('shift-header', pixels_above_lines=36)
        self.shift_padding = self.buf.create_tag('shift-padding')
        self.shift_tools = Gtk.Box(spacing=4)
        self.shift_tools.set_name('shift-tools')
        self.shift_grip = Gtk.Label(label='⠿')
        self.shift_grip.set_tooltip_text('Paragrafo indipendente')
        self.shift_prev = self.button('‹', 'Variante precedente', lambda: self.select_shift(-1))
        self.shift_next = self.button('›', 'Variante successiva', lambda: self.select_shift(1))
        self.shift_count = Gtk.Label()
        self.shift_add = self.button('+', 'Scrivi una variante di questo paragrafo', self.add_shift)
        for widget in (self.shift_grip, self.shift_prev, self.shift_count, self.shift_next, self.shift_add):
            self.shift_tools.pack_start(widget, False, False, 0)
        self.shift_preview = Gtk.TextView()
        self.shift_preview.set_name('shift-preview')
        self.shift_preview.set_editable(False)
        self.shift_preview.set_cursor_visible(False)
        self.shift_preview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.shift_preview.set_left_margin(12)
        self.shift_preview.set_right_margin(12)
        self.shift_preview.set_top_margin(0)
        self.shift_preview.set_bottom_margin(8)
        self.shift_close = self.button('×', 'Torna alla lettura verticale (Esc)', self.close_shift)
        for widget in (self.shift_preview, self.shift_tools, self.shift_close):
            widget.set_halign(Gtk.Align.START)
            widget.set_valign(Gtk.Align.START)
            widget.set_no_show_all(True)
            self.editor_overlay.add_overlay(widget)
        self.buf.connect('mark-set', lambda _b, _i, mark: self.queue_shift() if mark.get_name() == 'insert' else None)
        self.buf.connect('changed', lambda *_: self.queue_shift())
        self.buf.connect('undo', lambda *_: self.shift_before_undo(False))
        self.buf.connect_after('undo', lambda *_: self.shift_after_undo(False))
        self.buf.connect('redo', lambda *_: self.shift_before_undo(True))
        self.buf.connect_after('redo', lambda *_: self.shift_after_undo(True))
        self.editor_sw.get_vadjustment().connect('value-changed', lambda *_: self.queue_shift())
        self.editor_overlay.connect('size-allocate', lambda *_: self.queue_shift())
        self.connect('destroy', self.destroy_shift)
        self.view.connect('key-press-event', self.shift_key)
        self.view.connect('focus-out-event', lambda *_: self.queue_shift())

    def position_shift_child(self, _overlay, widget, allocation):
        if widget not in self._shift_positions:
            return False
        x, y = self._shift_positions[widget]
        _minimum, width = widget.get_preferred_width()
        _minimum, height = widget.get_preferred_height_for_width(width)
        allocation.x, allocation.y = x, y
        allocation.width, allocation.height = max(1,width), max(1,height)
        return True

    def position_shift_widget(self, widget, x, y):
        position = (max(0,int(x)), max(0,int(y)))
        if self._shift_positions.get(widget) != position:
            self._shift_positions[widget] = position
            self.editor_overlay.queue_resize()

    def destroy_shift(self, *_):
        self._shift_destroyed = True
        if self._shift_idle:
            GLib.source_remove(self._shift_idle)
            self._shift_idle = 0

    def shift_key(self, _widget, event):
        from gi.repository import Gdk
        if event.keyval == Gdk.KEY_Escape and self._shift_open:
            self.close_shift()
            return True
        return False

    def shift_context(self):
        offset = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
        for group in self.shift_groups:
            a = self.buf.get_iter_at_mark(group['start']).get_offset()
            b = self.buf.get_iter_at_mark(group['end']).get_offset()
            if a <= offset <= b:
                return group, a, b
        for block in blocks(self.get_text()):
            end = block.end - (len(block.text) - len(block.text.rstrip('\r\n')))
            if block.start <= offset <= end:
                return None, block.start, end
        return None

    def add_shift(self):
        self.finish_note_action()
        context = self.shift_context()
        if context is None or self._editing_note is not None or self._shift_corrupt:
            return False
        group, a, b = context
        if any(a <= note.start <= b for note in footnotes(self.get_text())):
            self.error('Crea la variante sul paragrafo che richiama la nota, non sulla sua definizione.')
            return False
        before = self.shift_snapshot()
        if group is None:
            record = {'id': uuid.uuid4().hex, 'start': a, 'end': b,
                      'active': 0, 'versions': [self.get_text()[a:b]]}
            records = before + [record]
            self.shift_install(records)
            group = self.shift_groups[-1]
        else:
            group['versions'][group['active']] = self.get_text()[a:b]
        versions = list(group['versions']) + ['']
        return self.shift_transition(group, len(versions)-1, versions, before)

    def select_shift(self, direction):
        self.finish_note_action()
        context = self.shift_context()
        if context is None or context[0] is None or self._editing_note is not None:
            return False
        group, a, b = context
        target = group['active'] + direction
        if not 0 <= target < len(group['versions']):
            return False
        versions = list(group['versions'])
        versions[group['active']] = self.get_text()[a:b]
        return self.shift_transition(group, target, versions, self.shift_snapshot())

    def shift_transition(self, group, active, versions, before):
        if self._shift_corrupt:
            return False
        a = self.buf.get_iter_at_mark(group['start']).get_offset()
        b = self.buf.get_iter_at_mark(group['end']).get_offset()
        old = self.get_text()
        records = self.shift_snapshot()
        record = next(r for r in records if r['id'] == group['id'])
        version_notes = record['notes']
        while len(version_notes) < len(versions):
            version_notes.append({})
        content = versions[active]
        current_notes = {n.number: n.content for n in footnotes(old)}
        used = {int(r.number) for r in references(old)} | {int(n) for n in current_notes}
        next_id = max(used, default=0)+1
        mapping, additions = {}, []
        for number, note in version_notes[active].items():
            if current_notes.get(number) != note:
                mapping[number] = str(next_id)
                additions.append(definition(str(next_id), note))
                next_id += 1
        for ref in reversed(references(content)):
            if ref.number in mapping:
                content = content[:ref.start] + '[^' + mapping[ref.number] + ']' + content[ref.end:]
        versions[active] = content
        version_notes[active] = {mapping.get(n,n): value for n,value in version_notes[active].items()}
        # An empty last paragraph needs a real blank line for its insertion point.
        tail = old[b:]
        removed_padding = bool(group.get('padding') and tail == '\n')
        if removed_padding:
            tail = ''
        suffix = '\n' if not content and not tail else ''
        text = old[:a] + content + suffix + tail
        if additions:
            text = text.rstrip('\n') + '\n\n' + ''.join(additions)
        delta = len(content) + len(suffix) - (b-a) - int(removed_padding)
        for record in records:
            if record['id'] == group['id']:
                record.update(start=a, end=a+len(content), active=active, versions=versions, notes=version_notes, padding=bool(suffix))
            elif record['start'] >= b:
                record['start'] += delta
                record['end'] += delta
        if not self.persist_shift(document=text, records=records):
            self.shift_install(before)
            return False
        self._shift_busy = True
        self.replace_document(text, a)
        self.shift_install(records)
        self._shift_busy = False
        if old != text:
            self._shift_history.append((old, text, before, copy.deepcopy(records)))
        self.buf.set_modified(True)
        self._shift_redo.clear()
        selected = next(g for g in self.shift_groups if g['id'] == group['id'])
        self._shift_open = selected['id'] if active > 0 else None
        if active > 0:
            self.expand_shift()
        else:
            self.close_shift()
        self.view.grab_focus()
        self.queue_shift()
        GLib.idle_add(self.center_shift)
        return True

    def expand_shift(self):
        if self._shift_sides is None:
            self._shift_sides = (self.left_pane.get_visible(), self.right_pane.get_visible())
        self.left_pane.hide()
        self.right_pane.hide()
        self.view.set_top_margin(max(48, self.view.get_allocated_height()//2))
        self.view.set_bottom_margin(max(120, self.view.get_allocated_height()//2))
        self.schedule_fit()

    def center_shift(self):
        if self._shift_destroyed:
            return False
        context = self.shift_context()
        if context:
            self.view.scroll_to_iter(self.buf.get_iter_at_offset(context[1]), .1, True, .5, .5)
        self.queue_shift()
        return False

    def close_shift(self):
        if hasattr(self, "view"):
            self.view.set_top_margin(48)
            self.view.set_bottom_margin(120)
        self._shift_layout_key = None
        self._shift_open = None
        if hasattr(self, 'shift_preview'):
            self.shift_preview.hide()
            self.shift_close.hide()
            start, end = self.buf.get_bounds()
            for tag in (self.shift_margin, self.shift_header, self.shift_padding):
                self.buf.remove_tag(tag, start, end)
        if self._shift_sides is not None:
            left, right = self._shift_sides
            self.left_pane.set_visible(left)
            self.right_pane.set_visible(right)
            self._shift_sides = None
            self.schedule_fit()
        self.queue_shift()

    def queue_shift(self):
        if not self._shift_idle and not self._shift_busy and not self._shift_destroyed:
            self._shift_idle = GLib.idle_add(self.layout_shift)

    def layout_shift(self):
        self._shift_idle = 0
        if self._shift_destroyed or not hasattr(self, 'shift_tools') or self._shift_busy:
            return False
        context = self.shift_context()
        if context is None or self._editing_note is not None:
            self.shift_tools.hide()
            if self._shift_open:
                self.close_shift()
            return False
        group, a, b = context
        key = (self.get_text(), a, b, group['id'] if group else None,
               group['active'] if group else 0, self._shift_open, self.view.get_allocated_width(),
               self.editor_sw.get_vadjustment().get_value(), self.cfg['size'], self.cfg['font'], self.cfg['width'], self.view.get_allocated_height(), self.view.get_left_margin(), self.view.get_right_margin())
        if key == self._shift_layout_key:
            return False
        self._shift_layout_key = key
        if self._shift_open and (group is None or group['id'] != self._shift_open):
            self.close_shift()
        start, end = self.buf.get_bounds()
        for tag in (self.shift_margin, self.shift_header, self.shift_padding):
            self.buf.remove_tag(tag, start, end)
        width = self.view.get_allocated_width()
        if width < 100:
            return False
        split = bool(group and group['id'] == self._shift_open)
        self.shift_preview.set_visible(split)
        self.shift_close.set_visible(split)
        it = self.buf.get_iter_at_offset(a)
        tag_end = self.buf.get_iter_at_offset(min(self.buf.get_char_count(), max(b, a+1)))
        if split:
            half = width // 2
            gap = 28
            column = max(100, min(self.cfg['width'], half-gap-24))
            left = max(16, half-gap-column)
            right_start = half+gap
            self.shift_margin.set_property('left-margin', right_start)
            self.shift_margin.set_property('right-margin', max(20, width-right_start-column))
            self.buf.apply_tag(self.shift_margin, it, tag_end)
            self.buf.apply_tag(self.shift_header, it, self.buf.get_iter_at_offset(min(a+1,self.buf.get_char_count())))
            previous = group['versions'][group['active']-1]
            if self.shift_preview.get_buffer().get_text(*self.shift_preview.get_buffer().get_bounds(), True) != previous:
                self.shift_preview.get_buffer().set_text(previous)
            self.shift_preview.set_size_request(column, -1)
        rect = self.view.get_iter_location(it)
        x, y = self.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, rect.x, rect.y)
        if y < 0 or y > self.view.get_allocated_height()-20:
            self.shift_tools.hide()
            self.shift_preview.hide()
            self.shift_close.hide()
            return False
        active = group['active'] if group else 0
        count = len(group['versions']) if group else 1
        self.shift_prev.set_sensitive(active > 0)
        self.shift_next.set_sensitive(active+1 < count)
        self.shift_count.set_text(f'{active+1} / {count}' if group else '')
        for child in self.shift_tools.get_children():
            child.show_all()
        self.shift_tools.show()
        for widget in (self.shift_prev, self.shift_next, self.shift_count):
            widget.set_visible(group is not None)
        # Controls belong only to the paragraph containing the insertion cursor.
        self.position_shift_widget(self.shift_tools, max(4, min(width-(210 if group else 65), x if split else width-self.view.get_right_margin()+8)), y-34 if split else y)
        if split:
            self.position_shift_widget(self.shift_preview, left, y)
            self.position_shift_widget(self.shift_close, width-36, y-34)
            # Reserve enough document height for the longer of the two alternatives.
            layout = self.shift_preview.create_pango_layout(previous)
            from gi.repository import Pango
            layout.set_width(max(80,column-24)*Pango.SCALE)
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
            preview_height = layout.get_pixel_size()[1]+16
            self.shift_preview.set_size_request(column, preview_height)
            last = self.view.get_iter_location(self.buf.get_iter_at_offset(b))
            active_height = last.y-rect.y+last.height
            padding = max(0,preview_height-active_height)
            self.shift_padding.set_property('pixels-below-lines', padding+8)
            line_start = self.buf.get_iter_at_offset(b)
            line_start.set_line_offset(0)
            self.buf.apply_tag(self.shift_padding,line_start,tag_end)
        return False

    def shift_before_undo(self, redo):
        self._shift_before_undo = self.get_text()

    def shift_after_undo(self, redo):
        source = self._shift_redo if redo else self._shift_history
        dest = self._shift_history if redo else self._shift_redo
        if source:
            old, new, before, after = source[-1]
            expected, result = (old,new) if redo else (new,old)
            if self._shift_before_undo == expected and self.get_text() == result:
                self.close_shift()
                self.shift_install(after if redo else before)
                dest.append(source.pop())
        self.queue_shift()
