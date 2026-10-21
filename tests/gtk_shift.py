"""Isolated GTK/X11 test: xvfb-run -a /usr/bin/python3 tests/gtk_shift.py.
Uses temporary XDG paths and native pointer events; never run on your working display.
"""
import os,sys,tempfile,time
from pathlib import Path
root=tempfile.TemporaryDirectory()
for var,folder in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
    os.environ[var]=root.name+'/'+folder;Path(os.environ[var]).mkdir()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tasto.app import Tasto,DEFAULTS
from gi.repository import Gtk,Gdk
DEFAULTS['folder']=root.name
errors=[]
sys.excepthook=lambda *args: (errors.append(args),sys.__excepthook__(*args))
w=Tasto();w.cfg['autosave']=False
w.error=lambda message: (_ for _ in ()).throw(AssertionError(message))
w.start();w.dismiss_splash()
def pump(seconds=.3):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.005)
p=Path(root.name)/'a.md';original='Primo **paragrafo**.\n\nSecondo paragrafo.\n\nTerzo.';p.write_text(original)
w.set_content(original,str(p));w.buf.place_cursor(w.buf.get_start_iter());pump()
assert w.shift_add.get_visible()
assert w.add_shift();pump()
assert len(w.shift_groups)==1
assert not any(w.buf.get_iter_at_offset(0).has_tag(t) for t in w.md_tags)
assert w.shift_preview.get_visible()
w.buf.begin_user_action();w.buf.insert_at_cursor('Alternativa **due**.');w.buf.end_user_action();pump()
assert w.select_shift(-1);pump()
assert w.get_text()==original,(w.get_text(),original)
assert w.select_shift(1);pump()
assert w.get_text().startswith('Alternativa **due**.\n\nSecondo')
assert w.file_save(); active=w.get_text()
w.set_content(p.read_text(),str(p));pump()
assert w.get_text()==active and len(w.shift_groups)==1
w.buf.place_cursor(w.buf.get_start_iter());assert w.select_shift(-1);pump()
assert w.get_text()==original
w.buf.undo();pump();assert w.get_text()==active and w.shift_groups[0]['active']==1
w.buf.redo();pump();assert w.get_text()==original and w.shift_groups[0]['active']==0
assert not errors,errors
print('PASS create, type, previous/next, save/reopen, undo/redo',flush=True)
# Native pointer clicks exercise the same + and arrow buttons a writer uses.
import ctypes
x11=ctypes.CDLL('libX11.so.6');xtst=ctypes.CDLL('libXtst.so.6')
x11.XOpenDisplay.restype=ctypes.c_void_p;x11.XOpenDisplay.argtypes=[ctypes.c_char_p]
x11.XFlush.argtypes=[ctypes.c_void_p]
xtst.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
xtst.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
display=x11.XOpenDisplay(None)
def click(widget, settle=.3):
    px,py=widget.translate_coordinates(w,widget.get_allocated_width()//2,widget.get_allocated_height()//2)
    _,ox,oy=w.get_window().get_origin()
    xtst.XTestFakeMotionEvent(display,-1,ox+px,oy+py,0)
    xtst.XTestFakeButtonEvent(display,1,1,0);xtst.XTestFakeButtonEvent(display,1,0,0)
    x11.XFlush(display);pump(settle)
click(w.shift_next)
assert w.shift_groups[0]['active']==1 and w.shift_preview.get_visible()
rect=w.view.get_iter_location(w.buf.get_start_iter())
_,cy=w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,rect.x,rect.y)
assert 0 <= cy < w.view.get_allocated_height()
assert w.view.get_top_margin()==48
click(w.shift_add)
assert w.shift_groups[0]['active']==2 and len(w.shift_groups[0]['versions'])==3
w.buf.begin_user_action();w.buf.insert_at_cursor('Terza variante _letterale_.');w.buf.end_user_action();pump()
click(w.shift_prev)
assert w.get_text().startswith('Alternativa **due**.')
click(w.shift_next)
assert w.get_text().startswith('Terza variante _letterale_.')
assert w.shift_preview.get_buffer().get_text(*w.shift_preview.get_buffer().get_bounds(),True)=='Alternativa **due**.'
w.close_shift();pump()
assert not w.shift_preview.get_visible() and w.left_pane.get_visible()==w.cfg['sidebar']
assert w.view.get_top_margin()==48
w.resize(820,740);pump()
assert w.get_size().width <= 840, w.get_size()
w.resize(1280,800);pump()
print('PASS native + / previous / next, centered horizontal layout, literal Markdown, collapse and resizing',flush=True)

