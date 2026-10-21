#!/usr/bin/env python3
"""Tasto: editor di testo minimale per scrivere in Markdown (GTK 3 + GtkSourceView 4).

Dipendenze (Debian/Ubuntu):
    sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtksource-4 fonts-ibm-plex fonts-noto-core
(IBM Plex è il carattere principale; se manca, il programma ripiega su Noto.)
Per i suoni serve uno tra pw-play, paplay, aplay (pipewire-bin, pulseaudio-utils, alsa-utils).

Uso:
    /usr/bin/python3 -m tasto [file.md]

Salvataggio automatico: i file con nome vengono salvati da soli pochi secondi dopo
le modifiche; il testo senza nome viene conservato come bozza e ripristinato al
prossimo avvio. Si disattiva dall'ingranaggio.

Scorciatoie:
    Ctrl+N / Ctrl+O / Ctrl+S / Ctrl+Shift+S   nuovo, apri, salva, salva con nome
    Ctrl+B / Ctrl+I / Ctrl+U                 grassetto, corsivo, sottolineato
    Ctrl+Shift+X / Ctrl+Shift+N               barrato, nota a margine
    Ctrl+Z / Ctrl+Y                           annulla, ripeti
    Ctrl++ / Ctrl+- / Ctrl+0                  ingrandisci, riduci, ripristina il corpo del testo
    Ctrl + rotella                            ingrandisci o riduci il corpo del testo
    Ctrl+F                                    cerca nel testo (Invio: successivo, Maiusc+Invio: precedente)
    F1  istruzioni markdown   F8  inserisci ASCII art   F9  indice   F10  appunti

Suoni personalizzati: metti in ~/.config/tasto/sounds/ dei file WAV chiamati
key1.wav ... key4.wav, space.wav, back.wav, enter.wav; al posto di quelli sintetici
verranno usati i tuoi.
"""

import bisect
from .formatting import format_edit
from .preview import parse as parse_preview, active_lines
from .library import markdown_files, recent_in_folder, remember_file
from .footnotes import notes as document_notes, add_note as add_footnote, update_note, reference_offset, references, synchronize_notes, reconcile_notes
from pathlib import Path
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import time
import wave

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gdk, GLib, GtkSource, Gtk, Pango

APP = "Tasto"
CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "tasto")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
NOTES_PATH = os.path.join(CONFIG_DIR, "appunti.json")
RECOVERY_PATH = os.path.join(GLib.get_user_data_dir(), "tasto", "recupero.md")

# --- Impostazioni modificabili -------------------------------------------------


def theme(label, fg, bg, dim, sel, line, find,
          head, bold, ital, code, quote, lst, link):
    """fg/bg testo e sfondo, dim testo attenuato, sel selezione e passaggio del mouse,
    line filetti sottili, find evidenziazione della ricerca; il resto sono i colori
    del markdown (opzione "Colori")."""
    return dict(label=label, fg=fg, bg=bg, dim=dim, sel=sel, line=line, find=find,
                syn=dict(head=head, bold=bold, ital=ital, code=code,
                         quote=quote, list=lst, link=link))


THEMES = {
    "chiaro": theme("Chiaro", "#111111", "#ffffff", "#666666", "#dbe3f0", "#dcdcdc", "#ffe58f",
                    "#0550ae", "#953800", "#8250df", "#1a7f37", "#57606a", "#cf222e", "#0969da"),
    "seppia": theme("Seppia", "#3a2412", "#f0e4c8", "#5f4c30", "#dccaa0", "#d7c8a2", "#f2c94c",
                    "#a2381b", "#7a4a00", "#6b3f8a", "#2f6b3a", "#5f4c30", "#a2381b", "#1f5f8b"),
    "antracite": theme("Scuro", "#f0f0f0", "#2b2f33", "#9aa1a8", "#4b535b", "#3d4348", "#5a4a14",
                       "#79c0ff", "#ffa657", "#d2a8ff", "#7ee787", "#9aa1a8", "#ff7b72", "#58a6ff"),
    "ghiaccio": theme("Ghiaccio", "#24384b", "#edf3f8", "#526779", "#cedeea", "#c9d7e3", "#f5df92",
                      "#185b9d", "#934117", "#7147a2", "#226745", "#526779", "#a33349", "#145f85"),
    "sole": theme("Sole", "#55351c", "#fff0ce", "#7b5b36", "#efd29b", "#dfc594", "#efd06b",
                  "#95451d", "#805200", "#86418c", "#396333", "#7b5b36", "#a33428", "#266777"),
    "dracula": theme("Dracula", "#f8f8f2", "#282a36", "#a6accd", "#44475a", "#44475a", "#66552c",
                     "#bd93f9", "#ffb86c", "#ff79c6", "#50fa7b", "#a6accd", "#ff5555", "#8be9fd"),
    "terminale": theme("Terminale", "#a4e5a0", "#101a13", "#7cab7d", "#294532", "#304a37", "#4d5427",
                       "#c1f5ad", "#e0d68a", "#86d8af", "#a4e5a0", "#7cab7d", "#dfb477", "#8bcac4"),
}
THEME_ORDER = ["chiaro", "ghiaccio", "seppia", "sole", "antracite", "dracula", "terminale"]

# (nome mostrato, famiglie in ordine di preferenza, fattore di grandezza).
# IBM Plex è una famiglia progettata per stare insieme, con grassetto e corsivo veri
# in tutti e tre i caratteri. Il mono, a parità di punti, appare molto più grande
# (lettere più larghe), quindi viene ridotto del 10%.
FONTS = [
    ("Mono", "'IBM Plex Mono', 'Noto Sans Mono', 'DejaVu Sans Mono', monospace", 0.9),
    ("Serif", "'IBM Plex Serif', 'Noto Serif', 'DejaVu Serif', serif", 1.0),
    ("Sans", "'IBM Plex Sans', 'Noto Sans', 'DejaVu Sans', sans-serif", 1.0),
]
CODE_FAMILY = "IBM Plex Mono, Noto Sans Mono, DejaVu Sans Mono, Monospace"  # blocchi ``` e ASCII art

SIZE_MIN, SIZE_MAX = 8, 48                        # pt
WIDTH_MIN, WIDTH_MAX, WIDTH_STEP = 360, 1800, 60  # px
PARAGRAPH_SPACE = 0.8   # spazio dopo l'a capo, in multipli del corpo del testo
LINE_SPACE = 0.25       # spazio extra tra le righe di uno stesso paragrafo
UI_SIZE = 10            # pt, barre laterali, barra inferiore e menu
SIDE_MIN, SIDE_MAX, SIDE_RATIO = 220, 300, 0.2    # barre laterali: 20% della finestra, tra 220 e 300 px
SIDE_GAP = 24           # distanza minima tra una barra laterale e il testo (px)
TEXT_MIN = 320          # sotto questa larghezza la colonna non viene più centrata
RIGHT_GAP = 16          # distanza del testo dei titoli dal bordo destro della barra
MAX_RESULTS = 500       # risultati massimi evidenziati nel testo
RESULT_ROWS = 150       # risultati mostrati nell'elenco
CONTEXT_BEFORE, CONTEXT_AFTER = 40, 140   # caratteri di contesto nell'anteprima dei risultati
AUTOSAVE_SECONDS = 5    # il salvataggio automatico scatta al massimo ogni tot secondi
SHOW_CLOCK = True       # orologio al centro della barra inferiore
MODIFIER_KEYS = ("Shift", "Control", "Alt", "Meta", "Super", "Hyper", "Caps_Lock",
                 "Num_Lock", "ISO_Level", "Mode_switch")   # non chiudono la schermata iniziale

DEFAULTS = {"theme": "chiaro", "font": 1, "size": 14, "width": 720, "sidebar": True,
            "notes": False, "right_page": "scratch", "target": 0, "colors": False, "sound": False,
            "autosave": True, "folder": "", "recent_files": [], "win": [1280, 800]}

CSS = Path(__file__).with_name("style.css").read_text(encoding="utf-8")


def extra_css():
    """Ogni campione mostra sfondo e carattere del proprio tema."""
    return "\n".join(f"#bar button.sq.sq-{key}, #pop button.sq.sq-{key} {{ background-color: {THEMES[key]['bg']}; }} "
                     f"#bar button.sq.sq-{key} label, #pop button.sq.sq-{key} label {{ color: {THEMES[key]['fg']}; }}"
                     for key in THEME_ORDER)


# --- Markdown ------------------------------------------------------------------

QUOTE = re.compile(r"^\s{0,3}>")
LIST = re.compile(r"^\s*([-+*]|\d{1,3}[.)])(?=\s)")
WORD = re.compile(r"\S*\w\S*")

HELP = [
    ("# Titolo", "titolo di primo livello"),
    ("## Titolo", "secondo livello"),
    ("### Titolo", "terzo livello"),
    ("**testo**", "grassetto · Ctrl+B"),
    ("*testo*  _testo_", "corsivo · Ctrl+I"),
    ("<u>testo</u>", "sottolineato · Ctrl+U"),
    ("~~testo~~", "barrato · Ctrl+Shift+X"),
    ("[^1] / [^1]: nota", "nota a margine · Ctrl+Shift+N"),
    ("- voce", "elenco puntato"),
    ("1. voce", "elenco numerato"),
    ("> testo", "citazione"),
    ("[testo](indirizzo)", "collegamento"),
    ("`codice`", "codice nel testo"),
    ("```", "blocco di codice (a inizio e a fine)"),
    ("---", "linea di separazione"),
]
HELP_NOTE = ("I titoli #, ## e ### compaiono nell'indice a sinistra.\n"
             "Ctrl+F cerca · F8 inserisci · F9 indice · F10 appunti e note")


# --- ASCII art per il menu Inserisci ---------------------------------------------
# Le immagini su più righe vengono inserite dentro un blocco ``` per mantenere
# l'allineamento (nel blocco il testo è sempre a spaziatura fissa).

def frame(title="", rows=2, w=34, corner="+", hor="-", ver="|"):
    top = corner + hor * w + corner
    out = [top]
    if title:
        out += [ver + title.center(w) + ver, top]
    out += [ver + " " * w + ver] * rows
    out.append(top)
    return "\n".join(out)


def book(w=13, rows=4):
    page = "  " + "~" * (w - 4) + "  "
    lines = [" ." + "-" * w + "." + "-" * w + "."]
    lines += [" |" + page + "|" + page + "|"] * rows
    lines.append(" '" + "-" * w + "'" + "-" * w + "'")
    return "\n".join(lines)


OWL = r"""
  ,_,
 (O,O)
 (   )
 -"-"-
""".strip("\n")

CAT = r"""
 |\__/,|   (`\
 |_ _  |.--.) )
 ( T   )     /
(((^_(((/(((_/
""".strip("\n")

HOURGLASS = r"""
 ,---------.
  \       /
   \     /
     ) (
    /   \
   /  .  \
  /_______\
 '---------'
""".strip("\n")

CANDLE = r"""
    )
   (_)
   |=|
   | |
  /___\
""".strip("\n")

CUP = r"""
    ( (
     ) )
  ........
  |      |]
  \      /
   `----'
""".strip("\n")

BOAT = r"""
       |\
       | \
       |  \
       |___\
   ____|____\____
   \            /
    \__________/
""".strip("\n")

FIR = r"""
      *
     /|\
    //|\\
   ///|\\\
  ////|\\\\
      |
""".strip("\n")

HEART = r"""
  _____     _____
 /     \   /     \
|       \ /       |
 \               /
  \             /
   \           /
    \         /
     \       /
      \     /
       \   /
        \_/
""".strip("\n")

RINGS = r"""
        .-.   .-.
   ~~~~(   )-(   )~~~~
        '-'   '-'
""".strip("\n")

