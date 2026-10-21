# Tasto

Editor Markdown minimale per Linux, in Python, GTK 3 e GtkSourceView 4.
Questa versione adotta come base il file `scrivi3.py` fornito dall'autore del
progetto, con l'interfaccia mostrata negli screenshot. Il prototipo precedente
con GTK 4 resta recuperabile dalla cronologia Git.

## Installazione e avvio

Su Debian, Ubuntu o Linux Mint:

```sh
sudo apt update
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtksource-4
```

Font consigliati (opzionali; in assenza vengono usati quelli di sistema):

```sh
sudo apt install fonts-ibm-plex fonts-noto-core
```

Dalla cartella del progetto:

```sh
/usr/bin/python3 -m tasto
```

Puoi anche aprire un documento direttamente:

```sh
/usr/bin/python3 -m tasto percorso/documento.md
```

Questa versione richiede GTK **3**, anche se avevi già installato GTK 4.
Non servono pip o credenziali. Per aggiornare una copia scaricata con Git,
chiudi prima Tasto, entra nella cartella del progetto ed esegui `git pull`.

## Funzioni presenti nella base importata

- Schermata iniziale «premi un TASTO», colonna centrata e barre laterali richiudibili.
- Sette temi, tre famiglie di font, dimensione e larghezza regolabili.
- Evidenziazione Markdown, indice collassabile (tre livelli), ricerca con anteprime.
- Conteggi e obiettivo di parole con barra di avanzamento.
- Appunti persistenti: incolla, copia dalla selezione e inserisci nel documento.
- Menu di elementi ASCII, aiuto Markdown, annulla e ripeti.
- Preferenze salvate, salvataggio automatico e recupero di una bozza senza nome.
- Suoni opzionali se è disponibile `pw-play`, `paplay` oppure `aplay`.

**Il salvataggio automatico è attivo per impostazione predefinita:** modifica
anche i documenti aperti dopo pochi secondi. Puoi disattivarlo nell'ingranaggio.
Per le prime prove usa una copia dei tuoi documenti.

Gli appunti sono condivisi tra i documenti e vengono conservati in
`~/.config/tasto/appunti.json`; le preferenze in `~/.config/tasto/config.json`.
La bozza senza nome è in `~/.local/share/tasto/recupero.md` (i percorsi seguono
le directory XDG se personalizzate). I dati della precedente app Scrivi non
vengono modificati o importati automaticamente.

## Temi

Nella barra inferiore trovi un solo riquadro con una `t`: mostra il tema
corrente. Cliccalo per aprire la scelta dei sette temi; selezionandone uno
il menu si chiude e il riquadro si aggiorna:

- **Chiaro**: nero su bianco.
- **Ghiaccio**: blu ardesia su bianco freddo.
- **Seppia**: marrone scuro su beige.
- **Sole**: marrone su crema dorato.
- **Scuro**: bianco su antracite.
- **Dracula**: fondo viola scuro e accenti viola, rosa e ciano.
- **Terminale**: verde su fondo quasi nero.

Il tema viene ricordato alla chiusura. Attiva il pulsante **✱** per vedere
anche i colori Markdown specifici del tema.

## Menu + e formattazione

Il pulsante **+** a sinistra apre i comandi di formattazione:

- Grassetto (`**testo**`), corsivo (`_testo_`), sottolineato (`<u>testo</u>`) e barrato (`~~testo~~`).
- Elenco puntato, elenco numerato e aumento/riduzione del rientro (quattro spazi).

Seleziona il testo e scegli il comando. Senza selezione, i formati in linea
inseriscono i marcatori attorno al cursore; elenchi e rientri agiscono sulla
riga corrente. Con più righe selezionate agiscono su tutte le righe coinvolte.
Ogni comando è una singola operazione annullabile con Ctrl+Z.
Il sottolineato usa HTML perché Markdown non ha una sintassi standard dedicata.
Il pulsante **ASCII** e F8 mantengono accessibile il precedente menu di elementi ASCII.

### Scorciatoie di formattazione

Le scorciatoie agiscono quando il cursore è nel corpo del documento.

