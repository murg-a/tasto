"""Interfaccia GTK 4. Avviare con /usr/bin/python3 -m tasto."""
from pathlib import Path
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio
from .document import Document

THEMES = {
    'Carta': ('#ffffff', '#202020'), 'Seppia': ('#f4ecd8', '#49392b'),
    'Notte': ('#252629', '#eeeeee'), 'Ghiaccio': ('#edf3f8', '#273b50'),
    'Sole': ('#fff0cc', '#634423'), 'Dracula': ('#282a36', '#f8f8f2'),
    'Terminale': ('#121b14', '#8cdb91'),
}


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Tasto', default_width=1050, default_height=720)
        self.doc = Document()
        self.font_size = 19
        self.width = 720
        self.family = 'serif'
        self.theme = 'Carta'
        self.connect('close-request', self.close_requested)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        body = Gtk.Box()
        root.append(body)
        body.set_vexpand(True)
        self.left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.left.set_size_request(210, -1)
        self.left.set_visible(False)
        body.append(self.left)
        self.left.append(Gtk.Label(label='INDICE · CERCA', margin_top=20))
        self.search = Gtk.SearchEntry(placeholder_text='Cerca nel testo')
        self.search.connect('search-changed', self.find_text)
        self.left.append(self.search)
        self.outline = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.outline)
        self.left.append(scroll)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        body.append(center)
        self.welcome = Gtk.Label(label='T A S T O\n\nCtrl+N  Nuovo     Ctrl+O  Apri     Ctrl+S  Salva\n\nInizia a scrivere…', margin_top=24, margin_bottom=24)
        center.append(self.welcome)
        self.editor = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=24, bottom_margin=36)
        self.editor.add_css_class('manuscript')
        self.buffer = self.editor.get_buffer()
        self.buffer.connect('changed', self.changed)
        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroller.set_child(self.editor)
        center.append(scroller)
        center.connect('notify::width', self.resize_column)
        self.right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, width_request=220, visible=False)
        body.append(self.right)
        self.right.append(Gtk.Label(label='APPUNTI', margin_top=20))
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
        note_scroll = Gtk.ScrolledWindow(vexpand=True)
        note_scroll.set_child(self.notes)
        self.right.append(note_scroll)
        self.right.append(self.button('Copia selezione negli appunti', self.copy_note))
        self.right.append(Gtk.Label(label='Appunti temporanei: non salvati nel file.', wrap=True))
        bar = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=10, margin_bottom=10)
        root.append(bar)
        bar.append(self.button('☰', lambda *_: self.left.set_visible(not self.left.get_visible())))
        plus = Gtk.MenuButton(label='+')
        bar.append(plus)
        pop = Gtk.Popover()
        tools = Gtk.Box(spacing=5)
        for label, marker in [('B', '**'), ('I', '*'), ('S̶', '~~')]:
            tools.append(self.button(label, lambda _, m=marker: self.format_selection(m)))
        for label, marker in [('H1', '# '), ('H2', '## '), ('•', '- '), ('1.', '1. ')]:
            tools.append(self.button(label, lambda _, m=marker: self.insert_prefix(m)))
        pop.set_child(tools)
        plus.set_popover(pop)
        self.count = Gtk.Label(hexpand=True)
        bar.append(self.count)
        themes = Gtk.DropDown.new_from_strings(list(THEMES))
        themes.connect('notify::selected', lambda w, _: self.choose_theme(list(THEMES)[w.get_selected()]))
        bar.append(themes)
        settings = Gtk.MenuButton(label='⚙')
        settings_pop = Gtk.Popover()
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10)
        for label, callback in [('Font +', lambda *_: self.font_change(1)), ('Font −', lambda *_: self.font_change(-1)), ('Colonna +', lambda *_: self.column_change(80)), ('Colonna −', lambda *_: self.column_change(-80))]:
            controls.append(self.button(label, callback))
        fonts = Gtk.DropDown.new_from_strings(['Serif', 'Sans', 'Monospace'])
        fonts.connect('notify::selected', lambda w, _: self.choose_font(['serif', 'sans-serif', 'monospace'][w.get_selected()]))
        controls.append(fonts)
        settings_pop.set_child(controls)
        settings.set_popover(settings_pop)
        bar.append(settings)
        bar.append(self.button('▤', lambda *_: self.right.set_visible(not self.right.get_visible())))
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply_style()
        for name, callback, keys in [('new', self.new, ['<Control>n']), ('open', self.open_file, ['<Control>o']), ('save', self.save_file, ['<Control>s']), ('save-as', lambda *_: self.save_file(force=True), ['<Control><Shift>s']), ('quit', lambda *_: self.close(), ['<Control>q'])]:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.add_action(action)
            app.set_accels_for_action('win.' + name, keys)
        self.changed()

    @staticmethod
    def button(label, callback):
        button = Gtk.Button(label=label)
        button.connect('clicked', callback)
        return button

    def changed(self, *_):
        self.doc.text = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)
        chars, words = self.doc.counts
        self.count.set_text(f'{chars} caratteri · {words} parole')
        self.welcome.set_visible(not self.doc.text)
        self.set_title(('● ' if self.doc.modified else '') + (self.doc.path.name if self.doc.path else 'Senza titolo') + ' — Tasto')
        while child := self.outline.get_first_child():
            self.outline.remove(child)
        for level, title, offset in self.doc.headings:
            self.outline.append(self.button('  ' * (level - 1) + title, lambda _, o=offset: self.jump(o)))

    def jump(self, offset):
        it = self.buffer.get_iter_at_offset(offset)
        self.buffer.place_cursor(it)
        self.editor.scroll_to_iter(it, .15, False, 0, 0)
        self.editor.grab_focus()

    def find_text(self, *_):
        term = self.search.get_text()
        if term and (offset := self.doc.text.casefold().find(term.casefold())) >= 0:
            # Use original text indices: case folding can change string length.
            import re
            match = re.search(re.escape(term), self.doc.text, re.IGNORECASE)
            if match:
                self.jump(match.start())
                self.buffer.select_range(self.buffer.get_iter_at_offset(match.start()), self.buffer.get_iter_at_offset(match.end()))

    def format_selection(self, marker):
        bounds = self.buffer.get_selection_bounds()
        if not bounds:
            return
        a, b = bounds
        text = self.buffer.get_text(a, b, True)
        self.buffer.begin_user_action()
        self.buffer.delete(a, b)
        self.buffer.insert(a, marker + text + marker)
        self.buffer.end_user_action()

    def insert_prefix(self, prefix):
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        it.set_line_offset(0)
        self.buffer.insert(it, prefix)

    def copy_note(self, *_):
        if bounds := self.buffer.get_selection_bounds():
            buf = self.notes.get_buffer()
            buf.insert(buf.get_end_iter(), self.buffer.get_text(*bounds, True) + '\n')

    def confirm_discard(self, callback):
        if not self.doc.modified:
            callback()
            return
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, text='Ci sono modifiche non salvate.', secondary_text='Salva il documento prima di continuare, oppure scegli Scarta.')
        dialog.add_button('Annulla', Gtk.ResponseType.CANCEL)
        dialog.add_button('Scarta', Gtk.ResponseType.ACCEPT)
        dialog.connect('response', lambda d, r: (d.destroy(), callback() if r == Gtk.ResponseType.ACCEPT else None))
        dialog.present()

    def new(self, *_):
        def reset():
            self.doc = Document()
            self.buffer.set_text('')
        self.confirm_discard(reset)

    def open_file(self, *_):
        self.confirm_discard(lambda: self.file_dialog(False))

    def save_file(self, *_, force=False):
        if not self.doc.path or force:
            self.file_dialog(True)
        else:
            self.write(self.doc.path)

    def file_dialog(self, saving):
        chooser = Gtk.FileChooserNative(title='Salva Markdown' if saving else 'Apri Markdown', transient_for=self, action=Gtk.FileChooserAction.SAVE if saving else Gtk.FileChooserAction.OPEN)
        if saving:
            chooser.set_current_name(self.doc.path.name if self.doc.path else 'Senza titolo.md')
        def response(dialog, result):
            if result == Gtk.ResponseType.ACCEPT:
                path = dialog.get_file().get_path()
                try:
                    if saving:
                        self.doc.save(path)
                    else:
                        self.doc.open(path)
                        self.buffer.set_text(self.doc.text)
                    self.changed()
                except (OSError, UnicodeError) as error:
                    self.error(str(error))
            dialog.destroy()
        chooser.connect('response', response)
        chooser.show()

    def write(self, path):
        try:
            self.doc.save(path)
            self.changed()
        except OSError as error:
            self.error(str(error))

    def error(self, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, text='Operazione non riuscita', secondary_text=message, buttons=Gtk.ButtonsType.CLOSE)
        dialog.connect('response', lambda d, _: d.destroy())
        dialog.present()

    def close_requested(self, *_):
        if self.doc.modified:
            self.confirm_discard(lambda: (setattr(self.doc, 'saved_text', self.doc.text), self.close()))
            return True
        return False

    def choose_theme(self, theme):
        self.theme = theme
        self.apply_style()

    def choose_font(self, family):
        self.family = family
        self.apply_style()

    def font_change(self, delta):
        self.font_size = max(12, min(40, self.font_size + delta))
        self.apply_style()

    def column_change(self, delta):
        self.width = max(320, min(1200, self.width + delta))
        self.resize_column(self.editor.get_parent().get_parent())

    def resize_column(self, widget, *_):
        margin = max(24, (widget.get_width() - self.width) // 2)
        self.editor.set_left_margin(margin)
        self.editor.set_right_margin(margin)

    def apply_style(self):
        bg, fg = THEMES[self.theme]
        self.css.load_from_data(f'window, textview, textview text {{background-color:{bg}; color:{fg};}} .manuscript {{font-family:{self.family}; font-size:{self.font_size}px;}}'.encode())


def main():
    app = Gtk.Application(application_id='io.github.murg_a.Tasto')
    app.connect('activate', lambda application: Window(application).present())
    app.run(None)
