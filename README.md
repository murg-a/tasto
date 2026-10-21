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

## Funzioni disponibili

- Schermata iniziale «premi un TASTO», colonna centrata e barre laterali richiudibili.
- Sette temi, tre famiglie di font, dimensione e larghezza regolabili.
- Live Preview Markdown, indice collassabile (tre livelli), ricerca con anteprime.
- Conteggi e obiettivo di parole con barra di avanzamento.
- Appunti persistenti: incolla, copia dalla selezione, modifica e inserisci nel documento.
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

## Live Preview

La riga del cursore mostra i delimitatori Markdown/HTML per modificarli. Fuori
dalla riga attiva i delimitatori vengono nascosti: titoli da `#` a `######`,
grassetto, corsivo, barrato, codice inline e link mostrano il testo formattato.
Le righe selezionate mostrano la sorgente; nei blocchi delimitati da backtick o
tilde viene rivelato l'intero blocco. Il contenuto dei blocchi di codice resta
letterale.

L'HTML supportato è limitato ai tag inline accoppiati senza attributi:
`b`, `strong`, `i`, `em`, `u`, `s`, `del`, `code`. Il resto rimane visibile
come sorgente; HTML e script non vengono eseguiti. Immagini, tabelle, liste e
citazioni mantengono i propri marcatori: questa versione non è un renderer
CommonMark completo.

Il Markdown originale resta nel buffer e nel file; le decorazioni non cambiano
salvataggio o cronologia di annullamento. Il parser è indipendente da GTK.
Le modifiche al documento vengono raggruppate con il ritardo esistente di 150 ms;
il movimento del cursore aggiorna soltanto la visibilità delle righe che cambiano
stato, riutilizzando il risultato del parser.

## Rientri e continuazione degli elenchi

Gli elenchi puntati e numerati hanno un rientro sporgente: le righe lunghe si
allineano al testo dopo il marcatore. Anche le citazioni hanno un rientro;
le righe lunghe si allineano al testo dopo `>`. Il rientro è solo visivo e si
adatta al carattere, allo zoom e alla colonna di scrittura.

Con **Invio** dentro una voce, Tasto inserisce il marcatore sulla riga successiva:
`- voce` continua con `- `, `9. voce` con `10. ` e `9) voce` con `10) `.
Il tipo di punto, gli spazi e il rientro della sorgente vengono mantenuti.
**Invio su una voce vuota** rimuove il marcatore e termina l'elenco;
**Maiusc+Invio** inserisce un normale a capo senza continuarlo.
L'inserimento si annulla o ripete con una sola operazione. I blocchi di codice
non ricevono rientri di lista/citazione né continuazione automatica.

## Schermata iniziale

All'avvio trovi la biblioteca della cartella scelta e il consueto invito
**premi un TASTO**. Puoi riaprirla dall'ingranaggio → **Schermata iniziale**:
il documento aperto e la sua posizione vengono conservati finché non scegli
un altro file o un nuovo documento.

- **Cartella:** mostra il percorso; **Scegli** apre la selezione di cartella.
  La prima cartella proposta è `Tasto` dentro la cartella Documenti dell'utente.
- **Recenti:** gli ultimi cinque file Markdown aperti o salvati nella cartella
  selezionata, escludendo quelli rimossi o appartenenti ad altre cartelle.
- **Tutti i file:** sette file `.md` / `.markdown` in ordine alfabetico; **+**
  mostra altri sette file alla volta. I nomi sono cliccabili.

La composizione mantiene un unico sfondo e porta l'invito alla scrittura sopra
la biblioteca. Recenti e file sono disposti su due colonne allineate, con
intestazioni discrete, conteggio degli elementi e una sola linea di separazione.
Su finestre strette le sezioni si dispongono in verticale. I comandi da tastiera
restano visibili in fondo e il focus dei pulsanti è riconoscibile.

