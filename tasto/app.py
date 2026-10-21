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
    "chiaro": theme("Chiaro", "#111111", "#f6f6f6", "#666666", "#dbe3f0", "#dcdcdc", "#ffe58f",
                    "#0550ae", "#953800", "#8250df", "#1a7f37", "#57606a", "#cf222e", "#0969da"),
    "seppia": theme("Seppia", "#3a2412", "#f0e4c8", "#5f4c30", "#dccaa0", "#d7c8a2", "#f2c94c",
                    "#a2381b", "#7a4a00", "#6b3f8a", "#2f6b3a", "#5f4c30", "#a2381b", "#1f5f8b"),
    "antracite": theme("Scuro", "#f0f0f0", "#2b2f33", "#9aa1a8", "#4b535b", "#3d4348", "#5a4a14",
                       "#79c0ff", "#ffa657", "#d2a8ff", "#7ee787", "#9aa1a8", "#ff7b72", "#58a6ff"),
}
THEME_ORDER = ["chiaro", "seppia", "antracite"]

# (nome mostrato, famiglie in ordine di preferenza, fattore di grandezza).
# IBM Plex è una famiglia progettata per stare insieme, con grassetto e corsivo veri
# in tutti e tre i caratteri. Il mono, a parità di punti, appare molto più grande
# (lettere più larghe), quindi viene ridotto del 10%.
FONTS = [
    ("Mono", "'IBM Plex Mono', 'Noto Sans Mono', 'DejaVu Sans Mono', monospace", 0.9),
    ("Serif", "'IBM Plex Serif', 'Noto Serif', 'DejaVu Serif', serif", 1.0),
    ("Sans", "'IBM Plex Sans', 'Noto Sans', 'DejaVu Sans', sans-serif", 1.0),
]
UI_FONT = FONTS[0][1]  # carattere unico di barre laterali, barra inferiore e menu
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
            "notes": False, "target": 0, "colors": False, "sound": False,
            "autosave": True, "splash": True, "win": [1280, 800]}

CSS = Path(__file__).with_name("style.css").read_text(encoding="utf-8")


def extra_css():
    """Colori dei tre riquadri tema nella barra inferiore."""
    return "\n".join(f"#bar button.sq.sq-{key} {{ background-color: {THEMES[key]['bg']}; }}"
                     for key in THEME_ORDER)


# --- Markdown ------------------------------------------------------------------

HEADING = re.compile(r"^(#{1,3})[ \t]+(.*\S)[ \t]*$")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
QUOTE = re.compile(r"^\s{0,3}>")
LIST = re.compile(r"^\s*([-+*]|\d{1,3}[.)])(?=\s)")
LINK = re.compile(r"(\[[^\]\n]+\])(\([^)\n]+\))")
INLINE = [
    (re.compile(r"\*\*[^*\n]+\*\*"), "bold"),
    (re.compile(r"(?<!\*)\*(?!\s)[^*\n]+(?<!\s)\*(?!\*)"), "ital"),
    (re.compile(r"(?<![\w_])_(?!\s)[^_\n]+(?<!\s)_(?![\w_])"), "ital"),
    (re.compile(r"`[^`\n]+`"), "code"),
]
WORD = re.compile(r"\S*\w\S*")

