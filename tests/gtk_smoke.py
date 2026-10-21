"""Test GTK completo con eventi X11 nativi, da eseguire su un display isolato.

    xvfb-run -a /usr/bin/python3 tests/gtk_smoke.py

Richiede GTK 3, GtkSourceView 4, Xvfb, xauth e libXtst. Non avviarlo sul display
in uso: il test genera eventi di tastiera. Configurazione e dati sono temporanei.
"""
import ctypes
import sys
errors=[]
def record_error(*error):
    errors.append(error)
    sys.__excepthook__(*error)
sys.excepthook=record_error
import json
import time
from pathlib import Path
import os
import tempfile
# Non leggere o modificare configurazione, appunti e bozze dell'utente.
_test_directory = tempfile.TemporaryDirectory(prefix="tasto-gtk-")
for variable, folder in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
    path = Path(_test_directory.name) / folder
    path.mkdir()
    os.environ[variable] = str(path)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tasto.app import Tasto, NOTES_PATH
from gi.repository import Gtk, Gdk, GLib


def pump(seconds=.3):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.005)

x11=ctypes.CDLL('libX11.so.6')
xtst=ctypes.CDLL('libXtst.so.6')
x11.XOpenDisplay.restype=ctypes.c_void_p
x11.XOpenDisplay.argtypes=[ctypes.c_char_p]
x11.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
x11.XKeysymToKeycode.restype=ctypes.c_uint
x11.XSetInputFocus.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
x11.XFlush.argtypes=[ctypes.c_void_p]
xtst.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
display=x11.XOpenDisplay(None)
assert display

def shortcut(*syms):
    for sym in syms: xtst.XTestFakeKeyEvent(display,x11.XKeysymToKeycode(display,sym),1,0)
    for sym in reversed(syms): xtst.XTestFakeKeyEvent(display,x11.XKeysymToKeycode(display,sym),0,0)
    x11.XFlush(display)
    pump()