# Anchors follow ordinary text edits before another group.
pos=w.get_text().index('Secondo')
w.buf.place_cursor(w.buf.get_iter_at_offset(pos));pump()
assert w.add_shift();pump()
w.buf.begin_user_action();w.buf.insert_at_cursor('Secondo alternativo');w.buf.end_user_action();pump()
assert len(w.shift_groups)==2
w.close_shift();w.buf.begin_user_action();w.buf.insert(w.buf.get_start_iter(),'Premessa.\n\n');w.buf.end_user_action();pump()
assert w.select_shift(-1);pump()
assert 'Secondo paragrafo.' in w.get_text() and w.get_text().startswith('Premessa.')
assert w.file_save()
saved=w.get_text()
# Other document / save-as isolation.
other=Path(root.name)/'b.md';other.write_text('Documento B')
w.set_content(other.read_text(),str(other));pump();assert not w.shift_groups
w.set_content(saved,str(p));pump();assert len(w.shift_groups)==2
w.buf.place_cursor(w.buf.get_iter_at_offset(saved.index('Terza')));pump()
assert w.select_shift(-1);pump()
assert w.discard_shift()
w.set_content(p.read_text(),str(p));pump();assert w.get_text()==saved
assert w.shift_groups[0]['active']==2
print('PASS multiple groups, moving anchors, document isolation and discard',flush=True)

# Delete selected versions, including identical and empty variants, with native undo.
remove=Path(root.name)/'remove.md';remove.write_text('# Titolo\n\nOriginale **uno**.\n\nFinale.')
w.set_content(remove.read_text(),str(remove));pump()
body=w.get_text().index('Originale')
w.buf.place_cursor(w.buf.get_iter_at_offset(body));pump()
assert w.add_shift();pump()
w.buf.begin_user_action();w.buf.insert_at_cursor('Seconda **versione**.');w.buf.end_user_action();pump()
assert w.shift_delete.get_visible()
comparison=w._shift_open
rect=w.view.get_iter_location(w.buf.get_iter_at_offset(body))
before_y=w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,rect.x,rect.y)[1]
assert w.select_shift(-1);pump()
assert w._shift_open==comparison
now=w.view.get_iter_location(w.buf.get_iter_at_offset(body))
assert abs(w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,now.x,now.y)[1]-before_y)<3
assert w.view.get_top_margin()==48
w.editor_sw.get_vadjustment().set_value(0);pump()
heading=w.view.get_iter_location(w.buf.get_start_iter())
assert w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,heading.x,heading.y)[1]<120
assert w.buf.get_start_iter().has_tag(w.t_h[0])
assert w.select_shift(1);pump()
click(w.shift_delete)
assert len(w.shift_groups[0]['versions'])==1 and 'Originale **uno**.' in w.get_text()
assert not w.delete_shift()
w.buf.undo();pump();assert len(w.shift_groups[0]['versions'])==2 and 'Seconda **versione**.' in w.get_text()
w.buf.redo();pump();assert len(w.shift_groups[0]['versions'])==1
assert w.add_shift();pump()
# Two empty versions require undo even though deleting one changes no Markdown.
assert w.add_shift();pump()
text=w.get_text();count=len(w.shift_groups[0]['versions'])
assert w.delete_shift();pump();assert w.get_text()==text and len(w.shift_groups[0]['versions'])==count-1
w.buf.undo();pump();assert w.get_text()==text and len(w.shift_groups[0]['versions'])==count
w.buf.redo();pump();assert len(w.shift_groups[0]['versions'])==count-1
assert w.file_save()
w.set_content(remove.read_text(),str(remove));pump();assert len(w.shift_groups[0]['versions'])==count-1
print('PASS Markdown in main flow, no title overscroll, stable option switches and undoable version deletion',flush=True)

# Regression: native typing immediately after + in a long document, then navigation.
x11.XSetInputFocus.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
x11.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
x11.XKeysymToKeycode.restype=ctypes.c_uint
xtst.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
x11.XSetInputFocus(display,w.get_window().get_xid(),2,0);x11.XFlush(display)
def native_key(symbol):
    code=x11.XKeysymToKeycode(display,symbol)
    xtst.XTestFakeKeyEvent(display,code,1,0);xtst.XTestFakeKeyEvent(display,code,0,0)
    x11.XFlush(display);pump()