I criteri di leggibilità, larghezza contenuta e contrasto si ispirano alle
indicazioni W3C su [presentazione del testo](https://github.com/w3c/wcag/blob/main/understanding/20/visual-presentation.html)
e [contrasto](https://github.com/w3c/wcag/blob/main/understanding/20/contrast-minimum.html),
adattate all'interfaccia desktop e all'estetica tipografica di Tasto.

Cartella e cronologia vengono ricordate nelle preferenze. Una cartella vuota
o non più accessibile mostra un messaggio e permette di sceglierne un'altra.

**Tab / Shift+Tab** spostano il focus e **Invio** apre il file selezionato.
**Ctrl+O** apre un file, **Ctrl+N** crea un documento e **Ctrl+Shift+O** sceglie
la cartella quando la schermata iniziale è visibile. **Esc**, un clic
sull'invito o un tasto di scrittura riportano al documento, mantenendo il
comportamento dell'invito iniziale: il primo tasto chiude la schermata.
Se scegli un altro file con modifiche ancora da salvare, viene richiesta la
consueta scelta Salva / Scarta / Annulla.

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

Le scorciatoie di formato agiscono sul corpo del documento. **Ctrl+Shift+N**
aggiunge una nota anche se il focus è nella ricerca o nella barra laterale,
usando l’ultima posizione del cursore nel documento.

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

### Barra destra: Appunti e Note

Due schede nella parte alta della barra, **Appunti** e **Note**, selezionano
il contenuto: entrambe usano tutta l'altezza disponibile. La scelta viene
ricordata al riavvio; aggiungere una nota apre automaticamente la scheda Note.

Per modificare un appunto, premi **✎** sulla sua scheda: si apre lo stesso
editor sovrapposto delle note. **Salva l'appunto** o **Ctrl+Invio** salva le
modifiche; **Annulla** o **Esc** le scarta. Il documento centrale resta invariato.
Gli appunti modificati vengono salvati subito nel loro file JSON, con scrittura
atomica. Un errore di salvataggio lascia l'editor aperto e conserva il testo.

### Note a margine

Dal menu **+ → Aggiungi nota**, o con **Ctrl+Shift+N**, inserisci il richiamo
numerato al cursore. Si apre un editor sovrapposto al documento, centrato, senza bordi e distinto
tramite un'ombra. Premi **Salva la nota** o **Ctrl+Invio** per applicare il
contenuto, oppure **Annulla** / **Esc** per scartare le modifiche.
Aggiungere o modificare una nota conserva la posizione di lettura del documento.
La dimensione del pannello si adatta alla finestra (fino a circa 900 × 640 px).
La barra destra mostra l'elenco delle note: cliccando sul testo di una nota
torni al suo richiamo nel documento, che viene selezionato; **Modifica** apre
l'editor sovrapposto. Se il richiamo è ripetuto si raggiunge il primo.
Anche il percorso inverso funziona: un clic su `[^n]` nel corpo del documento
apre l'editor della relativa nota. Trascinare per selezionare il testo non apre
l'editor; i richiami negli esempi di codice non sono attivi.
Annullare una nota appena creata lascia una nota vuota, rimovibile con Ctrl+Z.
Durante la modifica, il documento sottostante è bloccato; per chiudere Tasto
occorre prima salvare o annullare la nota.

Le note appartengono al documento, a differenza degli appunti condivisi:
sono salvate come Markdown standard, con `[^1]` nel testo e `[^1]: contenuto`
in fondo al documento. Le definizioni sono visibili anche nel corpo del testo.
Modifiche e inserimenti seguono il normale salvataggio/autosalvataggio e sono
annullabili. I numeri seguono automaticamente la prima posizione dei richiami
nel testo. Inserendo una nota prima della 5, la nuova diventa 5 e la precedente
5 diventa 6: vengono aggiornati insieme richiami, definizioni ed elenco laterale.
La numerazione viene riordinata anche aprendo documenti esistenti.

Cancellare un richiamo completo rimuove la definizione quando non ci sono più
altri richiami alla stessa nota. **Backspace** subito dopo `[^n]` o **Canc**
subito prima lo elimina come unità. Puoi anche selezionarlo e cancellarlo.
Eliminare una definizione completa nel Markdown rimuove i richiami corrispondenti.
La rinumerazione e la cancellazione automatica fanno parte della stessa azione:
un solo **Ctrl+Z** ripristina testo, nota e numeri; **Ctrl+Y** ripete l'operazione.
Modifiche parziali alla sintassi non cancellano il contenuto della nota.
Le definizioni già prive di richiamo in un file importato vengono conservate.
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
- `tasto/library.py`: elenco dei file Markdown e recenti della cartella scelta.
- `tasto/footnotes.py`: lettura, creazione e modifica di note Markdown.
- `tasto/formatting.py`: trasformazioni Markdown usate dal menu +.
- `tasto/style.css`: stile estratto dal file originale; i segnaposto `@bg@`,
  `@fg@`, ecc. sono sostituiti da Python in base al tema.
- `tasto/document.py`: componente del precedente prototipo, conservato ma non
  utilizzato dall'interfaccia importata.
- `tests/test_document.py`: test del componente precedente, non test della nuova interfaccia.
- `tests/test_imported_source.py`: controlli di integrazione sul codice importato e sul CSS.

Da completare rispetto al progetto originale: cinque livelli di titoli,
sostituzione e spostamento delle sezioni. Attualmente eliminare un appunto
non richiede conferma.

Test senza interfaccia grafica:

```sh
python3 -m unittest discover -s tests -v
```

Collaudo della finestra e delle scorciatoie con eventi X11 reali su un display
virtuale isolato (dipendenze aggiuntive: `xvfb`, `xauth`, `libxtst6`):

```sh
xvfb-run -a /usr/bin/python3 tests/gtk_smoke.py
```

Il test usa cartelle temporanee per preferenze, appunti e bozze. Verifica
formattazione e annullamento, aggiunta note da tastiera e menu senza salti
di scorrimento, Ctrl+Invio, modifica e annullamento degli appunti, persistenza
su disco, gestione del salvataggio fallito, navigazione ai richiami e ripristino
della scheda destra al riavvio. Verifica inoltre rinumerazione per posizione,
clic nativo sui richiami, cancellazione collegata e recupero con annulla/ripeti,
incluso il caso di una nota con più richiami. Per la schermata iniziale controlla
cartella e cronologia persistenti, filtri per cartella, paginazione, apertura
da tastiera, ritorno al documento in corso, gestione della cartella assente e
passaggio fra colonne affiancate e sezioni verticali ridimensionando la finestra. Non eseguirlo sul display in uso: genera eventi
di tastiera. Nel cloud è stato eseguito con GTK 3, GtkSourceView 4 e Xvfb.

Il parser CSS di GTK 3 è stato verificato anche sulle 21 combinazioni di temi e font.