| Comando | Scorciatoia |
| --- | --- |
| Grassetto | Ctrl+B |
| Corsivo | Ctrl+I |
| Sottolineato | Ctrl+U |
| Barrato | Ctrl+Shift+X |
| Elenco puntato | Ctrl+Shift+7 |
| Elenco numerato | Ctrl+Shift+8 |
| Aumenta / riduci rientro | Ctrl+] / Ctrl+[ |
| Aggiungi nota | Ctrl+Shift+N |

### Note a margine

Dal menu **+ → Aggiungi nota**, o con **Ctrl+Shift+N**, inserisci il richiamo
numerato al cursore. Si apre un editor sovrapposto al documento, centrato, senza bordi e distinto
tramite un'ombra. Premi **Salva la nota** o **Ctrl+Invio** per applicare il
contenuto, oppure **Annulla** / **Esc** per scartare le modifiche.
La dimensione del pannello si adatta alla finestra (fino a circa 900 × 640 px).
La barra destra mostra l'elenco delle note: cliccando sul testo di una nota
torni al suo richiamo nel documento, che viene selezionato; **Modifica** apre
l'editor sovrapposto. Se il richiamo è ripetuto si raggiunge il primo.
Annullare una nota appena creata lascia una nota vuota, rimovibile con Ctrl+Z.
Durante la modifica, il documento sottostante è bloccato; per chiudere Tasto
occorre prima salvare o annullare la nota.

Le note appartengono al documento, a differenza degli appunti condivisi:
sono salvate come Markdown standard, con `[^1]` nel testo e `[^1]: contenuto`
in fondo al documento. Le definizioni sono visibili anche nel corpo del testo.
Modifiche e inserimenti seguono il normale salvataggio/autosalvataggio e sono
annullabili. I numeri restano stabili; non vengono rinumerati quando sposti il testo.
Aprendo di nuovo il file, le note ricompaiono nella barra destra.

### Font dell'interfaccia

La scelta **Mono / Serif / Sans** cambia anche barre, menu ed editor delle
note. Le tre famiglie IBM Plex sono coordinate e restano la scelta consigliata;
in loro assenza si usano Noto, poi DejaVu e i font generici di sistema.
La dimensione del testo resta regolabile; i controlli mantengono dimensioni
compatte, compensate per il Mono, e i margini della colonna continuano ad
adattarsi alla finestra. Codice e anteprime ASCII mantengono la spaziatura fissa
necessaria all'allineamento.

## Sviluppo

- `tasto/app.py`: base GTK importata da `scrivi3.py`, adattata al nome e ai percorsi Tasto.
- `tasto/footnotes.py`: lettura, creazione e modifica di note Markdown.
- `tasto/formatting.py`: trasformazioni Markdown usate dal menu +.
- `tasto/style.css`: stile estratto dal file originale; i segnaposto `@bg@`,
  `@fg@`, ecc. sono sostituiti da Python in base al tema.
- `tasto/document.py`: componente del precedente prototipo, conservato ma non
  utilizzato dall'interfaccia importata.
- `tests/test_document.py`: test del componente precedente, non test della nuova interfaccia.
- `tests/test_imported_source.py`: controlli di integrazione sul codice importato e sul CSS.

Da completare rispetto al progetto originale: cinque livelli di
titoli, sostituzione, spostamento delle sezioni e
modifica degli appunti. Attualmente eliminare un appunto non
richiede conferma.

```sh
python3 -m unittest discover -s tests -v
```

Nell'ambiente cloud mancano GtkSourceView 4 e un display virtuale: l'avvio,
il rendering e le interazioni di questa versione devono ancora essere
verificati su Linux. I test automatici senza display non ne sostituiscono il collaudo.

Verifica aggiuntiva eseguita: il parser CSS di GTK 3 accetta tutte le 21
combinazioni dei sette temi e dei tre font. Questo non verifica il rendering.

Il collegamento della formattazione è stato verificato anche con un vero
Gtk.TextBuffer (grassetto, sottolineato, elenco numerato), senza finestra.

Verifiche dell’ultimo aggiornamento: parsing e modifica delle note, callback
di modifica del documento con Gtk.TextBuffer reale, instradamento delle
scorciatoie (con traduzione della tastiera simulata) e CSS su 21 combinazioni.
La verifica visiva e della tastiera fisica richiede ancora il PC Linux.