ASCII_ART = [
    ("Divisori", [
        ("Tre asterischi", "* * *"),
        ("Onda", "~" * 32),
        ("Onda con cresta", '_.~"~.' * 6),
        ("Trattini e uguali", "-=" * 16),
        ("Ghirlanda", ".:*~*:._" * 3 + ".:*~*:."),
        ("Asterisco centrale", "-" * 12 + " * " + "-" * 12),
        ("Puntini", ". " * 16),
        ("Cerchietti", ".oOo." * 6 + "."),
        ("Fiocchi", "~*" * 16),
        ("Più e trattini", "+-" * 16 + "+"),
        ("Rosa", "@}-;-'---"),
    ]),
    ("Intestazioni", [
        ("Parentesi e uguali", "---=[ TITOLO ]=---"),
        ("Uguali", "=== TITOLO ==="),
        ("Frecce", ">>> TITOLO <<<"),
        ("Asterischi", "* * *  TITOLO  * * *"),
    ]),
    ("Cornici", [
        ("Riquadro", frame()),
        ("Riquadro con titolo", frame("TITOLO")),
        ("Riquadro doppio", frame(corner="#", hor="=")),
        ("Riquadro di asterischi", frame(corner="*", hor="*", ver="*")),
        ("Riquadro arrotondato",
         "." + "-" * 34 + ".\n" + ("|" + " " * 34 + "|\n") * 2 + "'" + "-" * 34 + "'"),
    ]),
    ("Decorazioni", [
        ("Cuore", HEART),
        ("Rombo di asterischi",
         "\n".join(" " * (3 - k) + "*" * (2 * k + 1) for k in (0, 1, 2, 3, 2, 1, 0))),
        ("Anelli", RINGS),
    ]),
    ("Disegni", [
        ("Gufo", OWL),
        ("Gatto", CAT),
        ("Clessidra", HOURGLASS),
        ("Libro aperto", book()),
        ("Candela", CANDLE),
        ("Tazza di caffè", CUP),
        ("Barca a vela", BOAT),
        ("Abete", FIR),
    ]),
]


# --- Suono di macchina da scrivere --------------------------------------------------

RATE = 44100


def _tone(freq, ms, decay_ms, amp):
    n = int(RATE * ms / 1000)
    k = 2 * math.pi * freq / RATE
    d = RATE * decay_ms / 1000
    return [amp * math.sin(k * i) * math.exp(-i / d) for i in range(n)]


def _noise(rnd, ms, decay_ms, amp, bright=True):
    n = int(RATE * ms / 1000)
    d = RATE * decay_ms / 1000
    out, prev, low = [], 0.0, 0.0
    for i in range(n):
        x = rnd.uniform(-1, 1)
        if bright:
            y = (x - prev) * 0.5       # rumore "secco", ricco di alte frequenze
        else:
            low += 0.12 * (x - low)    # rumore "sordo", più grave
            y = low * 2.5
        prev = x
        out.append(amp * y * math.exp(-i / d))
    return out


def _mix(parts, ms):
    out = [0.0] * int(RATE * ms / 1000)
    for at, samples in parts:
        s = int(RATE * at / 1000)
        for i, v in enumerate(samples):
            if s + i < len(out):
                out[s + i] += v
    return out


def _write_wav(path, samples, level):
    peak = max(1e-9, max(abs(v) for v in samples))
    gain = level / peak
    data = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767))
                    for v in samples)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)


