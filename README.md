# Tasto

Prototipo di un editor Markdown minimale per Linux, scritto in Python e GTK 4.
Questa è una prima base di sviluppo: l'interfaccia grafica deve ancora essere
collaudata su un sistema con GTK 4 e un display disponibile.

## Avvio su Linux

Su Debian o Ubuntu, apri il Terminale e installa i componenti grafici:

```sh
sudo apt update
sudo apt install python3 python3-gi gir1.2-gtk-4.0
```

Entra nella cartella del progetto e avvia:

```sh
/usr/bin/python3 -m tasto
```

Non servono pip, un account o credenziali. Usa il Python di sistema perché
contiene il collegamento a GTK installato dal gestore dei pacchetti.

## Uso del prototipo

- Scrivi direttamente al centro della finestra.
- `Ctrl+N`: nuovo; `Ctrl+O`: apri; `Ctrl+S`: salva; `Ctrl+Shift+S`: salva con nome.
- `Ctrl+Q`: chiudi. Le modifiche non salvate richiedono conferma prima di essere scartate.
- Il pulsante ☰ mostra indice e ricerca della prima corrispondenza.
- Il pulsante + inserisce alcuni marcatori Markdown; seleziona il testo per grassetto, corsivo e barrato.
- Seleziona uno dei sette temi e usa ⚙ per carattere, dimensione e colonna.
- Il pulsante ▤ mostra appunti temporanei. **Gli appunti non vengono salvati e si perdono alla chiusura.**

Il testo resta Markdown visibile, senza anteprima renderizzata. Il salvataggio
usa UTF-8 e sostituisce il file solo dopo avere completato la scrittura.

## Percorso di sviluppo

1. Collaudare l'interfaccia GTK e migliorare apertura, salvataggio e recupero dei documenti.
2. Aggiungere obiettivi di scrittura e barra di progresso; persistenza delle preferenze.
3. Completare formattazione, sottolineato, rientri e note numerate.
4. Aggiungere indice collassabile, spostamento delle sezioni e ricerca con risultati e sostituzione.
5. Salvare appunti e note associati al documento, con modifica, conferma di eliminazione e reinserimento.
6. Completare schermata iniziale con cartella e recenti, evidenziazione per tema e suoni.
7. Rifinire accessibilità, distribuzione Linux e valutare macOS e Windows.

Queste voci sono lavoro futuro, non funzioni già disponibili.

## Test

Dalla cartella del progetto:

```sh
python3 -m unittest discover -s tests -v
```

I test verificano la gestione dei documenti senza dipendere da GTK.
La cartella `tasto` contiene il programma: `document.py` gestisce il testo e i file,
`app.py` costruisce la finestra. `tests` contiene le verifiche automatiche.