HELP = [
    ("# Titolo", "titolo di primo livello"),
    ("## Titolo", "secondo livello"),
    ("### Titolo", "terzo livello"),
    ("**testo**", "grassetto"),
    ("*testo*  _testo_", "corsivo"),
    ("- voce", "elenco puntato"),
    ("1. voce", "elenco numerato"),
    ("> testo", "citazione"),
    ("[testo](indirizzo)", "collegamento"),
    ("`codice`", "codice nel testo"),
    ("```", "blocco di codice (a inizio e a fine)"),
    ("---", "linea di separazione"),
]
HELP_NOTE = ("I titoli #, ## e ### compaiono nell'indice a sinistra.\n"
             "Ctrl+F cerca · F8 inserisci · F9 indice · F10 appunti")


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
        if cfg["theme"] not in THEMES:
            cfg["theme"] = DEFAULTS["theme"]
        if not (isinstance(cfg["font"], int) and 0 <= cfg["font"] < len(FONTS)):
            cfg["font"] = DEFAULTS["font"]
        cfg["size"] = max(SIZE_MIN, min(SIZE_MAX, int(cfg["size"])))
        cfg["width"] = max(WIDTH_MIN, min(WIDTH_MAX, int(cfg["width"])))
        cfg["target"] = max(0, int(cfg["target"]))
        cfg["win"] = [int(cfg["win"][0]), int(cfg["win"][1])]
        for key in ("sidebar", "notes", "colors", "sound", "autosave", "splash"):
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
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


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
        self.editor_sw = Gtk.ScrolledWindow()
        self.editor_sw.add(self.view)

        # Tre colonne affiancate, senza maniglie né divisori: tutto sullo stesso piano
        self.body.pack_start(self.left_pane, False, False, 0)
        self.body.pack_start(self.editor_sw, True, True, 0)
        self.body.pack_start(self.right_pane, False, False, 0)
        self.root.connect("size-allocate", self.schedule_fit)

        b = self.buf
        self.t_h = [b.create_tag(f"h{i}", weight=Pango.Weight.BOLD, scale=s)
                    for i, s in ((1, 1.6), (2, 1.35), (3, 1.15))]
        self.t_mark = b.create_tag("mark")
        self.tags = {
            "bold": b.create_tag("bold", weight=Pango.Weight.BOLD),
            "ital": b.create_tag("ital", style=Pango.Style.ITALIC),
            "code": b.create_tag("code", family=CODE_FAMILY),
            "quote": b.create_tag("quote"),
            "list": b.create_tag("list"),
            "linktext": b.create_tag("linktext"),
            "linkurl": b.create_tag("linkurl"),
        }
        self.md_tags = self.t_h + [self.t_mark] + list(self.tags.values())
        self.t_find = b.create_tag("find")   # creato per ultimo: ha la precedenza
        b.connect("changed", self.on_changed)
        b.connect("modified-changed", lambda *_: self.update_title())

        self.build_bottom_bar()
        self.build_splash()

        self.connect("key-press-event", self.on_key)
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
        self.right_pane.pack_start(self.pane_title("APPUNTI"), False, False, 0)
        self.right_pane.pack_start(row, False, False, 0)
        self.right_pane.pack_start(notes_sw, True, True, 0)
        self.rebuild_notes()

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
        self.insert_btn = self.button("Inserisci", "Inserisci ASCII art (F8)", self.show_insert)
        left.pack_start(self.side_btn, False, False, 0)
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

        self.theme_btns = {}
        for name in THEME_ORDER:
            btn = self.button("", THEMES[name]["label"], lambda n=name: self.set_theme(n))
            ctx = btn.get_style_context()
            ctx.add_class("sq")
            ctx.add_class("sq-" + name)
            self.theme_btns[name] = add(btn)
        self.color_btn = add(self.glyph_button("✱", "Colora gli elementi del markdown",
                                               self.toggle_colors), 12)
        self.sound_btn = add(self.glyph_button("T", "Suono di macchina da scrivere",
                                               self.toggle_sound))
        self.gear_btn = add(self.icon_button(
            ("emblem-system-symbolic", "preferences-system-symbolic"), "⚙",
            "Carattere, grandezza, larghezza e salvataggio", self.show_settings), 12)
        self.notes_btn = add(self.icon_button(
            ("sidebar-show-right-symbolic", "view-dual-symbolic"), "▥",
            "Mostra o nascondi gli appunti (F10)", self.toggle_notes))

        self.insert_menu = self.build_insert_menu()
        self.settings_menu = self.build_settings_menu()
        self.help_menu = self.build_help_menu()
        self.goal_menu = self.build_goal_menu()

    def tick(self):
        self.clock.set_text(time.strftime("%H:%M"))
        return True

    def build_splash(self):
        """Schermata iniziale: sparisce al primo tasto (o con un clic)."""
        self.splash = Gtk.EventBox()
        self.splash.set_name("splash")
        self.splash.set_visible_window(True)
        self.splash.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.splash.connect("button-press-event", self.on_splash_click)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        self.splash_dots = None
        for text, cls in (("premi un", None), ("TASTO", "key"), ("...", "dots")):
            label = Gtk.Label(label=text)
            if cls:
                label.get_style_context().add_class(cls)
            if cls == "dots":
                self.splash_dots = label
            box.pack_start(label, False, False, 0)
        self.splash.add(box)
        self.overlay.add_overlay(self.splash)           # per ultimo: sta sopra a tutto
        self.overlay.set_overlay_pass_through(self.splash, False)
        GLib.timeout_add(650, self.blink_splash)

    def blink_splash(self):
        if not self.splash.get_visible():
            return False
        dots = self.splash_dots
        dots.set_opacity(1.0 if dots.get_opacity() < 1.0 else 0.15)
        return True

    def on_splash_click(self, *_):
        self.dismiss_splash()
        return True

    def dismiss_splash(self):
        if self.splash.get_visible():
            self.splash.hide()
            self.view.grab_focus()

    def start(self, path=None):
        self.show_all()
        if not self.cfg["splash"]:
            self.splash.hide()
        self.left_pane.set_visible(self.cfg["sidebar"])
        self.right_pane.set_visible(self.cfg["notes"])
        self.update_goal()
        if path:
            self.open_path(path)
        else:
            self.restore_draft()
        self.view.grab_focus()

    # --- Menu a comparsa (seguono il tema) ----------------------------------------------

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
        self.splash_btn.connect("clicked", lambda *_: self.toggle_splash())
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
        values = dict(th, font=font_css, size=f"{eff:.1f}", ui=str(UI_SIZE),
                      uifont=UI_FONT, accent=th["syn"]["head"])
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
                           ("quote", "quote"), ("list", "list"), ("linktext", "link")):
            self.paint(self.tags[key], syn.get(color))
        self.paint(self.tags["linkurl"], th["dim"] if c["colors"] else None)

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
        self.flag(self.splash_btn, c["splash"])

    def set_theme(self, name):
        self.cfg["theme"] = name
        self.apply_style()

    def set_font(self, index):
        self.cfg["font"] = index
        self.apply_style()

    def toggle_colors(self):
        self.cfg["colors"] = not self.cfg["colors"]
        self.apply_style()

    def toggle_splash(self):
        self.cfg["splash"] = not self.cfg["splash"]
        self.sync_settings()

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

    def style_markdown(self, text):
        start, end = self.buf.get_bounds()
        for tag in self.md_tags:
            self.buf.remove_tag(tag, start, end)
        heads, in_code = [], False
        for n, line in enumerate(text.split("\n")):
            if FENCE.match(line):
                in_code = not in_code
                self.tag_range(self.tags["code"], n, 0, len(line))
            elif in_code:
                self.tag_range(self.tags["code"], n, 0, len(line))
            else:
                m = HEADING.match(line)
                if m:
                    level = len(m.group(1))
                    self.tag_range(self.t_h[level - 1], n, 0, len(line))
                    self.tag_range(self.t_mark, n, 0, level)
                    heads.append((level, m.group(2), n))
                    continue
                if QUOTE.match(line):
                    self.tag_range(self.tags["quote"], n, 0, len(line))
                m = LIST.match(line)
                if m:
                    self.tag_range(self.tags["list"], n, m.start(1), m.end(1))
                for rx, name in INLINE:
                    for mm in rx.finditer(line):
                        self.tag_range(self.tags[name], n, mm.start(), mm.end())
                for mm in LINK.finditer(line):
                    self.tag_range(self.tags["linktext"], n, *mm.span(1))
                    self.tag_range(self.tags["linkurl"], n, *mm.span(2))
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
        if self.splash.get_visible():           # il primo tasto chiude la schermata iniziale
            if (Gdk.keyval_name(key) or "").startswith(MODIFIER_KEYS):
                return False
            self.dismiss_splash()
            if self.cfg["sound"]:
                self.typewriter.play("key")
            return True
        if key == Gdk.KEY_Escape and self._menu is not None:
            self.close_menu()
            return True
        in_editor = self.get_focus() is self.view
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
        self.buf.begin_not_undoable_action()
        self.buf.set_text(text)
        self.buf.end_not_undoable_action()
        self.buf.set_modified(False)
        self.buf.place_cursor(self.buf.get_start_iter())
        self.path = path
        self._autosave_failed = False
        self.refresh()

    def file_new(self):
        if self.confirm():
            if self.path is None:
                self.remove_draft()
            self.set_content("", None)

    def file_open(self):
        path = self.choose(Gtk.FileChooserAction.OPEN)
        if path and self.confirm():
            if self.path is None:
                self.remove_draft()
            self.open_path(path)

    def open_path(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.error(f"Impossibile aprire il file:\n{e}")
            return
        self.set_content(text, path)

    def file_save(self, as_new=False):
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
        self.update_title()
        return True

    def on_delete(self, *_):
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