longfile=Path(root.name)/'long.md'
longtext=''.join(f'Paragrafo {i:03} con testo.\n\n' for i in range(80))
longfile.write_text(longtext)
w.set_content(longtext,str(longfile));pump()
position=longtext.index('Paragrafo 040')
w.buf.place_cursor(w.buf.get_iter_at_offset(position));pump()
w.view.scroll_to_mark(w.buf.get_insert(),0,True,.5,.5);pump()
click(w.shift_add, settle=.01)
assert w.get_focus() is w.view
native_key(Gdk.KEY_x)
assert w.get_text()[position:position+3]=='x\n\n'
rect=w.view.get_iter_location(w.buf.get_iter_at_offset(position))
_,cy=w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,rect.x,rect.y)
assert abs(cy-w.view.get_allocated_height()/2)<40, (cy,w.document_viewport())
identity=w._shift_open
viewport=w.document_viewport()[1]
native_key(Gdk.KEY_Down);native_key(Gdk.KEY_Down)
assert w._shift_open==identity and abs(w.document_viewport()[1]-viewport)<2
native_key(Gdk.KEY_Up);native_key(Gdk.KEY_Up)
assert w._shift_open==identity and abs(w.document_viewport()[1]-viewport)<2
# A click in a different paragraph must leave the comparison geometry unchanged.
next_position=w.get_text().index('Paragrafo 041')+4
rect=w.view.get_iter_location(w.buf.get_iter_at_offset(next_position))
px,py=w.view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,rect.x+2,rect.y+5)
px,py=w.view.translate_coordinates(w,px,py)
_,ox,oy=w.get_window().get_origin()
xtst.XTestFakeMotionEvent(display,-1,ox+px,oy+py,0)
xtst.XTestFakeButtonEvent(display,1,1,0);xtst.XTestFakeButtonEvent(display,1,0,0)
x11.XFlush(display);pump()
assert w._shift_open==identity and abs(w.document_viewport()[1]-viewport)<2
assert w.shift_context()[0] is None
w.editor_sw.get_vadjustment().set_value(0);pump()
assert w.shift_close.get_visible()
click(w.shift_close)
assert w._shift_open is None and w._shift_center_source==0
assert w.view.get_top_margin()==48
print('PASS immediate native typing after +, centered long document and stable click/arrow navigation',flush=True)

# The last block can have an empty alternative and survive reopening.
last=Path(root.name)/'last.md';last.write_text('Unico paragrafo')
w.set_content(last.read_text(),str(last));pump()
assert w.add_shift();pump()
assert w.get_text().strip()==''
assert w.file_save()
w.set_content(last.read_text(),str(last));pump()
assert len(w.shift_groups)==1 and w.select_shift(-1)
pump();assert w.get_text()=='Unico paragrafo'
# Inactive footnote references must not attach to a different renumbered note.
notes=Path(root.name)/'notes.md'
notes.write_text('Uno[^1].\n\nDue[^2].\n\n[^1]: nota originale\n[^2]: nota comune\n')
w.set_content(notes.read_text(),str(notes));pump()
assert w.add_shift();pump()
w.buf.begin_user_action();w.buf.insert_at_cursor('Alternativa.');w.buf.end_user_action();pump()
assert w.select_shift(-1);pump()
from tasto.footnotes import references, notes as document_notes
first_reference=references(w.get_text())[0]
definitions={n.number:n.content for n in document_notes(w.get_text())}
assert definitions[first_reference.number]=='nota originale', (w.get_text(),w.shift_snapshot())
assert any(value=='nota comune' for value in definitions.values())
assert w.file_save()
notes_text=w.get_text()
w.set_content(notes.read_text(),str(notes));pump()
assert w.get_text()==notes_text and len(w.shift_groups)==1 and not w._shift_corrupt
print('PASS empty last variant and original footnote contents after renumbering',flush=True)
# Return to the multi-variant fixture for failure and recovery tests.
w.set_content(p.read_text(),str(p));pump()
w.buf.place_cursor(w.buf.get_iter_at_offset(w.get_text().index('Terza')));pump()

# Write failures cannot erase either active or inactive text.
import tasto.app as app
original_save=app.save_json
messages=[];w.error=messages.append
app.save_json=lambda *args: False
text=w.get_text();before=w.shift_snapshot()
assert not w.add_shift()
assert w.get_text()==text and w.shift_snapshot()==before and messages
app.save_json=original_save
assert w.persist_shift()
# Unsaved recovery after a variant switch.
assert w.select_shift(-1);pump();recovered=w.get_text()
w.set_content(p.read_text(),str(p));pump();assert w.get_text()==recovered
# Conflicting external changes must never be overwritten, even by refresh.
archive=Path(w.shift_path()).read_text()
p.write_text('Modificato esternamente')
w.refresh()
w.set_content(p.read_text(),str(p));pump()
assert w.get_text()=='Modificato esternamente' and w._shift_corrupt
assert Path(w.shift_path()).read_text()==archive
assert not w.persist_shift()
assert not errors,errors
print('PASS write failures, unsaved recovery and external conflict preservation',flush=True)
w.destroy()
