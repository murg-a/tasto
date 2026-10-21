"""Paragraph parking UI; the Markdown buffer remains the source of document text."""
import copy
import hashlib
import json
import os
import uuid
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango
from .paragraphs import blocks, insert_block
from .footnotes import notes as footnotes, references, definition, reconcile_notes, synchronize_notes

MIME = 'application/x-tasto-paragraph'
TARGET = Gtk.TargetEntry.new(MIME, Gtk.TargetFlags.SAME_APP, 82)


class ParagraphDock:
    def init_dock(self):
        self.parked = []
        self._dock_saved_cards = []
        self._dock_history = []
        self._dock_redo = []
        self._dock_drag = None
        self._dock_hover = None
        self._dock_failed = False
        self._dock_warning = ''
        self._dock_base = hashlib.sha256(b'').hexdigest()
        self._dock_corrupt = False

    def dock_path(self, path=None):
        from .app import CONFIG_DIR
        key = os.path.realpath(path or self.path) if (path or self.path) else 'untitled'
        return os.path.join(CONFIG_DIR, 'paragraphs', hashlib.sha256(key.encode()).hexdigest() + '.json')

    def persist_dock(self, cards, path=None, document=None):
        from .app import save_json
        if self._dock_corrupt:
            return False
        document = self.get_text() if document is None else document
        base = self._dock_base
        if path is not None:
            try:
                with open(path, encoding='utf-8') as stream:
                    base = hashlib.sha256(stream.read().encode()).hexdigest()
            except (OSError, UnicodeDecodeError):
                base = hashlib.sha256(b'').hexdigest()
        payload = {'version': 1, 'cards': cards, 'document': document,
                   'base': base, 'pending': hashlib.sha256(document.encode()).hexdigest() != base,
                   'saved_cards': self._dock_saved_cards}
        if save_json(self.dock_path(path), payload):
            self._dock_failed = False
            return True
        self._dock_failed = True
        self.error('Impossibile salvare i paragrafi parcheggiati. Il testo viene conservato; riprova il salvataggio.')
        return False

    def dock_saved(self):
        self._dock_base = hashlib.sha256(self.get_text().encode()).hexdigest()
        self._dock_saved_cards = copy.deepcopy(self.parked)
        return self.persist_dock(self.parked)

    def discard_dock_changes(self):
        if self._dock_corrupt:
            return True
        try:
            with open(self.path, encoding='utf-8') as stream:
                text = stream.read()
        except (OSError, TypeError, UnicodeDecodeError):
            text = ''
        self._dock_base = hashlib.sha256(text.encode()).hexdigest()
        if not self.persist_dock(self._dock_saved_cards, document=text):
            return False
        self.parked = copy.deepcopy(self._dock_saved_cards)
        if self.path is None:
            self.remove_draft()
        return True

    def load_dock(self):
        self._dock_base = hashlib.sha256(self.get_text().encode()).hexdigest()
        self.grip.hide()
        self._dock_warning = ''
        self.parked = []
        self._dock_saved_cards = []
        self._dock_failed = False
        self._dock_corrupt = False
        try:
            with open(self.dock_path(), encoding='utf-8') as stream:
                data = json.load(stream)
            if data.get('version') != 1 or not isinstance(data.get('cards'), list):
                raise ValueError('Formato non riconosciuto')
            for card in data['cards']:
                if not (isinstance(card, dict) and isinstance(card.get('id'), str)
                        and isinstance(card.get('text'), str) and isinstance(card.get('origin'), int)
                        and isinstance(card.get('notes', {}), dict)
                        and all(isinstance(k, str) and k.isdigit() and isinstance(v, str)
                                for k, v in card.get('notes', {}).items())):
                    raise ValueError('Card non valida')
            self.parked = data['cards']
            self._dock_saved_cards = copy.deepcopy(data.get('saved_cards', self.parked))
            saved_text = data.get('document')
            if data.get('pending') and isinstance(saved_text, str) and saved_text != self.get_text():
                current = hashlib.sha256(self.get_text().encode()).hexdigest()
                if current == data.get('base'):
                    self._mutating_notes = True
                    self.buf.begin_not_undoable_action()
                    self.buf.set_text(saved_text)
                    self.buf.end_not_undoable_action()
                    self._mutating_notes = False
                    self.buf.set_modified(True)
                else:
                    self._dock_warning = 'File modificato esternamente: testo del file conservato. Le card restano disponibili.'
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self._dock_failed = True
            self._dock_corrupt = True
            self.error(f'Impossibile leggere i paragrafi parcheggiati:\n{exc}')
        self._dock_history = []
        self._dock_redo = []
        self._dock_drag = None
        self.rebuild_dock()

    def build_dock_page(self):
        self.dock_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.dock_list.set_border_width(12)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.dock_list)
        self.right_stack.add_titled(scroll, 'paragraphs', 'Paragrafi')
        # The entire right pane accepts a block, including Appunti/Note tabs.
        self.right_pane.drag_dest_set(Gtk.DestDefaults.ALL, [TARGET], Gdk.DragAction.MOVE)
        self.right_pane.connect('drag-data-received', self.dock_received)
        self.rebuild_dock()

    def setup_dock_editor(self):
        self.editor_overlay = Gtk.Overlay()
        self.editor_overlay.add(self.editor_sw)
        self.grip = Gtk.Button(label='⠿')
        self.grip.set_name('paragraph-grip')
        self.grip.set_tooltip_text('Trascina questo paragrafo nel pannello destro')
        self.grip.set_halign(Gtk.Align.START)
        self.grip.set_valign(Gtk.Align.START)
        self.grip.set_no_show_all(True)
        self.editor_overlay.add_overlay(self.grip)
        self.grip.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [TARGET], Gdk.DragAction.MOVE)
        self.grip.connect('drag-begin', self.grip_begin)
        self.grip.connect('drag-data-get', self.dock_drag_data)
        self.grip.connect('drag-end', self.dock_drag_end)
        self.view.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.view.connect('motion-notify-event', self.dock_motion)
        self.view.connect('leave-notify-event', self.dock_leave)
        self.editor_sw.get_vadjustment().connect('value-changed', lambda *_: self.grip.hide())
        self.view.drag_dest_add_text_targets()
        self.view.drag_dest_add_uri_targets()
        targets = self.view.drag_dest_get_target_list()
        targets.add(Gdk.Atom.intern(MIME, False), Gtk.TargetFlags.SAME_APP, 82)
        self.view.connect('drag-data-received', self.editor_dock_received)
        self.view.connect('drag-motion', self.dock_drop_motion)
        self.buf.connect('undo', lambda *_: self.dock_before_history(False))
        self.buf.connect_after('undo', lambda *_: self.dock_after_history(False))
        self.buf.connect('redo', lambda *_: self.dock_before_history(True))
        self.buf.connect_after('redo', lambda *_: self.dock_after_history(True))

    def dock_motion(self, _view, event):
        if self._editing_note is not None or self._dock_drag:
            return False
        window = self.view.get_window_type(event.window)
        x, y = self.view.window_to_buffer_coords(window, int(event.x), int(event.y))
        _inside, it = self.view.get_iter_at_location(x, y)
        block = next((b for b in blocks(self.get_text()) if b.start <= it.get_offset() < b.end), None)
        if block is None:
            self.grip.hide()
            return False
        self._dock_hover = block
        rect = self.view.get_iter_location(self.buf.get_iter_at_offset(block.start))
        wx, wy = self.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, rect.x, rect.y)
        self.grip.set_margin_start(max(0, wx - 36))
        self.grip.set_margin_top(max(0, wy))
        self.grip.show()
        return False

    def dock_leave(self, _view, event):
        # Keep the handle available when the pointer crosses from text to handle.
        if event.x < 0 or event.y < 0 or event.y >= self.view.get_allocated_height():
            self.grip.hide()
        return False

    def grip_begin(self, _button, _context):
        self.finish_note_action()
        block = self._dock_hover
        if block and self.get_text()[block.start:block.end] == block.text:
            self._dock_drag = ('editor', block, self.get_text())
            if not self.cfg['notes']:
                self.toggle_notes()
            self.right_stack.set_visible_child_name('paragraphs')

    def card_begin(self, _widget, _context, identity):
        self._dock_drag = ('card', identity, self.get_text())

    def dock_drag_data(self, _widget, _context, selection, _info, _time):
        selection.set(selection.get_target(), 8, b'tasto')

    def dock_drag_end(self, *_):
        self._dock_drag = None
        self.grip.hide()

    def dock_received(self, _widget, context, _x, _y, _selection, info, timestamp):
        if info != 82:
            return
        success = False
        if self._dock_drag and self._dock_drag[0] == 'editor':
            _, block, original = self._dock_drag
            if original == self.get_text():
                success = self.park_block(block)
        Gtk.drag_finish(context, success, False, timestamp)
        self._dock_drag = None

    def drop_offset(self, x, y):
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        return self.view.get_iter_at_location(bx, by)[1].get_offset()

    def dock_drop_motion(self, _widget, context, x, y, timestamp):
        if not self._dock_drag or self._dock_drag[0] != 'card':
            return False
        self.view.drag_highlight()
        self.buf.place_cursor(self.buf.get_iter_at_offset(self.drop_offset(x, y)))
        Gdk.drag_status(context, Gdk.DragAction.MOVE, timestamp)
        return True

    def editor_dock_received(self, _widget, context, x, y, _selection, info, timestamp):
        if info != 82:
            return
        success = False
        if self._dock_drag and self._dock_drag[0] == 'card':
            success = self.restore_block(self._dock_drag[1], self.drop_offset(x, y))
        self.view.drag_unhighlight()
        Gtk.drag_finish(context, success, False, timestamp)
        self._dock_drag = None
        self.view.stop_emission_by_name('drag-data-received')

    def park_block(self, block):
        if self._editing_note is not None or self._dock_failed:
            return False
        text = self.get_text()
        if text[block.start:block.end] != block.text:
            return False
        definitions = footnotes(text)
        if any(block.start <= n.start < block.end for n in definitions):
            self.error('Questo blocco contiene definizioni di note. Sposta il paragrafo con i richiami; le relative note lo seguiranno automaticamente.')
            return False
        linked = {ref.number for ref in references(block.text)}
        note_contents = {n.number: n.content for n in definitions if n.number in linked}
        card = {'id': uuid.uuid4().hex, 'text': block.text, 'origin': block.start,
                'before': text[max(0, block.start-80):block.start], 'after': text[block.end:block.end+80], 'notes': note_contents}
        remaining = text[:block.start] + text[block.end:]
        remaining, cursor, _ = reconcile_notes(text, remaining, block.start, linked, set())
        return self.dock_transaction(remaining, self.parked + [card], cursor)

    def restore_block(self, identity, offset):
        if self._editing_note is not None or self._dock_failed:
            return False
        card = next((c for c in self.parked if c['id'] == identity), None)
        if card is None:
            return False
        current = self.get_text()
        content = card['text']
        definitions = {n.number: n.content for n in footnotes(current)}
        used = {int(ref.number) for ref in references(current)} | {int(n) for n in definitions}
        next_id = max(used, default=0) + 1
        mapping = {}
        additions = []
        for number, note in card.get('notes', {}).items():
            if definitions.get(number) == note:
                continue
            mapping[number] = str(next_id)
            additions.append(definition(str(next_id), note))
            next_id += 1
        for ref in reversed(references(content)):
            if ref.number in mapping:
                content = content[:ref.start] + '[^' + mapping[ref.number] + ']' + content[ref.end:]
        text, cursor = insert_block(current, offset, content)
        if additions:
            text = text.rstrip('\n') + '\n\n' + ''.join(additions)
        text, cursor, _ = synchronize_notes(text, cursor)
        return self.dock_transaction(text, [c for c in self.parked if c['id'] != identity], cursor)

    def dock_transaction(self, text, cards, cursor):
        self.finish_note_action()
        before = self.get_text()
        if not self.persist_dock(cards, document=text):
            return False
        record = (before, text, copy.deepcopy(self.parked), copy.deepcopy(cards))
        self.replace_document(text, cursor)
        self.parked = cards
        self._dock_history.append(record)
        self._dock_redo.clear()
        self.rebuild_dock()
        self.right_stack.set_visible_child_name('paragraphs')
        return True

    def dock_before_history(self, redo):
        self._dock_before_history = self.get_text()

    def dock_after_history(self, redo):
        source = self._dock_redo if redo else self._dock_history
        dest = self._dock_history if redo else self._dock_redo
        if not source:
            return
        before, after, old_cards, new_cards = source[-1]
        expected, result = (before, after) if redo else (after, before)
        if self._dock_before_history == expected and self.get_text() == result:
            self.parked = copy.deepcopy(new_cards if redo else old_cards)
            dest.append(source.pop())
            self.persist_dock(self.parked)
            self.rebuild_dock()

    def rebuild_dock(self):
        for child in self.dock_list.get_children():
            self.dock_list.remove(child)
        hint = Gtk.Label(label=self._dock_warning or 'Trascina qui un paragrafo dalla maniglia ⠿.\nTrascina una card nel testo per reinserirla.')
        hint.set_line_wrap(True)
        hint.set_max_width_chars(24)
        self.dock_list.pack_start(hint, False, False, 0)
        for card in self.parked:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_name('paragraph-card')
            box.set_border_width(10)
            label = Gtk.Label(label=card['text'], xalign=0)
            label.set_line_wrap(True)
            label.set_max_width_chars(24)
            label.set_lines(8)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            box.pack_start(label, True, True, 0)
            identity = card['id']
            button = self.button('↳ Inserisci al cursore', 'Sposta il paragrafo nel documento',
                                 lambda identity=identity: self.restore_block(identity, self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()))
            box.pack_start(button, False, False, 0)
            # Gtk.Box has no GdkWindow: an EventBox receives pointer events for dragging.
            event = Gtk.EventBox()
            event.add(box)
            event.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [TARGET], Gdk.DragAction.MOVE)
            event.connect('drag-begin', self.card_begin, identity)
            event.connect('drag-data-get', self.dock_drag_data)
            event.connect('drag-end', self.dock_drag_end)
            self.dock_list.pack_start(event, False, False, 0)
        self.dock_list.show_all()
