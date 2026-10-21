"""Run only on an isolated display: xvfb-run -a /usr/bin/python3 tests/gtk_paragraphs.py.
Uses temporary XDG directories and generates native X11 pointer events.
"""
import os, tempfile, sys
from pathlib import Path
root=tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME']=root.name+'/cfg'
os.environ['XDG_DATA_HOME']=root.name+'/data'
os.environ['XDG_CACHE_HOME']=root.name+'/cache'
Path(os.environ['XDG_CACHE_HOME']).mkdir()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tasto.app import Tasto
from tasto.paragraphs import blocks
from gi.repository import Gtk
w=Tasto(); w.cfg['autosave']=False
w.error=lambda msg: (_ for _ in ()).throw(AssertionError(msg))
w.start(); w.dismiss_splash()
p=Path(root.name)/'a.md'; p.write_text('Uno.\n\nDue.\n\nTre.')
w.set_content(p.read_text(),str(p))
assert w.park_block(blocks(w.get_text())[1])
assert 'Due.' not in w.get_text() and len(w.parked)==1
parked_text=w.get_text(); identity=w.parked[0]['id']
w.buf.undo(); assert w.get_text()==p.read_text() and not w.parked
w.buf.redo(); assert w.get_text()==parked_text and len(w.parked)==1
w.set_content(p.read_text(),str(p)); assert w.get_text()==parked_text and len(w.parked)==1
assert w.restore_block(identity,0)
assert w.get_text().startswith('Due.\n\nUno.') and not w.parked
w.buf.undo(); assert w.get_text()==parked_text and len(w.parked)==1
w.buf.redo(); assert not w.parked
assert w.file_save()
w.set_content(p.read_text(),str(p)); assert not w.parked
# Reopen a document must never replace external edits with a recovery snapshot.
w.park_block(blocks(w.get_text())[0]); p.write_text('Modifica esterna')
w.refresh()  # Persisting the dock must not adopt an external edit as its recovery base.
w.set_content(p.read_text(),str(p)); assert w.get_text()=='Modifica esterna' and w.parked
# Other documents have their own dock.
other=Path(root.name)/'b.md';other.write_text('Altro')
w.set_content(other.read_text(),str(other)); assert not w.parked
print('PASS dock move, undo/redo, recovery without autosave, restore, save/reopen, external edit, isolation',flush=True)
# Notes follow a parked reference and survive conflicting numbering on restore.
w.set_content('Uno[^1].\n\nDue[^2].\n\n[^1]: nota uno\n[^2]: nota due\n', None)
assert w.park_block(blocks(w.get_text())[0])
assert 'nota uno' not in w.get_text() and 'nota due' in w.get_text()
assert w.restore_block(w.parked[0]['id'], 0)
assert 'Uno[^1]' in w.get_text() and '[^1]: nota uno' in w.get_text()
assert '[^2]: nota due' in w.get_text()
print('PASS footnotes move with paragraphs and restore after renumbering', flush=True)

# A failed card save must leave both the document and the dock untouched.
import tasto.app as app
original_save = app.save_json
errors=[]
w.error=errors.append
original_text=w.get_text(); original_cards=list(w.parked)
app.save_json=lambda *args: False
assert not w.park_block(blocks(original_text)[0])
assert w.get_text()==original_text and w.parked==original_cards and errors
app.save_json=original_save
assert w.persist_dock(w.parked)
# Discard restores both halves of the last saved document/dock state.
assert w.park_block(blocks(w.get_text())[0])
assert w.discard_dock_changes()
w.set_content('', None)
assert not w.parked and not w.get_text()
print('PASS failed writes preserve text; discard restores saved dock',flush=True)

# Exercise the actual GTK drag source/destination with native X11 pointer events.
import ctypes, time
x11=ctypes.CDLL('libX11.so.6'); xtst=ctypes.CDLL('libXtst.so.6')
x11.XOpenDisplay.restype=ctypes.c_void_p
x11.XOpenDisplay.argtypes=[ctypes.c_char_p]
x11.XFlush.argtypes=[ctypes.c_void_p]
xtst.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
display=x11.XOpenDisplay(None)
def pump(seconds=.2):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.005)
def motion(x,y):
    xtst.XTestFakeMotionEvent(display,-1,int(x),int(y),0);x11.XFlush(display);pump(.1)
def button(down):
    xtst.XTestFakeButtonEvent(display,1,int(down),0);x11.XFlush(display);pump(.1)
def screen(widget,x=0,y=0):
    wx,wy=widget.translate_coordinates(w, int(x),int(y))
    _, ox,oy=w.get_window().get_origin()
    return ox+wx,oy+wy
w.set_content('Primo paragrafo.\n\nSecondo paragrafo.', str(other))
w.right_stack.set_visible_child_name('paragraphs')
if not w.cfg['notes']: w.toggle_notes()
w.show_all();w.dismiss_splash();pump()
rect=w.view.get_iter_location(w.buf.get_start_iter())
px,py=w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,rect.x+15,rect.y+5)
motion(*screen(w.view,px,py));pump()
assert w.grip.get_visible(), 'hover handle invisible'
sx,sy=screen(w.grip,12,12)
dx,dy=screen(w.dock_list,45,45)
motion(sx,sy);button(True)
for step in range(1,21): motion(sx+(dx-sx)*step/20,sy+(dy-sy)*step/20)
button(False);pump()
assert len(w.parked)==1 and 'Primo' not in w.get_text(), ('native parking failed',w.get_text(),w.parked)
card=w.dock_list.get_children()[1]
sx,sy=screen(card,25,20)
rect=w.view.get_iter_location(w.buf.get_start_iter())
px,py=w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,rect.x,rect.y+5)
dx,dy=screen(w.view,px,py)
motion(sx,sy);button(True)
for step in range(1,21): motion(sx+(dx-sx)*step/20,sy+(dy-sy)*step/20)
button(False);pump()
assert not w.parked and 'Primo paragrafo.' in w.get_text(), ('native restoring failed', w.get_text(),w.parked)
print('PASS native X11 hover grip and drag/drop both directions',flush=True)
w.destroy()