class Typewriter:
    """Suoni sintetizzati al volo (nessun file audio da installare), riprodotti
    con il primo lettore disponibile tra pw-play, paplay e aplay."""

    NAMES = ["key1", "key2", "key3", "key4", "space", "back", "enter"]

    def __init__(self):
        self.player = None
        for cmd, args in (("pw-play", []), ("paplay", []), ("aplay", ["-q"])):
            path = shutil.which(cmd)
            if path:
                self.player = [path] + args
                break
        self.files = {}
        self.procs = []
        self.last = 0.0

    def synth(self, name, rnd):
        if name.startswith("key"):
            parts = [(0, _noise(rnd, 14, 3, 1.0)),
                     (0, _tone(rnd.uniform(1500, 2300), 16, 3, 0.35)),
                     (1, _tone(rnd.uniform(120, 180), 55, 14, 0.8)),
                     (28, _noise(rnd, 10, 2.5, 0.3))]       # il martelletto rimbalza
            return _mix(parts, 70), 0.7
        if name == "space":
            parts = [(0, _noise(rnd, 25, 6, 0.8, False)), (0, _tone(85, 100, 22, 0.9)),
                     (30, _noise(rnd, 10, 2.5, 0.3))]
            return _mix(parts, 120), 0.8
        if name == "back":
            parts = [(0, _noise(rnd, 12, 3, 0.8)), (0, _tone(700, 14, 3, 0.3))]
            return _mix(parts, 40), 0.5
        # a capo: cricchetto del carrello e campanello
        parts = [(k * 17, _noise(rnd, 8, 2, 0.6 + 0.04 * k)) for k in range(10)]
        parts += [(190, _tone(2093, 900, 220, 0.5)), (190, _tone(5640, 400, 90, 0.2))]
        return _mix(parts, 1000), 0.6

    def prepare(self):
        if self.files:
            return
        custom = os.path.join(CONFIG_DIR, "sounds")
        cache = os.path.join(GLib.get_user_cache_dir(), "scrivi", "sounds")
        os.makedirs(cache, exist_ok=True)
        rnd = random.Random(7)
        for name in self.NAMES:
            own = os.path.join(custom, name + ".wav")
            if os.path.exists(own):
                self.files[name] = own
                continue
            path = os.path.join(cache, name + "-v1.wav")
            if not os.path.exists(path):
                samples, level = self.synth(name, rnd)
                _write_wav(path, samples, level)
            self.files[name] = path

    def play(self, name):
        if not self.player or not self.files:
            return
        now = time.monotonic()
        if now - self.last < 0.02:
            return
        self.procs = [p for p in self.procs if p.poll() is None]
        if len(self.procs) >= 8:
            return
        self.last = now
        if name == "key":
            name = random.choice(("key1", "key2", "key3", "key4"))
        try:
            self.procs.append(subprocess.Popen(
                self.player + [self.files[name]], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError:
            self.player = None


# --- Configurazione, appunti, scrittura dei file --------------------------------------

def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
        if not isinstance(cfg["folder"], str):
            cfg["folder"] = ""
        if not isinstance(cfg["recent_files"], list):
            cfg["recent_files"] = []
        cfg["recent_files"] = [path for path in cfg["recent_files"] if isinstance(path, str)][:100]
        if cfg["right_page"] not in ("scratch", "footnotes"):
            cfg["right_page"] = "scratch"
        if cfg["theme"] not in THEMES:
            cfg["theme"] = DEFAULTS["theme"]
        if not (isinstance(cfg["font"], int) and 0 <= cfg["font"] < len(FONTS)):
            cfg["font"] = DEFAULTS["font"]
        cfg["size"] = max(SIZE_MIN, min(SIZE_MAX, int(cfg["size"])))
        cfg["width"] = max(WIDTH_MIN, min(WIDTH_MAX, int(cfg["width"])))
        cfg["target"] = max(0, int(cfg["target"]))
        cfg["win"] = [int(cfg["win"][0]), int(cfg["win"][1])]
        for key in ("sidebar", "notes", "colors", "sound", "autosave"):
            cfg[key] = bool(cfg[key])
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        cfg = dict(DEFAULTS)
    return cfg


def load_notes():
    try:
        with open(NOTES_PATH, encoding="utf-8") as f:
            return [t for t in json.load(f) if isinstance(t, str)]
    except (OSError, ValueError, TypeError):
        return []


def save_json(path, data):
    return write_atomic(path, json.dumps(data, indent=2, ensure_ascii=False))


def write_atomic(path, text):
    """Scrive in un file temporaneo e poi lo sostituisce: un'interruzione a metà
    non può lasciare il file troncato. Segue i collegamenti simbolici."""
    real = os.path.realpath(path)
    tmp = real + ".tasto-tmp"
    try:
        os.makedirs(os.path.dirname(real) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(real):
            try:
                shutil.copymode(real, tmp)
            except OSError:
                pass
        os.replace(tmp, real)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def fmt(n):
    return f"{n:,}".replace(",", ".")


class Tasto(Gtk.Window):
    def __init__(self):
        super().__init__(title=APP)
        self.set_name("main")
        self.cfg = load_config()
        self.notes = load_notes()
        self.path = None
        self.typewriter = Typewriter()
        self._timer = 0
        self._autosave_timer = 0
        self._autosave_failed = False
        self._last_draft = None
        self._fit_pending = False
        self._side = -1
        self._margins = (-1, -1)
        self._heads = None      # titoli dell'ultima costruzione dell'indice
        self._keys = []
        self.collapsed = set()  # indici dei titoli chiusi nell'indice
        self._building = False
        self._matches = []      # risultati della ricerca: (inizio, fine) in caratteri
        self._results_key = None
        self._menu = None       # menu aperto in questo momento
        self._chars = 0
        self._words = 0
        self._footnote_key = None
        self._editing_note = None
        self._viewport_restore = 0
        self._note_sync_source = 0
        self._splash_timer = 0
        self._home_limit = 7
        self._home_warning = ""
        self._home_viewport = None
        self._holding_note_action = False
        self._mutating_notes = False
        self._undoing_notes = False
        self.set_default_size(*self.cfg["win"])

        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Menu e schermata iniziale sono pannelli dentro la finestra (Overlay): seguono il
        # tema esattamente come ogni altro elemento, senza finestre di sistema a parte.
        self.overlay = Gtk.Overlay()
        self.add(self.overlay)
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.root.set_name("root")
        self.overlay.add(self.root)
        self.scrim = Gtk.EventBox()          # strato trasparente: un clic fuori chiude il menu
        self.scrim.set_visible_window(False)
        self.scrim.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.scrim.connect("button-press-event", self.on_scrim_click)
        self.scrim.set_no_show_all(True)
        self.overlay.add_overlay(self.scrim)
        self.overlay.set_overlay_pass_through(self.scrim, False)
        self.body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.root.pack_start(self.body, True, True, 0)

        self.build_left_pane()
        self.build_right_pane()

        # Testo
        self.buf = GtkSource.Buffer()
        self.buf.set_max_undo_levels(-1)
        self.view = GtkSource.View.new_with_buffer(self.buf)
        self.view.set_name("editor")
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_top_margin(48)
        self.view.set_bottom_margin(120)
        self.view.add_events(Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.view.connect("scroll-event", self.on_scroll)
        self.view.connect("button-press-event", self.on_reference_event)
        self.view.connect("button-release-event", self.on_reference_event)
        self.editor_sw = Gtk.ScrolledWindow()
        self.editor_sw.add(self.view)

        # Tre colonne affiancate, senza maniglie né divisori: tutto sullo stesso piano
        self.body.pack_start(self.left_pane, False, False, 0)
        self.body.pack_start(self.editor_sw, True, True, 0)
        self.body.pack_start(self.right_pane, False, False, 0)
        self.root.connect("size-allocate", self.schedule_fit)

        b = self.buf
        self.t_h = [b.create_tag(f"h{i}", weight=Pango.Weight.BOLD, scale=s)
                    for i, s in ((1, 1.6), (2, 1.35), (3, 1.15), (4, 1.1), (5, 1.05), (6, 1.0))]
        self.t_mark = b.create_tag("mark")
        self.tags = {
            "bold": b.create_tag("bold", weight=Pango.Weight.BOLD),
            "ital": b.create_tag("ital", style=Pango.Style.ITALIC),
            "footnote": b.create_tag("footnote", rise=4000, scale=0.8),
            "strike": b.create_tag("strike", strikethrough=True),
            "underline": b.create_tag("underline", underline=Pango.Underline.SINGLE),
            "code": b.create_tag("code", family=CODE_FAMILY),
            "quote": b.create_tag("quote"),
            "list": b.create_tag("list"),
            "linktext": b.create_tag("linktext"),
            "linkurl": b.create_tag("linkurl"),
        }
        self.md_tags = self.t_h + [self.t_mark] + list(self.tags.values())
        self.t_hidden = b.create_tag("preview-hidden", invisible=True)
        self._preview_lines = []
        self._preview_active = set()
        self._preview_idle = 0
        b.connect("mark-set", self.preview_mark_set)
        self.t_find = b.create_tag("find")   # creato per ultimo: ha la precedenza
        b.connect("begin-user-action", self.begin_note_action)
        b.connect("delete-range", self.record_note_deletion)
        b.connect("undo", self.before_note_undo)
        b.connect_after("undo", self.after_note_undo)
        b.connect("redo", self.before_note_undo)
        b.connect_after("redo", self.after_note_undo)
        b.connect("changed", self.on_changed)
        b.connect("modified-changed", lambda *_: self.update_title())

        self.build_bottom_bar()
        self.build_splash()
        self.build_note_editor()

        self.connect("key-press-event", self.on_key)
        # Un acceleratore GTK ha precedenza sulle associazioni di GtkSourceView.
        accelerators = Gtk.AccelGroup()
        accelerators.connect(Gdk.KEY_n, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK,
                             Gtk.AccelFlags.VISIBLE, self.activate_note_shortcut)
        self.add_accel_group(accelerators)
        self.connect("delete-event", self.on_delete)

        if self.cfg["sound"]:
            if self.typewriter.player:
                self.typewriter.prepare()
            else:
                self.cfg["sound"] = False
        self.apply_style()
        self.refresh()

    # --- Costruzione -----------------------------------------------------------

    def button(self, label, tip, cb):
        btn = Gtk.Button(label=label) if label else Gtk.Button()
        btn.set_tooltip_text(tip)
        btn.set_can_focus(False)
        btn.set_focus_on_click(False)
        btn.connect("clicked", lambda *_: cb())
        return btn

    def icon_button(self, icons, fallback, tip, cb):
        btn = self.button("", tip, cb)
        icon_theme = Gtk.IconTheme.get_default()
        name = next((i for i in icons if icon_theme.has_icon(i)), None)
        if name:
            btn.set_image(Gtk.Image.new_from_icon_name(name, Gtk.IconSize.MENU))
            btn.set_always_show_image(True)
        else:
            btn.set_label(fallback)
        return btn

    def glyph_button(self, glyph, tip, cb):
        btn = self.button(glyph, tip, cb)
        btn.get_style_context().add_class("ico")
        return btn

    @staticmethod
    def flag(btn, on):
        ctx = btn.get_style_context()
        (ctx.add_class if on else ctx.remove_class)("on")

    @staticmethod
    def small_heading(text):
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<small><b>{GLib.markup_escape_text(text)}</b></small>")
        return label

    @staticmethod
    def pane_title(text):
        label = Gtk.Label(xalign=0)
        label.set_name("panetitle")
        label.set_markup(f'<span letter_spacing="2000">{GLib.markup_escape_text(text)}</span>')
        label.set_margin_start(14)
        label.set_margin_top(18)
        label.set_margin_bottom(6)
        return label

    def make_menu(self, content):
        """Pannello a comparsa dentro la finestra: segue il tema come ogni altro elemento."""
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        menu.set_name("pop")
        menu.pack_start(content, True, True, 0)
        content.show_all()
        menu.set_no_show_all(True)
        self.overlay.add_overlay(menu)
        self.overlay.set_overlay_pass_through(menu, False)
        return menu

    def open_menu(self, menu, anchor, side):
        """Apre il menu sopra il pulsante `anchor`, allineato a sinistra, a destra o al centro."""
        if self._menu is menu:
            self.close_menu()
            return
        self.close_menu()
        total_w = self.overlay.get_allocated_width()
        total_h = self.overlay.get_allocated_height()
        a = anchor.get_allocation()
        menu.set_valign(Gtk.Align.END)
        menu.set_margin_bottom(max(8, total_h - a.y + 8))
        menu.set_margin_start(0)
        menu.set_margin_end(0)
        if side == "start":
            menu.set_halign(Gtk.Align.START)
            menu.set_margin_start(max(8, a.x - 4))
        elif side == "end":
            menu.set_halign(Gtk.Align.END)
            menu.set_margin_end(max(8, total_w - a.x - a.width - 4))
        else:
            menu.set_halign(Gtk.Align.CENTER)
        self._menu = menu
        self.scrim.show()
        menu.show()

    def close_menu(self):
        if self._menu is None:
            return
        self._menu.hide()
        self.scrim.hide()
        self._menu = None
        self.view.grab_focus()

    def on_scrim_click(self, *_):
        self.close_menu()
        return True

    @staticmethod
    def text_column(attr, col_index, weight_col=None):
        """Colonna di testo con un margine vuoto a destra."""
        cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, xpad=6, ypad=3)
        gap = Gtk.CellRendererText()
        gap.set_fixed_size(RIGHT_GAP, 1)
        col = Gtk.TreeViewColumn()
        col.pack_start(cell, True)
        col.pack_start(gap, False)
        col.add_attribute(cell, attr, col_index)
        if weight_col is not None:
            col.add_attribute(cell, "weight", weight_col)
        return col

    def build_left_pane(self):
        """Barra laterale sinistra: ricerca in alto, sotto l'indice (o i risultati)."""
        self.left_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.left_pane.set_name("leftpane")

        self.search = Gtk.SearchEntry()
        self.search.set_name("search")
        self.search.set_width_chars(1)
        self.search.set_placeholder_text("Cerca nel testo")
        self.search.connect("search-changed", lambda *_: self.run_search())
        self.search.connect("key-press-event", self.on_search_key)
        self.find_info = Gtk.Label(label="", xalign=0)
        self.find_info.set_name("findinfo")
        self.find_info.set_margin_start(14)
        self.find_info.set_margin_bottom(6)
        self.find_info.set_no_show_all(True)

        # indice ad albero: i livelli si chiudono con la freccia
        self.store = Gtk.TreeStore(str, int, int, int, int)  # titolo, riga, indice, peso, livello
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_name("sidebar")
        self.tree.set_headers_visible(False)
        self.tree.set_enable_search(False)
        self.tree.set_activate_on_single_click(True)
        col = self.text_column("text", 0, 3)
        col.set_cell_data_func(col.get_cells()[0], self.outline_cell_data)
        self.tree.append_column(col)
        self.tree.connect("row-activated", self.on_outline_row)
        self.tree.connect("row-collapsed", self.on_outline_toggle, True)
        self.tree.connect("row-expanded", self.on_outline_toggle, False)
        outline_sw = Gtk.ScrolledWindow()
        outline_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        outline_sw.add(self.tree)
        self.outline_sw = outline_sw

        # risultati della ricerca: ogni voce mostra più righe di contesto
        self.results = Gtk.ListBox()
        self.results.set_name("results")
        self.results.set_selection_mode(Gtk.SelectionMode.NONE)
        self.results.set_activate_on_single_click(True)
        self.results.connect("row-activated", self.on_result_row)
        results_sw = Gtk.ScrolledWindow()
        results_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        results_sw.add(self.results)

        empty = Gtk.Label(label="Nessun titolo.\nUsa # per crearne uno.")
        empty.set_name("emptyhint")
        empty.set_justify(Gtk.Justification.CENTER)
        empty.set_valign(Gtk.Align.START)
        empty.set_margin_top(28)

        self.stack = Gtk.Stack()
        self.stack.add_named(outline_sw, "outline")
        self.stack.add_named(results_sw, "results")
        self.stack.add_named(empty, "empty")
        self.left_pane.pack_start(self.pane_title("INDICE"), False, False, 0)
        self.left_pane.pack_start(self.search, False, False, 0)
        self.left_pane.pack_start(self.find_info, False, False, 0)
        self.left_pane.pack_start(self.stack, True, True, 0)

    def build_right_pane(self):
        """Barra laterale destra: appunti da riutilizzare in un secondo momento."""
        self.right_pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.right_pane.set_name("rightpane")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, homogeneous=True)
        row.set_margin_start(12)
        row.set_margin_end(12)
        row.set_margin_bottom(8)
        row.pack_start(self.button("Incolla", "Aggiungi il testo copiato negli appunti di sistema",
                                   self.note_from_clipboard), True, True, 0)
        row.pack_start(self.button("Selezione", "Aggiungi il testo selezionato nell'editor",
                                   self.note_from_selection), True, True, 0)

        self.notes_list = Gtk.ListBox()
        self.notes_list.set_name("notes")
        self.notes_list.set_selection_mode(Gtk.SelectionMode.NONE)
        hint = Gtk.Label(label="Nessun appunto.\nIncolla un brano o aggiungi\nla selezione.")
        hint.set_name("emptyhint")
        hint.set_justify(Gtk.Justification.CENTER)
        hint.set_margin_top(20)
        hint.show()
        self.notes_list.set_placeholder(hint)
        notes_sw = Gtk.ScrolledWindow()
        notes_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        notes_sw.add(self.notes_list)
        scratch_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scratch_page.pack_start(row, False, False, 0)
        scratch_page.pack_start(notes_sw, True, True, 0)
        self.footnote_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.footnote_list.set_border_width(12)
        footnote_sw = Gtk.ScrolledWindow()
        footnote_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        footnote_sw.add(self.footnote_list)
        self.right_stack = Gtk.Stack()
        self.right_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.right_stack.set_transition_duration(120)
        self.right_stack.add_titled(scratch_page, "scratch", "Appunti")
        self.right_stack.add_titled(footnote_sw, "footnotes", "Note")
        self.right_stack.show_all()
        self.right_stack.set_visible_child_name(self.cfg["right_page"])
        self.right_stack.connect("notify::visible-child-name", self.remember_right_page)
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.right_stack)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.set_margin_top(18)
        switcher.set_margin_bottom(12)
        self.right_pane.pack_start(switcher, False, False, 0)
        self.right_pane.pack_start(self.right_stack, True, True, 0)
        self.rebuild_notes()

    def remember_right_page(self, stack, _property):
        self.cfg["right_page"] = stack.get_visible_child_name()

    def build_bottom_bar(self):
        self.goal = Gtk.ProgressBar()
        self.goal.set_name("goal")
        self.goal.set_no_show_all(True)
        self.root.pack_start(self.goal, False, False, 0)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.set_name("bar")
        self.root.pack_start(bar, False, False, 0)

        # a sinistra: barra laterale e Inserisci
        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.side_btn = self.icon_button(("sidebar-show-symbolic", "view-list-symbolic"), "☰",
                                         "Mostra o nascondi l'indice (F9)", self.toggle_sidebar)
        self.format_btn = self.glyph_button("+", "Formatta il testo selezionato o il paragrafo", self.show_format)
        self.insert_btn = self.button("ASCII", "Inserisci ASCII art (F8)", self.show_insert)
        left.pack_start(self.side_btn, False, False, 0)
        left.pack_start(self.format_btn, False, False, 0)
        self.info_btn = self.glyph_button("i", "Istruzioni per il markdown (F1)", self.show_help)
        left.pack_start(self.info_btn, False, False, 0)
        left.pack_start(self.insert_btn, False, False, 0)
        bar.pack_start(left, False, False, 0)

        # al centro: ora e conteggio (un clic sul conteggio imposta l'obiettivo di parole)
        center = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.clock = Gtk.Label(label="")
        if SHOW_CLOCK:
            center.pack_start(self.clock, False, False, 0)
            self.tick()
            GLib.timeout_add_seconds(15, self.tick)
        self.counts_btn = self.button("", "Imposta un obiettivo di parole", self.show_goal)
        center.pack_start(self.counts_btn, False, False, 0)
        bar.set_center_widget(center)

        # a destra: temi, colori, suoni, ingranaggio, appunti, istruzioni
        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.pack_end(right, False, False, 0)

        def add(widget, gap=0):
            widget.set_margin_start(gap)
            right.pack_start(widget, False, False, 0)
            return widget

        self.theme_btn = add(self.button("t", "Scegli tema", self.show_themes))
        self.theme_btn.get_style_context().add_class("sq")
        self.color_btn = add(self.glyph_button("✱", "Colora gli elementi del markdown",
                                               self.toggle_colors), 12)
        self.sound_btn = add(self.glyph_button("T", "Suono di macchina da scrivere",
                                               self.toggle_sound))
        self.gear_btn = add(self.icon_button(
            ("emblem-system-symbolic", "preferences-system-symbolic"), "⚙",
            "Carattere, grandezza, larghezza e salvataggio", self.show_settings), 12)
        self.notes_btn = add(self.icon_button(
            ("sidebar-show-right-symbolic", "view-dual-symbolic"), "▥",
            "Mostra o nascondi Appunti e Note (F10)", self.toggle_notes))

        self.theme_menu = self.build_theme_menu()
        self.format_menu = self.build_format_menu()
        self.insert_menu = self.build_insert_menu()
        self.settings_menu = self.build_settings_menu()
        self.help_menu = self.build_help_menu()
        self.goal_menu = self.build_goal_menu()

    def tick(self):
        self.clock.set_text(time.strftime("%H:%M"))
        return True

    def build_splash(self):
        """Biblioteca iniziale e invito alla scrittura, nello stesso spazio dell'editor."""
        self.splash = Gtk.EventBox()
        self.splash.set_name("splash")
        self.splash.set_can_focus(True)
        self.splash.set_no_show_all(True)
        self.splash.set_visible_window(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.home_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=32)
        self.home_content.set_halign(Gtk.Align.CENTER)
        self.home_content.set_valign(Gtk.Align.CENTER)
        self.home_content.set_margin_top(56)
        self.home_content.set_margin_bottom(56)
        library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        library.set_name("home-library")
        folder_row = Gtk.Box(spacing=12)
        folder_row.set_margin_start(8)
        folder_row.set_margin_end(8)
        folder_row.pack_start(Gtk.Label(label="Cartella:", xalign=0), False, False, 0)
        self.home_folder = Gtk.Label(xalign=0, hexpand=True)
        self.home_folder.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        folder_row.pack_start(self.home_folder, True, True, 0)
        self.home_choose_btn = self.home_button("Scegli", "Scegli cartella (Ctrl+Shift+O)", self.choose_home_folder)
        folder_row.pack_start(self.home_choose_btn, False, False, 0)
        library.pack_start(folder_row, False, False, 0)
        self.home_status = Gtk.Label(xalign=0)
        self.home_status.set_line_wrap(True)
        library.pack_start(self.home_status, False, False, 0)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.get_style_context().add_class("home-rule")
        library.pack_start(separator, False, False, 0)
        self.home_columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=48, homogeneous=True)
        self.home_heading_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
        self.home_recent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.home_files = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for title, attribute, content in (("Recenti", "home_recent_count", self.home_recent),
                                           ("Tutti i file", "home_files_count", self.home_files)):
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            heading = Gtk.Box(spacing=12)
            self.home_heading_group.add_widget(heading)
            heading.set_margin_start(8)
            heading.set_margin_end(8)
            label = Gtk.Label(xalign=0)
            label.set_markup(f'<span letter_spacing="1600">{title.upper()}</span>')
            label.get_style_context().add_class("home-heading")
            heading.pack_start(label, True, True, 0)
            count = Gtk.Label()
            count.get_style_context().add_class("home-count")
            setattr(self, attribute, count)
            heading.pack_end(count, False, False, 0)
            section.pack_start(heading, False, False, 0)
            section.pack_start(content, False, False, 0)
            section.set_valign(Gtk.Align.START)
            self.home_columns.pack_start(section, True, True, 0)
        library.pack_start(self.home_columns, False, False, 0)
        prompt = Gtk.EventBox()
        prompt.set_visible_window(False)
        prompt.connect("button-press-event", self.on_splash_click)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        box.set_halign(Gtk.Align.CENTER)
        for text, cls in (("premi un", None), ("TASTO", "key"), ("...", "dots")):
            label = Gtk.Label(label=text)
            if cls:
                label.get_style_context().add_class(cls)
            if cls == "dots":
                self.splash_dots = label
            box.pack_start(label, False, False, 0)
        prompt.add(box)
        self.home_content.pack_start(prompt, False, False, 0)
        self.home_content.pack_start(library, False, False, 0)
        shortcuts = Gtk.Label(label="Ctrl+O  Apri     ·     Ctrl+N  Nuovo     ·     Ctrl+Q  Chiudi")
        shortcuts.get_style_context().add_class("home-shortcuts")
        shortcuts.set_line_wrap(True)
        shortcuts.set_justify(Gtk.Justification.CENTER)
        self.home_content.pack_start(shortcuts, False, False, 0)
        self.home_content.show_all()
        scroll.add(self.home_content)
        scroll.show()
        self.splash.add(scroll)
        self.overlay.add_overlay(self.splash)
        self.overlay.set_overlay_pass_through(self.splash, False)
        self.overlay.connect("size-allocate", self.resize_home)

    def home_button(self, label, tooltip, callback):
        button = self.button(label, tooltip, callback)
        button.set_can_focus(True)
        button.set_focus_on_click(True)
        return button

    def resize_home(self, _widget=None, allocation=None):
        allocation = allocation or self.overlay.get_allocation()
        width = max(1, min(840, allocation.width - 64))
        orientation = Gtk.Orientation.HORIZONTAL if width >= 640 else Gtk.Orientation.VERTICAL
        self.home_columns.set_orientation(orientation)
        self.home_columns.set_spacing(48 if orientation == Gtk.Orientation.HORIZONTAL else 28)
        self.home_columns.set_homogeneous(orientation == Gtk.Orientation.HORIZONTAL)
        if self.home_content.get_size_request()[0] != width:
            self.home_content.set_size_request(width, -1)

    def ensure_home_folder(self):
        if self.cfg["folder"]:
            return
        documents = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS)
        folder = Path(documents or os.path.join(GLib.get_home_dir(), "Documenti")) / "Tasto"
        self.cfg["folder"] = str(folder)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._home_warning = "Scegli una cartella accessibile. " + str(error)

    def refresh_home(self, reset=False):
        self.ensure_home_folder()
        if reset:
            self._home_limit = 7
        folder = self.cfg["folder"]
        self.home_folder.set_text(folder)
        self.home_folder.set_tooltip_text(folder)
        for container in (self.home_recent, self.home_files):
            for child in container.get_children():
                container.remove(child)
        message = self._home_warning
        try:
            files = markdown_files(folder)
            recent = recent_in_folder(folder, self.cfg["recent_files"])
        except (OSError, ValueError) as error:
            files, recent = [], []
            message = "Cartella non disponibile: " + str(error)
        self.home_recent_count.set_text(str(len(recent)))
        self.home_files_count.set_text(f"{min(self._home_limit, len(files))} / {len(files)}")
        self.home_status.set_text(message)
        self.home_status.set_visible(bool(message))
        for container, paths, empty in ((self.home_recent, recent, "Nessun file recente in questa cartella."),
                                        (self.home_files, files[:self._home_limit], "Nessun file Markdown in questa cartella.")):
            if not paths:
                label = Gtk.Label(label=empty, xalign=0)
                label.set_line_wrap(True)
                label.get_style_context().add_class("home-empty")
                label.set_margin_start(8)
                label.set_margin_end(8)
                container.pack_start(label, False, False, 0)
            for path in paths:
                button = self.home_button(path.name, str(path), lambda path=path: self.open_home_file(path))
                button.get_style_context().add_class("home-file")
                button.get_child().set_xalign(0)
                button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
                button.get_child().set_max_width_chars(38)
                container.pack_start(button, False, False, 0)
            container.show_all()
        if len(files) > self._home_limit:
            more = self.home_button("+", "Mostra altri 7 file", self.more_home_files)
            more.set_halign(Gtk.Align.START)
            more.get_style_context().add_class("home-more")
            self.home_files.pack_start(more, False, False, 0)
            more.show()

    def more_home_files(self):
        self._home_limit += 7
        self.refresh_home()

    def choose_home_folder(self):
        chooser = Gtk.FileChooserNative.new("Scegli la cartella di Tasto", self,
                                           Gtk.FileChooserAction.SELECT_FOLDER, "Scegli", "Annulla")
        if os.path.isdir(self.cfg["folder"]):
            chooser.set_current_folder(self.cfg["folder"])
        if chooser.run() == Gtk.ResponseType.ACCEPT:
            self.set_home_folder(chooser.get_filename())
        chooser.destroy()

    def set_home_folder(self, folder):
        self.cfg["folder"] = os.path.abspath(os.path.expanduser(folder))
        self._home_warning = "" if save_json(CONFIG_PATH, self.cfg) else "Impossibile salvare la cartella nelle preferenze."
        self.refresh_home(reset=True)

    def remember_document(self, path):
        self.cfg["recent_files"] = remember_file(self.cfg["recent_files"], path)
        if not save_json(CONFIG_PATH, self.cfg):
            self._home_warning = "Impossibile salvare i file recenti nelle preferenze."
        if self.splash.get_visible():
            self.refresh_home()

    def open_home_file(self, path):
        if not self.confirm():
            return
        unnamed = self.path is None
        if self.open_path(path) and unnamed:
            self.remove_draft()

    def show_home(self):
        self.finish_note_action()
        self.close_menu()
        if not self.splash.get_visible():
            self._home_viewport = self.document_viewport()
        self.refresh_home(reset=True)
        self.resize_home()
        self.root.set_sensitive(False)
        self.splash.show()
        self.splash.grab_focus()
        if not self._splash_timer:
            self._splash_timer = GLib.timeout_add(650, self.blink_splash)

    def blink_splash(self):
        if not self.splash.get_visible():
            self._splash_timer = 0
            return False
        self.splash_dots.set_opacity(1.0 if self.splash_dots.get_opacity() < 1.0 else 0.15)
        return True

    def on_splash_click(self, *_):
        self.dismiss_splash()
        return True

    def dismiss_splash(self):
        if self.splash.get_visible():
            self.splash.hide()
            if self._splash_timer:
                GLib.source_remove(self._splash_timer)
                self._splash_timer = 0
            self.root.set_sensitive(True)
            self.view.grab_focus()
            if self._home_viewport is not None:
                self.restore_document_viewport(self._home_viewport)
                self._home_viewport = None

    def start(self, path=None):
        self.show_all()
        self.left_pane.set_visible(self.cfg["sidebar"])
        self.right_pane.set_visible(self.cfg["notes"])
        self.update_goal()
        if path:
            if not self.open_path(path):
                self.show_home()
        else:
            self.restore_draft()
            self.show_home()

    # --- Menu a comparsa (seguono il tema) ----------------------------------------------

    def build_theme_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)
        box.pack_start(self.small_heading("Tema"), False, False, 0)
        self.theme_btns = {}
        for name in THEME_ORDER:
            button = self.button("t  ·  " + THEMES[name]["label"],
                                 "Seleziona " + THEMES[name]["label"],
                                 lambda n=name: self.choose_theme(n))
            button.get_style_context().add_class("sq")
            button.get_style_context().add_class("sq-" + name)
            box.pack_start(button, False, False, 0)
            self.theme_btns[name] = button
        return self.make_menu(box)

    def show_themes(self):
        self.open_menu(self.theme_menu, self.theme_btn, "end")

    def choose_theme(self, name):
        self.set_theme(name)
        self.close_menu()

    def build_format_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)
        box.pack_start(self.small_heading("Formato"), False, False, 0)
        for label, command in (("B  ·  Grassetto   Ctrl+B", "bold"), ("I  ·  Corsivo   Ctrl+I", "italic"),
                               ("U  ·  Sottolineato   Ctrl+U", "underline"), ("S  ·  Barrato   Ctrl+Shift+X", "strike"),
                               ("•  ·  Elenco puntato   Ctrl+Shift+7", "bullet"), ("1. ·  Elenco numerato   Ctrl+Shift+8", "number"),
                               ("→  ·  Aumenta rientro   Ctrl+]", "indent"), ("←  ·  Riduci rientro   Ctrl+[", "outdent")):
            box.pack_start(self.button(label, label, lambda c=command: self.format_text(c)), False, False, 0)
        box.pack_start(self.button("ⁿ  ·  Aggiungi nota   Ctrl+Shift+N",
                                   "Aggiungi nota a margine", self.add_margin_note), False, False, 0)
        return self.make_menu(box)

    def show_format(self):
        self.open_menu(self.format_menu, self.format_btn, "start")

    def format_text(self, command):
        bounds = self.buf.get_selection_bounds()
        if bounds:
            start, end = (it.get_offset() for it in bounds)
        else:
            start = end = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
        a, b, replacement, sel_a, sel_b = format_edit(self.get_text(), start, end, command)
        self.buf.begin_user_action()
        try:
            self.buf.delete(self.buf.get_iter_at_offset(a), self.buf.get_iter_at_offset(b))
            self.buf.insert(self.buf.get_iter_at_offset(a), replacement)
            self.buf.select_range(self.buf.get_iter_at_offset(a + sel_a),
                                  self.buf.get_iter_at_offset(a + sel_b))
        finally:
            self.buf.end_user_action()
        self.close_menu()
        self.view.grab_focus()

    def build_insert_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_border_width(8)
        for category, items in ASCII_ART:
            head = self.small_heading(category)
            head.set_margin_top(10)
            head.set_margin_start(8)
            box.pack_start(head, False, False, 0)
            for name, art in items:
                btn = Gtk.Button()
                btn.get_style_context().add_class("item")
                inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                title = Gtk.Label(xalign=0)
                title.set_markup(f"<small>{GLib.markup_escape_text(name)}</small>")
                title.get_style_context().add_class("hint")
                preview = Gtk.Label(xalign=0)
                preview.set_markup(f"<tt>{GLib.markup_escape_text(art)}</tt>")
                inner.pack_start(title, False, False, 0)
                inner.pack_start(preview, False, False, 0)
                btn.add(inner)
                btn.connect("clicked", lambda _b, a=art: self.insert_art(a))
                box.pack_start(btn, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_width(400)
        sw.set_propagate_natural_height(True)
        sw.add(box)
        self.insert_sw = sw
        return self.make_menu(sw)

    def build_settings_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(14)

        box.pack_start(self.small_heading("Carattere"), False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, homogeneous=True)
        self.font_btns = []
        for i, (name, _, _) in enumerate(FONTS):
            btn = Gtk.Button(label=name)
            btn.set_can_focus(False)
            btn.connect("clicked", lambda *_, i=i: self.set_font(i))
            row.pack_start(btn, True, True, 0)
            self.font_btns.append(btn)
        box.pack_start(row, False, False, 0)

        steppers = (("Grandezza", "size_label", lambda: self.change_size(-1),
                     lambda: self.change_size(1)),
                    ("Larghezza", "width_label", lambda: self.change_width(-1),
                     lambda: self.change_width(1)))
        for title, attr, minus, plus in steppers:
            heading = self.small_heading(title)
            heading.set_margin_top(8)
            box.pack_start(heading, False, False, 0)
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            b_minus = Gtk.Button(label="−")
            b_plus = Gtk.Button(label="+")
            for btn, f in ((b_minus, minus), (b_plus, plus)):
                btn.set_can_focus(False)
                btn.connect("clicked", lambda *_, f=f: f())
            label = Gtk.Label(label="", width_chars=8)
            setattr(self, attr, label)
            line.pack_start(b_minus, False, False, 0)
            line.pack_start(label, True, True, 0)
            line.pack_start(b_plus, False, False, 0)
            box.pack_start(line, False, False, 0)

        self.autosave_btn = Gtk.Button(label="Salvataggio automatico")
        self.autosave_btn.set_can_focus(False)
        self.autosave_btn.set_margin_top(12)
        self.autosave_btn.set_tooltip_text("Salva il file da solo dopo le modifiche; "
                                           "il testo senza nome diventa una bozza ripristinata all'avvio")
        self.autosave_btn.connect("clicked", lambda *_: self.toggle_autosave())
        box.pack_start(self.autosave_btn, False, False, 0)
        self.splash_btn = Gtk.Button(label="Schermata iniziale")
        self.splash_btn.set_can_focus(False)
        self.splash_btn.connect("clicked", lambda *_: self.show_home())
        box.pack_start(self.splash_btn, False, False, 0)
        box.set_size_request(280, -1)
        return self.make_menu(box)

    def build_help_menu(self):
        grid = Gtk.Grid(column_spacing=18, row_spacing=4)
        grid.set_border_width(14)
        for r, (syntax, meaning) in enumerate(HELP):
            a = Gtk.Label(xalign=0)
            a.set_markup(f"<tt>{GLib.markup_escape_text(syntax)}</tt>")
            grid.attach(a, 0, r, 1, 1)
            grid.attach(Gtk.Label(label=meaning, xalign=0), 1, r, 1, 1)
        note = Gtk.Label(label=HELP_NOTE, xalign=0)
        note.get_style_context().add_class("hint")
        note.set_margin_top(10)
        grid.attach(note, 0, len(HELP), 2, 1)
        return self.make_menu(grid)

    def build_goal_menu(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(14)
        box.pack_start(self.small_heading("Obiettivo di parole"), False, False, 0)
        self.goal_spin = Gtk.SpinButton.new_with_range(0, 200000, 50)
        self.goal_spin.set_numeric(True)
        self.goal_spin.set_value(self.cfg["target"])
        self.goal_spin.connect("value-changed", self.on_goal_changed)
        box.pack_start(self.goal_spin, False, False, 0)
        hint = Gtk.Label(label="0 per togliere l'obiettivo", xalign=0)
        hint.get_style_context().add_class("hint")
        box.pack_start(hint, False, False, 0)
        return self.make_menu(box)

    def show_insert(self):
        a = self.insert_btn.get_allocation()
        self.insert_sw.set_max_content_height(max(160, min(460, a.y - 40)))
        self.open_menu(self.insert_menu, self.insert_btn, "start")

    def show_settings(self):
        self.open_menu(self.settings_menu, self.gear_btn, "end")

    def show_help(self):
        self.open_menu(self.help_menu, self.info_btn, "start")

    def show_goal(self):
        self.open_menu(self.goal_menu, self.counts_btn, "center")

    def insert_art(self, art):
        self.close_menu()
        if "\n" in art:
            art = "```\n" + art + "\n```"
        buf = self.buf
        buf.begin_user_action()
        buf.delete_selection(True, True)
        prefix = "" if buf.get_iter_at_mark(buf.get_insert()).starts_line() else "\n"
        buf.insert_at_cursor(prefix + art + "\n")
        buf.end_user_action()
        self.view.scroll_to_mark(buf.get_insert(), 0.1, False, 0.0, 0.0)
        self.view.grab_focus()

    # --- Aspetto -----------------------------------------------------------------

    @staticmethod
    def paint(tag, color):
        if color:
            tag.set_property("foreground", color)
        else:
            tag.set_property("foreground-set", False)

    def apply_style(self):
        c = self.cfg
        th = THEMES[c["theme"]]
        _, font_css, font_scale = FONTS[c["font"]]
        eff = c["size"] * font_scale        # grandezza effettiva, compensata per carattere
        values = dict(th, font=font_css, size=f"{eff:.1f}", ui=f"{UI_SIZE * font_scale:.1f}",
                      uifont=font_css, accent=th["syn"]["head"])
        css = CSS
        for key, val in values.items():
            if isinstance(val, str):
                css = css.replace(f"@{key}@", val)
        try:
            self.provider.load_from_data((css + extra_css()).encode("utf-8"))
        except GLib.Error as e:
            print("CSS non valido:", e, file=sys.stderr)

        em = eff * 96 / 72
        self.view.set_pixels_below_lines(round(em * PARAGRAPH_SPACE))
        self.view.set_pixels_inside_wrap(round(em * LINE_SPACE))
        for tag in self.t_h:
            tag.set_property("pixels-above-lines", round(em * 0.6))
        # il codice (e l'ASCII art) resta alla stessa grandezza visiva del mono
        self.tags["code"].set_property("scale", FONTS[0][2] / font_scale)

        # Colori del markdown: attivi solo con l'opzione "Colori"
        syn = th["syn"] if c["colors"] else {}
        self.t_mark.set_property("foreground", th["dim"])
        self.t_find.set_property("background", th["find"])
        for tag in self.t_h:
            self.paint(tag, syn.get("head"))
        for key, color in (("bold", "bold"), ("ital", "ital"), ("code", "code"),
                           ("quote", "quote"), ("list", "list"), ("linktext", "link"),
                           ("strike", "bold"), ("underline", "ital"), ("footnote", "link")):
            self.paint(self.tags[key], syn.get(color))
        self.paint(self.tags["linkurl"], th["dim"] if c["colors"] else None)

        ctx = self.theme_btn.get_style_context()
        for name in THEME_ORDER:
            ctx.remove_class("sq-" + name)
        ctx.add_class("sq-" + c["theme"])
        self.theme_btn.set_tooltip_text("Tema: " + th["label"] + " · Scegli tema")
        for name, btn in self.theme_btns.items():
            self.flag(btn, name == c["theme"])
        self.flag(self.side_btn, c["sidebar"])
        self.flag(self.notes_btn, c["notes"])
        self.flag(self.color_btn, c["colors"])
        self.flag(self.sound_btn, c["sound"])
        self.sync_settings()
        self.tree.queue_draw()
        if self.search.get_text():
            self._results_key = None
            self.run_search()

    def sync_settings(self):
        c = self.cfg
        self.size_label.set_text(f"{c['size']} pt")
        self.width_label.set_text(f"{c['width']} px")
        for i, btn in enumerate(self.font_btns):
            self.flag(btn, i == c["font"])
        self.flag(self.autosave_btn, c["autosave"])

    def set_theme(self, name):
        self.cfg["theme"] = name
        self.apply_style()

    def set_font(self, index):
        self.cfg["font"] = index
        self.apply_style()

    def toggle_colors(self):
        self.cfg["colors"] = not self.cfg["colors"]
        self.apply_style()


    def toggle_autosave(self):
        self.cfg["autosave"] = not self.cfg["autosave"]
        self._autosave_failed = False
        self.sync_settings()
        if self.cfg["autosave"]:
            self.schedule_autosave()

    def toggle_sound(self):
        if not self.cfg["sound"]:
            if not self.typewriter.player:
                self.error("Per i suoni serve uno tra pw-play, paplay e aplay "
                           "(pacchetti pipewire-bin, pulseaudio-utils o alsa-utils).")
                return
            self.typewriter.prepare()
        self.cfg["sound"] = not self.cfg["sound"]
        self.apply_style()

    def change_size(self, delta):
        self.cfg["size"] = max(SIZE_MIN, min(SIZE_MAX, self.cfg["size"] + delta))
        self.apply_style()

    def change_width(self, direction):
        w = self.cfg["width"] + direction * WIDTH_STEP
        self.cfg["width"] = max(WIDTH_MIN, min(WIDTH_MAX, w))
        self.sync_settings()
        self.schedule_fit()

    def toggle_sidebar(self):
        show = not self.left_pane.get_visible()
        self.left_pane.set_visible(show)
        self.cfg["sidebar"] = show
        self.flag(self.side_btn, show)
        self.fit()

    def toggle_notes(self):
        show = not self.right_pane.get_visible()
        self.right_pane.set_visible(show)
        self.cfg["notes"] = show
        self.flag(self.notes_btn, show)
        self.fit()

    # --- Larghezze fisse e colonna di testo sempre al centro -----------------------------

    def schedule_fit(self, *_):
        if not self._fit_pending:
            self._fit_pending = True
            GLib.idle_add(self.fit)

    def side_width(self, total):
        """Larghezza fissa delle barre laterali: proporzionale alla finestra, ma mai
        più larga dello spazio che lascia libero la colonna di testo."""
        side = max(SIDE_MIN, min(SIDE_MAX, round(total * SIDE_RATIO)))
        room = (total - self.cfg["width"]) // 2 - SIDE_GAP
        if room >= SIDE_MIN:
            side = min(side, room)
        return side

    def fit(self):
        """Imposta la larghezza delle barre e centra la colonna di testo nella finestra."""
        self._fit_pending = False
        total = self.root.get_allocated_width()
        if total <= 1:
            return False
        side = self.side_width(total)
        if side != self._side:
            self._side = side
            self.left_pane.set_size_request(side, -1)
            self.right_pane.set_size_request(side, -1)
        left_w = side if self.left_pane.get_visible() else 0
        right_w = side if self.right_pane.get_visible() else 0
        col = self.cfg["width"]
        eff = min(col, total - 2 * (max(left_w, right_w) + SIDE_GAP))
        if eff >= TEXT_MIN:
            left = (total - eff) // 2 - left_w
            right = (total - eff) // 2 - right_w
        else:                       # finestra troppo stretta: centra nello spazio rimasto
            area = total - left_w - right_w
            left = right = max(24, (area - min(col, area - 48)) // 2)
        if (left, right) != self._margins:
            self._margins = (left, right)
            self.view.set_left_margin(left)
            self.view.set_right_margin(right)
        return False

    # --- Stile markdown, indice e conteggi -----------------------------------------

    def begin_note_action(self, buffer):
        if self._mutating_notes or self._undoing_notes or self._holding_note_action:
            return
        self._note_action_before = self.get_text()
        self._deleted_note_refs = set()
        self._deleted_note_defs = set()
        self._holding_note_action = True
        # Mantiene aperta l'azione nativa fino alla sincronizzazione al prossimo idle.
        buffer.begin_user_action()
        self._note_sync_source = GLib.idle_add(self.finish_note_action)

    def record_note_deletion(self, _buffer, start, end):
        if not self._holding_note_action or self._mutating_notes or self._undoing_notes:
            return
        text = self.get_text()
        a, b = start.get_offset(), end.get_offset()
        self._deleted_note_refs.update(ref.number for ref in references(text) if a <= ref.start and ref.end <= b)
        self._deleted_note_defs.update(note.number for note in document_notes(text)
                                      if a <= note.start and note.start + len(text[note.start:note.end].rstrip('\r\n')) <= b)

    def finish_note_action(self):
        if self._note_sync_source:
            GLib.source_remove(self._note_sync_source)
            self._note_sync_source = 0
        if not self._holding_note_action:
            return False
        try:
            text = self.get_text()
            cursor = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
            normalized, cursor, _mapping = reconcile_notes(self._note_action_before, text, cursor,
                                                          self._deleted_note_refs, self._deleted_note_defs)
            if normalized != text:
                self.replace_document(normalized, cursor)
        finally:
            self._holding_note_action = False
            self.buf.end_user_action()
        return False

    def before_note_undo(self, *_):
        self.finish_note_action()
        self._undoing_notes = True

    def after_note_undo(self, *_):
        self._undoing_notes = False

    def on_reference_event(self, _widget, event):
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            self._reference_press = (event.x, event.y)
        elif event.type == Gdk.EventType.BUTTON_RELEASE and event.button == 1:
            press = getattr(self, "_reference_press", None)
            self._reference_press = None
            if press and abs(press[0] - event.x) < 5 and abs(press[1] - event.y) < 5:
                self.finish_note_action()
                window_type = self.view.get_window_type(event.window)
                x, y = self.view.window_to_buffer_coords(window_type, int(event.x), int(event.y))
                inside, iterator = self.view.get_iter_at_location(x, y)
                if not inside:
                    return False
                offset = iterator.get_offset()
                ref = next((ref for ref in references(self.get_text()) if ref.start <= offset < ref.end), None)
                if ref:
                    self.edit_margin_note(ref.number)
                    return True
        return False

    def on_changed(self, *_):
        self.schedule()
        self.schedule_autosave()

    def schedule(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(150, self.refresh)

    def refresh(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = 0
        start, end = self.buf.get_bounds()
        text = self.buf.get_text(start, end, True)
        heads = self.style_markdown(text)
        self.update_counts(text)
        self.refresh_margin_notes(text)
        self.update_outline(heads)
        if self.search.get_text():
            self.run_search(text)
        self.update_title()
        return False

    def tag_range(self, tag, line, a, b):
        if b > a:
            self.buf.apply_tag(tag,
                               self.buf.get_iter_at_line_offset(line, a),
                               self.buf.get_iter_at_line_offset(line, b))

    def preview_mark_set(self, _buffer, _iterator, mark):
        if mark.get_name() in ("insert", "selection_bound") and not self._preview_idle:
            self._preview_idle = GLib.idle_add(self.update_preview_selection)

    def preview_selection(self):
        bounds = self.buf.get_selection_bounds()
        if bounds:
            start, end = bounds
            last = end.get_line()
            if end.starts_line() and end.get_offset() > start.get_offset():
                last -= 1
            active = active_lines(self._preview_lines, start.get_line(), last)
            cursor = self.buf.get_iter_at_mark(self.buf.get_insert()).get_line()
            return active | active_lines(self._preview_lines, cursor, cursor)
        line = self.buf.get_iter_at_mark(self.buf.get_insert()).get_line()
        return active_lines(self._preview_lines, line, line)

    def update_preview_selection(self):
        self._preview_idle = 0
        # Le decorazioni precedenti hanno offset obsoleti dopo una modifica.
        if self._timer:
            return False
        active = self.preview_selection()
        for n in active ^ self._preview_active:
            if n >= len(self._preview_lines):
                continue
            line = self._preview_lines[n]
            start = self.buf.get_iter_at_line(n)
            end = start.copy()
            end.forward_to_line_end()
            self.buf.remove_tag(self.t_hidden, start, end)
            if n not in active:
                for a, b in line.hidden:
                    self.tag_range(self.t_hidden, n, a, b)
        self._preview_active = active
        return False

    def style_markdown(self, text):
        start, end = self.buf.get_bounds()
        for tag in self.md_tags + [self.t_hidden]:
            self.buf.remove_tag(tag, start, end)
        self._preview_lines = parse_preview(text)
        self._preview_active = self.preview_selection()
        heads = []
        for n, line in enumerate(self._preview_lines):
            if line.heading:
                # L'indice esistente mostra i primi tre livelli.
                if line.heading[0] <= 3:
                    heads.append(line.heading)
            for name, a, b in line.spans:
                tag = self.t_h[int(name[1:]) - 1] if name.startswith('h') and name[1:].isdigit() else self.tags[name]
                self.tag_range(tag, n, a, b)
            if QUOTE.match(line.text):
                self.tag_range(self.tags["quote"], n, 0, len(line.text))
            marker = LIST.match(line.text)
            if marker:
                self.tag_range(self.tags["list"], n, *marker.span(1))
            if n not in self._preview_active:
                for a, b in line.hidden:
                    self.tag_range(self.t_hidden, n, a, b)
        return heads

    def update_counts(self, text):
        self._chars = len(text) - text.count("\n")  # spazi inclusi, a capo esclusi
        self._words = len(WORD.findall(text))
        self.update_goal()

    def update_goal(self):
        target = self.cfg["target"]
        words = fmt(self._words) if not target else f"{fmt(self._words)} / {fmt(target)}"
        self.counts_btn.set_label(f"{fmt(self._chars)} caratteri · {words} parole")
        if target:
            self.goal.set_fraction(min(1.0, self._words / target))
        self.goal.set_visible(bool(target))

    def on_goal_changed(self, spin):
        self.cfg["target"] = int(spin.get_value())
        self.update_goal()

    @staticmethod
    def heading_keys(heads):
        seen, keys = {}, []
        for level, title, _ in heads:
            n = seen.get((level, title), 0)
            seen[(level, title)] = n + 1
            keys.append((level, title, n))
        return keys

    def show_left_page(self):
        if self.search.get_text():
            name = "results"
        else:
            name = "outline" if self._heads else "empty"
        self.stack.set_visible_child_name(name)

    def outline_cell_data(self, _col, cell, model, it, _data=None):
        if model[it][4] >= 3 and not self.tree.get_selection().iter_is_selected(it):
            # i titoli di terzo livello sono attenuati, tranne quando sono selezionati
            cell.set_property("foreground", THEMES[self.cfg["theme"]]["dim"])
        else:
            cell.set_property("foreground-set", False)

    def update_outline(self, heads):
        if heads == self._heads:
            return
        keys = self.heading_keys(heads)
        if self._heads is not None and [h[0] for h in heads] == [h[0] for h in self._heads]:
            collapsed = set(self.collapsed)          # stessa struttura: tiene lo stato
        else:                                        # struttura cambiata: riconosce per titolo
            old = {self._keys[i] for i in self.collapsed if i < len(self._keys)}
            collapsed = {i for i, k in enumerate(keys) if k in old}
        self._heads, self._keys, self.collapsed = heads, keys, collapsed

        adj = self.outline_sw.get_vadjustment()
        pos = adj.get_value()
        self._building = True
        self.store.clear()
        stack, rows = [], []
        for idx, (level, title, line) in enumerate(heads):
            while stack and stack[-1][0] >= level:
                stack.pop()
            it = self.store.append(stack[-1][1] if stack else None,
                                   [title, line, idx, 700 if level == 1 else 400, level])
            stack.append((level, it))
            rows.append(it)
        self.tree.expand_all()
        for idx in collapsed:
            if idx < len(rows):
                self.tree.collapse_row(self.store.get_path(rows[idx]))
        self._building = False
        GLib.idle_add(adj.set_value, pos)
        self.show_left_page()

    def on_outline_toggle(self, _tree, it, _path, is_collapsed):
        if self._building:
            return
        idx = self.store[it][2]
        (self.collapsed.add if is_collapsed else self.collapsed.discard)(idx)

    def on_outline_row(self, _tree, path, _col):
        line = self.store[path][1]
        self.buf.place_cursor(self.buf.get_iter_at_line(line))
        self.view.scroll_to_mark(self.buf.get_insert(), 0.0, True, 0.0, 0.15)
        self.view.grab_focus()

    def update_title(self):
        name = os.path.basename(self.path) if self.path else "Senza titolo"
        dot = "• " if self.buf.get_modified() else ""
        self.set_title(f"{dot}{name} — {APP}")

    # --- Ricerca ------------------------------------------------------------------------

    def focus_search(self):
        if not self.left_pane.get_visible():
            self.toggle_sidebar()
        sel = self.buf.get_selection_bounds()
        if sel:
            chosen = self.buf.get_text(sel[0], sel[1], False)
            if chosen and "\n" not in chosen:
                self.search.set_text(chosen)
        self.search.grab_focus()
        self.search.select_region(0, -1)

    def on_search_key(self, _w, e):
        if e.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            shift = bool(e.state & Gdk.ModifierType.SHIFT_MASK)
            self.goto_match(-1 if shift else 1)
            return True
        if e.keyval == Gdk.KEY_Escape:
            self.search.set_text("")
            self.view.grab_focus()
            return True
        return False

    def run_search(self, text=None):
        term = self.search.get_text()
        buf = self.buf
        start, end = buf.get_bounds()
        buf.remove_tag(self.t_find, start, end)
        self._matches = []
        if not term:
            self._results_key = None
            for row in self.results.get_children():
                self.results.remove(row)
            self.find_info.set_visible(False)
            self.show_left_page()
            return
        if text is None:
            text = buf.get_text(start, end, True)
        for m in re.finditer(re.escape(term), text, re.IGNORECASE):
            self._matches.append((m.start(), m.end()))
            if len(self._matches) >= MAX_RESULTS:
                break

        starts = [0] + [m.end() for m in re.finditer("\n", text)]

        def iter_at(offset):
            line = bisect.bisect_right(starts, offset) - 1
            return buf.get_iter_at_line_offset(line, offset - starts[line])

        for a, b in self._matches:
            buf.apply_tag(self.t_find, iter_at(a), iter_at(b))

        key = (term, tuple(self._matches), self.cfg["theme"])
        if key != self._results_key:                 # l'elenco si ricostruisce solo se cambia
            self._results_key = key
            for row in self.results.get_children():
                self.results.remove(row)
            esc = GLib.markup_escape_text
            find = THEMES[self.cfg["theme"]]["find"]

            def flat(s):
                return s.replace("\n", " ")

            for a, b in self._matches[:RESULT_ROWS]:
                line = bisect.bisect_right(starts, a) - 1
                lo, hi = max(0, a - CONTEXT_BEFORE), min(len(text), b + CONTEXT_AFTER)
                pre = ("…" if lo > 0 else "") + text[lo:a]
                post = text[b:hi] + ("…" if hi < len(text) else "")
                markup = (f'<span alpha="55%" size="small">riga {line + 1}</span>\n'
                          f'{esc(flat(pre))}<span background="{find}"><b>{esc(flat(text[a:b]))}</b></span>'
                          f'{esc(flat(post))}')
                label = Gtk.Label(xalign=0, yalign=0)
                label.set_markup(markup)
                label.set_line_wrap(True)
                label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                label.set_lines(5)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.set_max_width_chars(20)
                row = Gtk.ListBoxRow()
                row.add(label)
                row.match = (a, b)
                self.results.add(row)
            self.results.show_all()

        count = len(self._matches)
        if not count:
            info = "Nessun risultato"
        else:
            info = f"{fmt(count)} risultat{'o' if count == 1 else 'i'}"
            if count >= MAX_RESULTS:
                info = f"Oltre {fmt(MAX_RESULTS)} risultati"
            if count > RESULT_ROWS:
                info += f" · primi {RESULT_ROWS} in elenco"
        self.find_info.set_text(info)
        self.find_info.set_visible(True)
        self.show_left_page()

    def select_match(self, match, focus):
        a, b = match
        self.buf.select_range(self.buf.get_iter_at_offset(b), self.buf.get_iter_at_offset(a))
        self.view.scroll_to_mark(self.buf.get_insert(), 0.15, False, 0.0, 0.0)
        if focus:
            self.view.grab_focus()

    def goto_match(self, direction):
        if not self._matches:
            return
        sel = self.buf.get_selection_bounds()
        if sel:
            lo, hi = sel[0].get_offset(), sel[1].get_offset()
        else:
            lo = hi = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
        if direction > 0:
            match = next((m for m in self._matches if m[0] >= hi), self._matches[0])
        else:
            match = next((m for m in reversed(self._matches) if m[1] <= lo), self._matches[-1])
        self.select_match(match, False)

    def on_result_row(self, _box, row):
        self.select_match(row.match, True)

    # --- Appunti -------------------------------------------------------------------------

    def rebuild_notes(self):
        for row in self.notes_list.get_children():
            self.notes_list.remove(row)
        for i, text in enumerate(self.notes):
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            label = Gtk.Label(label=text, xalign=0, yalign=0)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_lines(6)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(20)
            buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            buttons.pack_start(self.button("✎", "Modifica l'appunto",
                                           lambda i=i: self.edit_scratch(i)), False, False, 0)
            buttons.pack_start(self.button("↳", "Inserisci nel testo",
                                           lambda i=i: self.note_insert(i)), False, False, 0)
            buttons.pack_start(self.button("×", "Elimina l'appunto",
                                           lambda i=i: self.note_delete(i)), False, False, 0)
            box.pack_start(label, True, True, 0)
            box.pack_start(buttons, False, False, 0)
            row = Gtk.ListBoxRow()
            row.add(box)
            self.notes_list.add(row)
        self.notes_list.show_all()

    def add_note(self, text):
        text = text.strip("\n")
        if text.strip():
            self.notes.insert(0, text[:20000])
            save_json(NOTES_PATH, self.notes)
            self.rebuild_notes()

    def note_from_clipboard(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.request_text(lambda _c, text, *_: text and self.add_note(text))

    def note_from_selection(self):
        sel = self.buf.get_selection_bounds()
        if sel:
            self.add_note(self.buf.get_text(sel[0], sel[1], True))

    def note_insert(self, index):
        buf = self.buf
        buf.begin_user_action()
        buf.delete_selection(True, True)
        buf.insert_at_cursor(self.notes[index])
        buf.end_user_action()
        self.view.scroll_to_mark(buf.get_insert(), 0.1, False, 0.0, 0.0)
        self.view.grab_focus()

    def note_delete(self, index):
        del self.notes[index]
        save_json(NOTES_PATH, self.notes)
        self.rebuild_notes()

    def document_viewport(self):
        return (self.editor_sw.get_hadjustment().get_value(),
                self.editor_sw.get_vadjustment().get_value())

    def restore_document_viewport(self, position):
        if self._viewport_restore:
            GLib.source_remove(self._viewport_restore)
        horizontal = self.editor_sw.get_hadjustment()
        vertical = self.editor_sw.get_vadjustment()
        def restore():
            self._viewport_restore = 0
            if self.get_realized():
                horizontal.set_value(position[0])
                vertical.set_value(position[1])
            return False
        # Dopo la validazione del layout, altrimenti GtkTextView riposiziona la vista.
        self._viewport_restore = GLib.idle_add(restore, priority=GLib.PRIORITY_LOW)

    def replace_document(self, text, cursor):
        position = self.document_viewport()
        original = self.get_text()
        # Sostituisce solo l'intervallo cambiato: preserva i mark e il layout
        # delle righe precedenti, anziché cancellare e ricreare tutto il buffer.
        first = 0
        limit = min(len(original), len(text))
        while first < limit and original[first] == text[first]:
            first += 1
        tail = 0
        while tail < limit - first and original[-tail-1] == text[-tail-1]:
            tail += 1
        old_end = len(original) - tail
        new_end = len(text) - tail
        was_mutating = self._mutating_notes
        self._mutating_notes = True
        self.buf.begin_user_action()
        try:
            self.buf.delete(self.buf.get_iter_at_offset(first), self.buf.get_iter_at_offset(old_end))
            self.buf.insert(self.buf.get_iter_at_offset(first), text[first:new_end])
            self.buf.place_cursor(self.buf.get_iter_at_offset(min(cursor, len(text))))
        finally:
            self.buf.end_user_action()
            self._mutating_notes = was_mutating
        self.restore_document_viewport(position)

    def activate_note_shortcut(self, *_):
        if self._editing_note is not None or self.splash.get_visible():
            return False
        self.add_margin_note()
        return True

    def add_margin_note(self):
        self.finish_note_action()
        cursor = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
        text, cursor, number = add_footnote(self.get_text(), cursor)
        text, cursor, mapping = synchronize_notes(text, cursor)
        number = mapping[number]
        self.replace_document(text, cursor)
        self.close_menu()
        self.cfg["notes"] = True
        self.right_stack.set_visible_child_name("footnotes")
        self.right_pane.show()
        self.flag(self.notes_btn, True)
        self.schedule_fit()
        self.refresh_margin_notes(text)
        self.edit_margin_note(number)

    def refresh_margin_notes(self, text):
        entries = sorted(document_notes(text), key=lambda note: int(note.number))
        key = tuple((note.number, note.content) for note in entries)
        if key == self._footnote_key:
            return
        self._footnote_key = key
        for child in self.footnote_list.get_children():
            self.footnote_list.remove(child)
        if not entries:
            label = Gtk.Label(label="Nessuna nota. Aggiungila dal menu +.")
            label.set_line_wrap(True)
            self.footnote_list.pack_start(label, False, False, 0)
        for note in entries:
            label = Gtk.Label(label=f"{note.number}. {note.content or '(nota vuota)'}", xalign=0)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_max_width_chars(24)
            link = self.button("", "Torna al richiamo della nota " + note.number,
                               lambda n=note.number: self.goto_margin_note(n))
            link.get_style_context().add_class("note-link")
            link.add(label)
            self.footnote_list.pack_start(link, False, False, 0)
            self.footnote_list.pack_start(self.button("Modifica", "Modifica la nota " + note.number,
                                                    lambda n=note.number: self.edit_margin_note(n)), False, False, 0)
        self.footnote_list.show_all()

    def goto_margin_note(self, number):
        offset = reference_offset(self.get_text(), number)
        if offset is None:
            self.error("Questa nota non ha un richiamo nel corpo del documento.")
            return
        start = self.buf.get_iter_at_offset(offset)
        end = self.buf.get_iter_at_offset(offset + len(f"[^{number}]"))
        self.buf.select_range(start, end)
        self.view.scroll_to_iter(start, 0.15, True, 0.5, 0.4)
        self.view.grab_focus()

    def build_note_editor(self):
        # Un livello della stessa finestra, sopra corpo e barre: nessun nuovo toplevel.
        self.note_layer = Gtk.EventBox()
        self.note_layer.set_visible_window(False)
        self.note_layer.set_no_show_all(True)
        self.overlay.add_overlay(self.note_layer)
        self.overlay.set_overlay_pass_through(self.note_layer, False)
        self.note_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.note_panel.set_name("note-panel")
        self.note_panel.set_halign(Gtk.Align.CENTER)
        self.note_panel.set_valign(Gtk.Align.CENTER)
        self.note_layer.add(self.note_panel)
        self.note_heading = Gtk.Label(xalign=0)
        self.note_panel.pack_start(self.note_heading, False, False, 0)
        self.note_editor = Gtk.TextView()
        self.note_editor.set_name("note-editor")
        self.note_editor.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.note_editor.set_top_margin(8)
        self.note_editor.set_bottom_margin(16)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.note_editor)
        self.note_panel.pack_start(scroll, True, True, 0)
        self.note_status = Gtk.Label(label="Ctrl+Invio per salvare · Esc per annullare", xalign=0)
        self.note_status.set_line_wrap(True)
        self.note_panel.pack_start(self.note_status, False, False, 0)
        actions = Gtk.Box(spacing=12)
        actions.set_halign(Gtk.Align.END)
        actions.pack_start(self.button("Annulla", "Annulla le modifiche alla nota (Esc)",
                                       self.cancel_margin_note), False, False, 0)
        self.editor_save_btn = self.button("Salva la nota", "Salva (Ctrl+Invio)", self.save_margin_note)
        actions.pack_start(self.editor_save_btn, False, False, 0)
        self.note_panel.pack_start(actions, False, False, 0)
        self.note_panel.show_all()
        self.overlay.connect("size-allocate", self.resize_note_editor)

    def resize_note_editor(self, _widget=None, allocation=None):
        if allocation is None:
            allocation = self.overlay.get_allocation()
        size = (max(1, min(900, allocation.width - 96)),
                max(1, min(640, allocation.height - 112)))
        if self.note_panel.get_size_request() != size:
            self.note_panel.set_size_request(*size)

    def edit_margin_note(self, number):
        self.finish_note_action()
        matches = [note for note in document_notes(self.get_text()) if note.number == number]
        if len(matches) != 1:
            self.error("Numero di nota assente o duplicato: correggi le definizioni Markdown.")
            return
        self.open_text_editor(number, matches[0].content, "Nota " + number, "Salva la nota")

    def edit_scratch(self, index):
        self._scratch_original = self.notes[index]
        self.open_text_editor(("scratch", index), self.notes[index], "Appunto", "Salva l'appunto")

    def open_text_editor(self, identity, content, title, save_label):
        self.close_menu()
        self._editing_note = identity
        self._note_cursor = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
        self._editor_viewport = self.document_viewport()
        self.note_heading.set_text(title)
        self.editor_save_btn.set_label(save_label)
        self.note_editor.get_buffer().set_text(content)
        self.note_editor.get_buffer().set_modified(False)
        self.note_status.set_text("Ctrl+Invio per salvare · Esc per annullare")
        self.resize_note_editor()
        self.root.set_sensitive(False)
        self.note_layer.show()
        self.note_editor.grab_focus()
        self.restore_document_viewport(self._editor_viewport)

    def save_margin_note(self):
        if self._editing_note is None:
            return
        buf = self.note_editor.get_buffer()
        content = buf.get_text(*buf.get_bounds(), True)
        try:
            if isinstance(self._editing_note, tuple):
                index = self._editing_note[1]
                if index >= len(self.notes) or self.notes[index] != self._scratch_original:
                    self.note_status.set_text("L'appunto è cambiato. Annulla e riaprilo per modificarlo.")
                    return
                updated = self.notes.copy()
                updated[index] = content
                if not save_json(NOTES_PATH, updated):
                    self.note_status.set_text("Salvataggio non riuscito. Il testo resta aperto: riprova.")
                    return
                self.notes = updated
                self.rebuild_notes()
            else:
                text = update_note(self.get_text(), self._editing_note, content)
                self.replace_document(text, self._note_cursor)
                self.refresh_margin_notes(text)
        except ValueError as error:
            self.note_status.set_text(str(error))
            return
        self.cancel_margin_note()

    def cancel_margin_note(self):
        self.note_layer.hide()
        self._editing_note = None
        self.root.set_sensitive(True)
        self.view.grab_focus()
        self.restore_document_viewport(self._editor_viewport)

    # --- Tastiera e rotella --------------------------------------------------------

    def key_sound(self, key):
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            name = "enter"
        elif key == Gdk.KEY_space:
            name = "space"
        elif key in (Gdk.KEY_BackSpace, Gdk.KEY_Delete):
            name = "back"
        elif Gdk.keyval_to_unicode(key) >= 32:
            name = "key"
        else:
            return
        self.typewriter.play(name)

    def on_key(self, _w, e):
        state = e.state & Gtk.accelerator_get_default_mod_mask()
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        key = e.keyval
        self.finish_note_action()
        if self._editing_note is not None:
            if ctrl and key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.save_margin_note()
                return True
            if key == Gdk.KEY_Escape:
                self.cancel_margin_note()
                return True
            # Il resto della tastiera resta nell'editor della nota; niente comandi
            # di apertura, cambio documento o formattazione sul corpo sottostante.
            return False
        if self.splash.get_visible():
            if ctrl and shift and Gdk.keyval_to_lower(key) == Gdk.KEY_o:
                self.choose_home_folder()
                return True
            if ctrl and Gdk.keyval_to_lower(key) == Gdk.KEY_o:
                self.file_open()
                return True
            if ctrl and Gdk.keyval_to_lower(key) == Gdk.KEY_n:
                self.file_new()
                return True
            if ctrl and Gdk.keyval_to_lower(key) == Gdk.KEY_q:
                self.close()
                return True
            if key == Gdk.KEY_Escape:
                self.dismiss_splash()
                return True
            if ctrl or state & Gdk.ModifierType.MOD1_MASK:
                return False
            if (Gdk.keyval_name(key) or "").startswith(MODIFIER_KEYS):
                return False
            if key in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
                buttons = [self.home_choose_btn] + [child for container in (self.home_recent, self.home_files)
                                                   for child in container.get_children() if isinstance(child, Gtk.Button)]
                backwards = shift or key == Gdk.KEY_ISO_Left_Tab
                current = self.get_focus()
                index = ((buttons.index(current) + (-1 if backwards else 1)) % len(buttons)
                         if current in buttons else -1 if backwards else 0)
                buttons[index].grab_focus()
                return True
            if key in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Page_Up, Gdk.KEY_Page_Down):
                return False
            if isinstance(self.get_focus(), Gtk.Button) and key in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                return False
            self.dismiss_splash()
            return True
        if key == Gdk.KEY_Escape and self._menu is not None:
            self.close_menu()
            return True
        if ctrl and shift and Gdk.keyval_to_lower(key) == Gdk.KEY_n:
            return self.activate_note_shortcut()
        in_editor = self.get_focus() is self.view
        if in_editor and not state and key in (Gdk.KEY_BackSpace, Gdk.KEY_Delete) and not self.buf.get_has_selection():
            cursor = self.buf.get_iter_at_mark(self.buf.get_insert()).get_offset()
            ref = next((ref for ref in references(self.get_text())
                        if (key == Gdk.KEY_BackSpace and ref.end == cursor)
                        or (key == Gdk.KEY_Delete and ref.start == cursor)), None)
            if ref:
                self.buf.begin_user_action()
                self.buf.delete(self.buf.get_iter_at_offset(ref.start), self.buf.get_iter_at_offset(ref.end))
                self.buf.end_user_action()
                return True
        if (self.cfg["sound"] and in_editor
                and not state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)):
            self.key_sound(key)
        if key == Gdk.KEY_F1:
            self.show_help()
            return True
        if key == Gdk.KEY_F8:
            self.show_insert()
            return True
        if key == Gdk.KEY_F9:
            self.toggle_sidebar()
            return True
        if key == Gdk.KEY_F10:
            self.toggle_notes()
            return True
        if not ctrl:
            return False
        if in_editor:
            command = None
            lower = Gdk.keyval_to_lower(key)
            # Il simbolo Shift+7 cambia tra tastiere (es. & oppure /).
            translated = Gdk.Keymap.get_for_display(self.get_display()).translate_keyboard_state(
                e.hardware_keycode, Gdk.ModifierType(e.state & ~Gdk.ModifierType.SHIFT_MASK), e.group)
            base_key = translated[1] if translated[0] else lower
            if not shift:
                command = {Gdk.KEY_b: "bold", Gdk.KEY_i: "italic", Gdk.KEY_u: "underline",
                           Gdk.KEY_bracketright: "indent", Gdk.KEY_bracketleft: "outdent"}.get(lower)
            elif lower == Gdk.KEY_x:
                command = "strike"
            elif base_key == Gdk.KEY_7:
                command = "bullet"
            elif base_key == Gdk.KEY_8:
                command = "number"
            if command:
                self.format_text(command)
                return True
        if key in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.change_size(1)
        elif key in (Gdk.KEY_minus, Gdk.KEY_underscore, Gdk.KEY_KP_Subtract):
            self.change_size(-1)
        elif key in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.cfg["size"] = DEFAULTS["size"]
            self.apply_style()
        elif key in (Gdk.KEY_f, Gdk.KEY_F):
            self.focus_search()
        elif key in (Gdk.KEY_s, Gdk.KEY_S):
            self.file_save(as_new=shift)
        elif key in (Gdk.KEY_o, Gdk.KEY_O):
            self.file_open()
        elif key in (Gdk.KEY_n, Gdk.KEY_N):
            self.file_new()
        elif key in (Gdk.KEY_y, Gdk.KEY_Y):
            if in_editor and self.buf.can_redo():
                self.buf.redo()
        elif key in (Gdk.KEY_q, Gdk.KEY_Q):
            self.close()
        else:
            return False
        return True

    def on_scroll(self, _w, e):
        if not e.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        if e.direction == Gdk.ScrollDirection.UP:
            self.change_size(1)
        elif e.direction == Gdk.ScrollDirection.DOWN:
            self.change_size(-1)
        elif e.direction == Gdk.ScrollDirection.SMOOTH and e.delta_y != 0:
            self.change_size(-1 if e.delta_y > 0 else 1)
        else:
            return False
        return True

    # --- Salvataggio automatico ----------------------------------------------------------

    def schedule_autosave(self):
        if self.cfg["autosave"] and not self._autosave_timer:
            self._autosave_timer = GLib.timeout_add_seconds(AUTOSAVE_SECONDS, self.autosave_tick)

    def autosave_tick(self):
        self._autosave_timer = 0
        self.autosave_now()
        return False

    def flush_autosave(self):
        if self._autosave_timer:
            GLib.source_remove(self._autosave_timer)
            self._autosave_timer = 0
        self.autosave_now()

    def autosave_now(self):
        self.finish_note_action()
        """Con un file aperto lo salva; senza nome conserva una bozza da ripristinare."""
        if not self.cfg["autosave"] or not self.buf.get_modified():
            return
        text = self.get_text()
        if self.path:
            if write_atomic(self.path, text):
                self.buf.set_modified(False)
            elif not self._autosave_failed:
                self._autosave_failed = True
                self.error(f"Salvataggio automatico non riuscito:\n{self.path}")
        elif not text.strip():
            self.remove_draft()
        elif text != self._last_draft:
            if write_atomic(RECOVERY_PATH, text):
                self._last_draft = text

    def remove_draft(self):
        self._last_draft = None
        try:
            os.remove(RECOVERY_PATH)
        except OSError:
            pass

    def restore_draft(self):
        try:
            with open(RECOVERY_PATH, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            return
        if text.strip():
            self.set_content(text, None)
            self._last_draft = text
            self.buf.set_modified(True)

    # --- File ------------------------------------------------------------------------

    def get_text(self):
        start, end = self.buf.get_bounds()
        return self.buf.get_text(start, end, True)

    def error(self, message):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.CLOSE, text=message)
        d.run()
        d.destroy()

    def choose(self, action):
        saving = action == Gtk.FileChooserAction.SAVE
        dlg = Gtk.FileChooserNative.new(
            "Salva con nome" if saving else "Apri", self, action,
            "_Salva" if saving else "_Apri", "_Annulla")
        folder = (os.path.dirname(self.path) if self.path else "") or self.cfg["folder"]
        if os.path.isdir(folder):
            dlg.set_current_folder(folder)
        md = Gtk.FileFilter()
        md.set_name("Markdown e testo")
        for pattern in ("*.md", "*.markdown", "*.txt"):
            md.add_pattern(pattern)
        everything = Gtk.FileFilter()
        everything.set_name("Tutti i file")
        everything.add_pattern("*")
        dlg.add_filter(md)
        dlg.add_filter(everything)
        if saving:
            dlg.set_do_overwrite_confirmation(True)
            dlg.set_current_name(os.path.basename(self.path) if self.path else "senza-titolo.md")
        path = dlg.get_filename() if dlg.run() == Gtk.ResponseType.ACCEPT else None
        dlg.destroy()
        return path

    def confirm(self):
        """True se si può procedere (salvato, scartato o nulla da salvare)."""
        if not self.buf.get_modified():
            return True
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.NONE,
                              text="Salvare le modifiche?")
        d.format_secondary_text("Le modifiche non salvate andranno perse.")
        d.add_button("Annulla", Gtk.ResponseType.CANCEL)
        d.add_button("Scarta", Gtk.ResponseType.REJECT)
        d.add_button("Salva", Gtk.ResponseType.ACCEPT)
        d.set_default_response(Gtk.ResponseType.ACCEPT)
        response = d.run()
        d.destroy()
        if response == Gtk.ResponseType.ACCEPT:
            return self.file_save()
        return response == Gtk.ResponseType.REJECT

    def set_content(self, text, path):
        self.finish_note_action()
        if self._viewport_restore:
            GLib.source_remove(self._viewport_restore)
            self._viewport_restore = 0
        original = text
        text, _cursor, _mapping = synchronize_notes(text)
        self._mutating_notes = True
        self.buf.begin_not_undoable_action()
        self.buf.set_text(text)
        self.buf.end_not_undoable_action()
        self._mutating_notes = False
        self.buf.set_modified(text != original)
        self.buf.place_cursor(self.buf.get_start_iter())
        self.path = path
        self._autosave_failed = False
        self.refresh()

    def file_new(self):
        if self.confirm():
            if self.path is None:
                self.remove_draft()
            self.set_content("", None)
            self._home_viewport = None
            self.dismiss_splash()
            self.view.grab_focus()

    def file_open(self):
        path = self.choose(Gtk.FileChooserAction.OPEN)
        if path:
            self.open_home_file(path)

    def open_path(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.error(f"Impossibile aprire il file:\n{e}")
            return False
        self.set_content(text, os.fspath(path))
        self.remember_document(path)
        self._home_viewport = None
        self.dismiss_splash()
        self.view.grab_focus()
        return True

    def file_save(self, as_new=False):
        self.finish_note_action()
        path = self.path
        if as_new or not path:
            path = self.choose(Gtk.FileChooserAction.SAVE)
            if not path:
                return False
            if not os.path.splitext(path)[1]:
                path += ".md"
        if not write_atomic(path, self.get_text()):
            self.error(f"Impossibile salvare il file:\n{path}")
            return False
        if self.path is None:
            self.remove_draft()             # la bozza senza nome ora è un file vero
        self.path = path
        self.buf.set_modified(False)
        self.remember_document(path)
        self.update_title()
        return True

    def on_delete(self, *_):
        self.finish_note_action()
        if self._editing_note is not None:
            self.note_status.set_text("Salva o annulla la modifica prima di chiudere Tasto.")
            self.note_editor.grab_focus()
            return True
        if self.cfg["autosave"]:
            self.flush_autosave()           # salva (o conserva la bozza) senza chiedere
            if self.path and self.buf.get_modified() and not self.confirm():
                return True                 # il salvataggio automatico è fallito
        elif not self.confirm():
            return True
        self.cfg["win"] = list(self.get_size())
        save_json(CONFIG_PATH, self.cfg)
        return False


def main():
    win = Tasto()
    win.connect("destroy", Gtk.main_quit)
    win.start(sys.argv[1] if len(sys.argv) > 1 else None)
    Gtk.main()


if __name__ == "__main__":
    main()