win=Tasto();win.cfg['autosave']=False
win.start();win.dismiss_splash();pump()
x11.XSetInputFocus(display,win.get_window().get_xid(),2,0);x11.XFlush(display)
text=''.join(f'Paragrafo {i:03}: una riga per verificare lo scorrimento.\n\n' for i in range(100))
win.set_content(text,None);pump()
win.view.grab_focus()
win.buf.select_range(win.buf.get_iter_at_offset(0),win.buf.get_iter_at_offset(5))
shortcut(Gdk.KEY_Control_L,Gdk.KEY_b)
assert win.get_text().startswith('**Parag**')
shortcut(Gdk.KEY_Control_L,Gdk.KEY_z)
assert win.get_text()==text
print('PASS: formattazione Ctrl+B e annullamento Ctrl+Z con tastiera X11.')
cursor=text.index('Paragrafo 060')+20
win.buf.place_cursor(win.buf.get_iter_at_offset(cursor))
win.view.scroll_to_mark(win.buf.get_insert(),.1,True,.5,.5);pump()
original_view=win.document_viewport()
original_text=win.get_text()
shortcut(Gdk.KEY_Control_L,Gdk.KEY_Shift_L,Gdk.KEY_n)
assert win._editing_note=='1',('shortcut note non attiva',win._editing_note,win.get_focus())
assert win.right_stack.get_visible_child_name()=='footnotes'
assert len([w for w in Gtk.Window.list_toplevels() if w.get_window_type()==Gtk.WindowType.TOPLEVEL and w.get_visible()])==1, Gtk.Window.list_toplevels()
assert abs(win.document_viewport()[1]-original_view[1])<2,(original_view,win.document_viewport())
assert win.get_text()[cursor:cursor+4]=='[^1]'
win.note_editor.get_buffer().set_text('Una nota modificata con tastiera.')
shortcut(Gdk.KEY_Control_L,Gdk.KEY_Return)
assert win._editing_note is None
assert '[^1]: Una nota modificata con tastiera.' in win.get_text()
assert abs(win.document_viewport()[1]-original_view[1])<2,(original_view,win.document_viewport())
print('PASS: Ctrl+Shift+N e Ctrl+Invio con eventi X11 reali; vista conservata; nessuna finestra aggiuntiva.')
# Appunti: editor condiviso, salvataggio su disco, nessuna modifica al documento.
win.add_note('Appunto originale');before=win.get_text()
win.right_stack.set_visible_child_name('scratch');pump()
win.edit_scratch(0);pump()
win.note_editor.get_buffer().set_text('Appunto modificato ☕\nSeconda riga')
shortcut(Gdk.KEY_Control_L,Gdk.KEY_Return)
assert win.notes[0]=='Appunto modificato ☕\nSeconda riga'
assert json.loads(Path(NOTES_PATH).read_text())[0]==win.notes[0]
assert win.get_text()==before
win.edit_scratch(0);win.note_editor.get_buffer().set_text('Da annullare')
shortcut(Gdk.KEY_Escape)
assert win.notes[0]=='Appunto modificato ☕\nSeconda riga'
assert win.get_text()==before
print('PASS: modifica appunti persistita, annullamento, documento invariato.')
# Scorciatoia anche quando il focus è nella ricerca.
win.search.grab_focus();pump()
shortcut(Gdk.KEY_Control_L,Gdk.KEY_Shift_L,Gdk.KEY_n)
assert win._editing_note=='2',win._editing_note
win.cancel_margin_note();pump()
print('PASS: aggiunta nota dalla ricerca senza perdere il documento.')
# Schede a piena altezza e navigazione al richiamo.
win.goto_margin_note('1');pump()
a,b=win.buf.get_selection_bounds();assert win.buf.get_text(a,b,True)=='[^1]'
win.right_stack.set_visible_child_name('scratch');pump()
win.get_window().get_geometry()
assert win.right_stack.get_allocated_height()>win.get_allocated_height()*.7
print('PASS: schede a piena altezza e navigazione al richiamo.')
# Anche il percorso menu conserva la posizione.
cursor=win.get_text().index('Paragrafo 075')+15
win.buf.place_cursor(win.buf.get_iter_at_offset(cursor))
win.view.scroll_to_mark(win.buf.get_insert(),.1,True,.5,.5);pump()
position=win.document_viewport()
win.format_btn.clicked();pump()
win.format_menu.get_children()[0].get_children()[-1].clicked();pump()
assert win._editing_note=='3'
assert abs(win.document_viewport()[1]-position[1])<2,(position,win.document_viewport())
win.cancel_margin_note();pump()
print('PASS: aggiunta da menu + conserva la vista.')
# Un errore di scrittura mantiene l’appunto aperto e non perde il testo.
import tasto.app as app_module
saved_json=app_module.save_json
before=win.notes.copy();win.edit_scratch(0);win.note_editor.get_buffer().set_text('Da non perdere')
app_module.save_json=lambda *args:False
win.save_margin_note()
assert win._editing_note==('scratch',0) and win.notes==before
assert win.note_editor.get_buffer().get_text(*win.note_editor.get_buffer().get_bounds(),True)=='Da non perdere'
app_module.save_json=saved_json
win.cancel_margin_note();pump()
print('PASS: errore di scrittura appunti non perde testo e lascia aperto l’editor.')
# Acquisizione facoltativa del pannello condiviso, per il controllo visivo.
win.edit_scratch(0);pump()
shot=Gdk.pixbuf_get_from_window(win.get_window(),0,0,win.get_allocated_width(),win.get_allocated_height())
if path := os.environ.get('TASTO_TEST_SCREENSHOT'):
    shot.savev(path,'png',[],[])
