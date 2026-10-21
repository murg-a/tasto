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
- Tre temi, tre famiglie di font, dimensione e larghezza regolabili.
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

## Sviluppo

- `tasto/app.py`: base GTK importata da `scrivi3.py`, adattata al nome e ai percorsi Tasto.
- `tasto/style.css`: stile estratto dal file originale; i segnaposto `@bg@`,
  `@fg@`, ecc. sono sostituiti da Python in base al tema.
- `tasto/document.py`: componente del precedente prototipo, conservato ma non
  utilizzato dall'interfaccia importata.
- `tests/test_document.py`: test del componente precedente, non test della nuova interfaccia.
- `tests/test_imported_source.py`: controlli di integrazione sul codice importato e sul CSS.

Da completare rispetto al progetto originale: sette temi, cinque livelli di
titoli, menu di formattazione completo, sostituzione, spostamento delle sezioni,
note a margine e modifica degli appunti. Attualmente eliminare un appunto non
richiede conferma.

```sh
python3 -m unittest discover -s tests -v
```

Nell'ambiente cloud mancano GtkSourceView 4 e un display virtuale: l'avvio,
il rendering e le interazioni di questa versione devono ancora essere
verificati su Linux. I test automatici senza display non ne sostituiscono il collaudo.

Verifica aggiuntiva eseguita: il parser CSS di GTK 3 accetta tutte le nove
combinazioni dei tre temi e dei tre font. Questo non verifica il rendering.
