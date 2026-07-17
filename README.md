# 🏋️ Bar Path Tracker (versione accurata con object tracking)

Web app prototipo per tracciare la traiettoria reale del bilanciere ("bar path")
durante esercizi come panca piana, squat o stacco, a partire da un video
registrato con lo smartphone.

- **Frontend + Backend**: Streamlit
- **Elaborazione video**: OpenCV
- **Tracciamento**: object tracking classico (CSRT), inizializzato dal punto
  che l'utente clicca sul bilanciere nel primo fotogramma
- **Encoding output**: imageio + ffmpeg (H.264, compatibile con i browser)

---

## 🎯 Cosa è cambiato rispetto alla prima versione

La versione precedente usava MediaPipe Pose per stimare la posizione del
polso e usarla come proxy del bilanciere. Funzionava, ma con due limiti:
impugnature larghe o inquadrature particolari rendevano il polso un
riferimento impreciso, e le troppe opzioni (modello, confidenze, smoothing,
scheletro...) rendevano l'app confusionaria.

Questa versione risolve entrambi i problemi:

1. **Più accurato**: non si stima più un punto del corpo, si traccia
   **direttamente l'oggetto scelto dall'utente** — un bordo del disco, un
   anello del bilanciere, un adesivo — tramite CSRT, l'algoritmo di object
   tracking più preciso disponibile in OpenCV. Il percorso disegnato è il
   movimento reale rilevato nel video, senza approssimazioni né smoothing
   artificiale che potrebbe farlo deviare dal movimento vero.
2. **Punto di partenza scelto dall'utente**: prima di elaborare il video,
   clicchi direttamente sul bilanciere nel primo fotogramma (con un'anteprima
   che mostra l'area che verrà seguita). Questo è ciò che rende il
   tracciamento molto più affidabile rispetto a un punto stimato
   automaticamente.
3. **Meno opzioni**: rimossi modello di pose estimation, scelta del polso,
   soglie di confidenza, smoothing, scheletro di debug. Sono rimaste solo le
   opzioni che contano davvero: dimensione dell'area da seguire, colore e
   spessore della linea.

MediaPipe non è più una dipendenza del progetto.

---

## 📁 Contenuto del pacchetto

```
bar-path-tracker/
├── app.py                   # applicazione Streamlit completa
├── requirements.txt         # dipendenze (compatibili con Python 3.14)
├── .streamlit/
│   └── config.toml          # tema grafico dell'app
└── README.md                # queste istruzioni
```

---

## 💻 1. Come testarlo in locale su Windows (Python 3.14)

### Requisiti
- **Python 3.14** installato e nel PATH (verifica con `python --version`).
- Windows 10/11.

### Passaggi

1. **Estrai** lo zip in una cartella, ad esempio `C:\Progetti\bar-path-tracker`.

2. **Apri il Prompt dei comandi (cmd) o PowerShell** in quella cartella.

3. **Crea un ambiente virtuale pulito**:

   ```powershell
   python -m venv venv
   ```

4. **Attiva l'ambiente virtuale**:

   ```powershell
   venv\Scripts\activate
   ```

   Se PowerShell blocca l'esecuzione degli script, esegui una volta come amministratore:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

5. **Aggiorna pip e installa le dipendenze**:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   Tutte le dipendenze hanno wheel precompilate per Python 3.14: non serve
   compilare nulla, ma opencv è un pacchetto pesante quindi richiede qualche
   minuto.

6. **Avvia l'app**:

   ```powershell
   streamlit run app.py
   ```

7. Il browser si aprirà su `http://localhost:8501`. Se non si apre da solo,
   copia l'indirizzo mostrato nel terminale.

8. **Carica un video di prova**, poi **clicca sul bilanciere** nell'immagine
   del primo fotogramma (scegli un dettaglio ad alto contrasto: bordo di un
   disco, adesivo, anello). Regola se serve la dimensione dell'area da
   seguire, poi premi **"Elabora Video"**.

### Consigli per un tracciamento accurato
- Clicca su un punto **ad alto contrasto** (bordo netto, angolo, adesivo
  colorato): un'area uniforme (es. il centro liscio di un disco) è più
  difficile da seguire.
- Registra con **inquadratura fissa** (treppiede o appoggio stabile).
- Il bilanciere deve essere **già visibile** nel primo fotogramma del video.
- Se il messaggio finale segnala che il tracciamento è stato "perso" per
  molti fotogrammi, riprova scegliendo un punto diverso o un'area
  leggermente più grande.

---

## ☁️ 2. Come pubblicarlo online gratuitamente

### Opzione A — Streamlit Community Cloud (consigliata, più semplice)

1. Crea un account gratuito su [share.streamlit.io](https://share.streamlit.io).
2. Crea un repository GitHub e carica tutti i file del progetto.
3. Su Streamlit Community Cloud clicca **"New app"**, seleziona il
   repository, il branch e il file principale `app.py`.
4. Clicca **Deploy**: dopo qualche minuto la web app sarà online con un link
   pubblico condivisibile. Grazie alle versioni `>=` nel `requirements.txt`,
   funziona con qualunque versione Python offra la piattaforma.

### Opzione B — Hugging Face Spaces

1. Crea un account gratuito su [huggingface.co](https://huggingface.co).
2. Crea un nuovo **Space** → scegli **SDK: Streamlit**.
3. Carica gli stessi file del progetto (`app.py`, `requirements.txt`,
   `.streamlit/config.toml`).
4. Lo Space farà il build e pubblicherà l'app con un link tipo
   `https://huggingface.co/spaces/<tuo-utente>/<nome-space>`.

> Nota: entrambe le piattaforme gratuite hanno limiti di RAM/CPU ragionevoli
> per un prototipo (video di pochi secondi/minuti). Per un uso più intensivo
> serve un piano a pagamento o un server dedicato.

---

## ⚠️ Limiti noti del prototipo

- Il tracciamento segue **il punto scelto sul primo fotogramma**: se il
  bilanciere esce completamente dall'inquadratura o viene oscurato a lungo
  (es. da un'altra persona), il tracker può perdere il riferimento. L'app
  segnala quanti fotogrammi sono stati persi a fine elaborazione.
- Video verticali con metadati di rotazione a volte non vengono gestiti
  correttamente da OpenCV: se il video appare ruotato, registra in
  orizzontale o pre-ruota il file.
- L'elaborazione avviene sul server (o sul tuo PC in locale): video lunghi o
  ad alta risoluzione richiedono più tempo. CSRT è accurato ma più lento di
  altri tracker: per un set di pochi secondi il tempo di elaborazione resta
  comunque contenuto.

---

## 🔧 Idee per evoluzioni future

- Selezione di un **rettangolo** (non solo un punto) per inizializzare il
  tracker con più precisione.
- Calcolo automatico di metriche (deviazione orizzontale massima, velocità
  media della fase concentrica/eccentrica).
- Possibilità di correggere manualmente il punto tracciato se il tracciamento
  viene perso a metà video, invece di dover ripartire da capo.