win.cancel_margin_note();pump()
win.right_stack.set_visible_child_name('footnotes');pump()
win.cfg['autosave']=False;win.buf.set_modified(False)
assert win.on_delete() is False
win.destroy();pump(.1)
second=Tasto();second.cfg['autosave']=False;second.start();second.dismiss_splash();pump()
assert second.right_stack.get_visible_child_name()=='footnotes', (second.cfg['right_page'],second.right_stack.get_visible_child_name())
# Numerazione per posizione, clic reciproco e cancellazione atomica con annulla/ripeti.
win = second
x11.XSetInputFocus(display,win.get_window().get_xid(),2,0);x11.XFlush(display)
baseline='Alfa[^1] Beta[^2] Gamma[^3].\n\n[^1]: prima\n[^2]: seconda\n[^3]: terza\n'
win.set_content(baseline,None);win.view.grab_focus();pump()
win.buf.place_cursor(win.buf.get_iter_at_offset(baseline.index('Beta')))
shortcut(Gdk.KEY_Control_L,Gdk.KEY_Shift_L,Gdk.KEY_n)
assert win._editing_note=='2'
win.note_editor.get_buffer().set_text('inserita prima di Beta')
shortcut(Gdk.KEY_Control_L,Gdk.KEY_Return)
from tasto.footnotes import notes, reference_offset, references
assert {n.number:n.content for n in notes(win.get_text())}=={'1':'prima','2':'inserita prima di Beta','3':'seconda','4':'terza'}
assert 'Beta[^3]' in win.get_text()
print('PASS: inserimento prima di una nota rinumera richiami e contenuti associati.')
# Clic nativo sul richiamo, non chiamata diretta al callback.
position=reference_offset(win.get_text(),'3')
iterator=win.buf.get_iter_at_offset(position)
win.view.scroll_to_iter(iterator,.1,True,.5,.5);pump()
rectangle=win.view.get_iter_location(iterator)
x,y=win.view.buffer_to_window_coords(Gtk.TextWindowType.TEXT,rectangle.x+max(1,rectangle.width//2),rectangle.y+rectangle.height//2)
_,origin_x,origin_y=win.view.get_window(Gtk.TextWindowType.TEXT).get_origin()
xtst.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
xtst.XTestFakeMotionEvent(display,0,origin_x+x,origin_y+y,0)
xtst.XTestFakeButtonEvent(display,1,1,0);xtst.XTestFakeButtonEvent(display,1,0,0)
x11.XFlush(display);pump()
assert win._editing_note=='3',win._editing_note
assert win.note_editor.get_buffer().get_text(*win.note_editor.get_buffer().get_bounds(),True)=='seconda'
win.cancel_margin_note();pump()
print('PASS: clic X11 sul richiamo apre la nota corretta.')
# Backspace al termine del marcatore rimuove richiamo e definizione insieme.
before=win.get_text();position=reference_offset(before,'3')
win.buf.place_cursor(win.buf.get_iter_at_offset(position+4));win.view.grab_focus()
shortcut(Gdk.KEY_BackSpace)
after=win.get_text()
assert 'seconda' not in after and 'Gamma[^3]' in after
shortcut(Gdk.KEY_Control_L,Gdk.KEY_z)
assert win.get_text()==before
shortcut(Gdk.KEY_Control_L,Gdk.KEY_y)
assert win.get_text()==after
print('PASS: cancellazione richiamo, rinumerazione, Ctrl+Z e Ctrl+Y ripristinano anche il contenuto.')
# Cancellazione della definizione: rimuove anche il richiamo nel corpo.
win.set_content(baseline,None);pump()
note=notes(win.get_text())[1]
win.buf.select_range(win.buf.get_iter_at_offset(note.start),win.buf.get_iter_at_offset(note.end))
shortcut(Gdk.KEY_Delete)
assert 'seconda' not in win.get_text() and win.get_text().startswith('Alfa[^1] Beta Gamma[^2]')
shortcut(Gdk.KEY_Control_L,Gdk.KEY_z)
assert win.get_text()==baseline
# Più richiami: il primo eliminato non cancella la nota ancora citata.
reused='A[^1] B[^1] C[^2]\n\n[^1]: condivisa\n[^2]: altra\n'
win.set_content(reused,None);win.view.grab_focus();pump()
win.buf.select_range(win.buf.get_iter_at_offset(1),win.buf.get_iter_at_offset(5))
shortcut(Gdk.KEY_Delete)
assert 'condivisa' in win.get_text() and len([r for r in references(win.get_text()) if r.number=='1'])==1
shortcut(Gdk.KEY_Control_L,Gdk.KEY_z)
assert win.get_text()==reused
print('PASS: dipendenza inversa e conservazione delle note con richiami ripetuti.')
second.buf.set_modified(False);second.destroy();pump(.1)
print('PASS: la scheda selezionata è ricordata al riavvio.')

assert not errors, errors
