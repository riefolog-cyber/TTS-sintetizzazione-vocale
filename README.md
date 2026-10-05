# 🎙️ Sintesi Vocale Multilingua (Kokoro + Microsoft Edge)

Applicazione web locale per generare **audio** e **video con sottotitoli** in
**9 lingue**, con **traduzione automatica** e **lettore karaoke sincronizzato**.
Versione corrente: **3.3**

---

## ✨ Funzionalità

- **9 lingue**: Italiano, English, Français, Español, Deutsch, Português, 日本語, 中文, Русский
- **64 voci** selezionabili (41 Microsoft Edge + 23 Kokoro)
- **2 motori**: Microsoft Edge TTS (online, qualità alta) e Kokoro (offline)
- **Traduzione automatica** prima della sintesi, gratuita e privata
- **Video MP4** con sottotitoli incisi + file **SRT** + immagine di sfondo personalizzabile
- **Lettore karaoke**: il testo viene **evidenziato frase per frase** mentre l'audio suona
- **Controllo di tono**: velocità, pitch (altezza) e volume
- **Qualità audio**: loudness normalizzato a −16 LUFS (standard dei servizi cloud)
- **Nessun limite di caratteri** (verificato oltre 6.000 caratteri)
- **Player integrato** con testo letto mostrato e sincronizzato

---

## ⚙️ Requisiti

| Componente | Requisito | Note |
|---|---|---|
| **Python** | 3.10 o 3.11 (64 bit) | Su Windows ARM serve la versione **x64** |
| **ffmpeg** | nel PATH | Serve per video, MP3 e normalizzazione |
| **Node.js** | non richiesto | — |

Funziona su **Windows, Linux e macOS**, sia su PC Intel/AMD sia Apple Silicon.

> ### ⚠️ Nota importante: Windows su ARM (Snapdragon)
> Il Python "predefinito" su questi PC è spesso **ARM64**, e **PyTorch non esiste
> per ARM64 su Windows**: `pip install torch` fallisce e l'app non può funzionare.
> Per questo `installa.bat` crea un ambiente con **Python 3.11 x64**, che gira
> correttamente tramite emulazione. **Non lanciare `python kokoro_app.py`**
> direttamente: usa sempre `avvia.bat`.

Verificare la presenza di ffmpeg con `ffmpeg -version`.

---

## 📦 Installazione

Doppio clic su **`installa.bat`** (solo la prima volta).

Cosa fa:
1. verifica che Python 3.11 x64 sia installato;
2. crea l'ambiente virtuale `.venv` nella cartella del progetto;
3. installa le dipendenze elencate in `requirements.txt`;
4. al primo avvio i modelli vengono scaricati automaticamente (~3 GB):
   - **Kokoro-82M** (voci e modello)
   - **NLLB-200 distilled 600M** (traduzione, ~2,4 GB)
   - **MarianMT opus-mt-it-en / en-it** (traduzione di riserva)

Installazione manuale equivalente:

```bash
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## ▶️ Avvio

**Windows** — doppio clic su **`avvia.bat`**
**Linux / macOS** — esegui **`./avvia.sh`**

Poi apri il browser su:

```
http://localhost:8885
```

### Linux e macOS

```bash
chmod +x installa.sh avvia.sh
./installa.sh
```

Lo script crea l'ambiente, installa le dipendenze e ti avvisa se manca
`ffmpeg`. Su Debian/Ubuntu per la sintesi offline con Kokoro serve anche:

```bash
sudo apt install ffmpeg espeak-ng
```

Per chiudere: terminare il processo Python (oppure `Ctrl+C` se avviato da
terminale). I log sono in `server.log` e `server_err.log`.

### Clonare su un altro PC

```bash
git clone <url-del-repository>
cd sintesi-vocale-multilingua
```

Poi esegui l'installazione per il tuo sistema (`installa.bat` o `./installa.sh`).
L'ambiente `.venv` e i modelli **non** sono nel repository e vengono ricreati:
al primo avvio verranno riscaricati (~3 GB).

> Il font dei sottotitoli viene cercato automaticamente su Windows, Linux e
> macOS: nessun percorso è legato a un sistema operativo specifico.

---

## 📖 Guida all'uso

1. **Testo** — incolla o scrivi il testo da leggere.
2. **🌐 Lingua del testo** — la lingua in cui è scritto il testo.
3. **🔊 Lingua della lettura** — la lingua in cui verrà letto.
4. **🎙️ Motore voce** — *Edge online* (qualità migliore) o *Kokoro offline*.
5. **🌍 Traduci automaticamente** — spunta per tradurre il testo nella lingua di lettura.
6. **Voce** — scegli tra le voci del motore e della lingua selezionati.
7. **Velocità / Tono / Volume** — regola il ritmo, l'altezza e il volume della voce.
8. **🔊 Anteprima** — prova la voce prima di generare.
9. **Genera** — scegli **Audio** o **Video**.
10. **🔤 Testo pronunciato** — ascolta con l'evidenziazione sincronizzata.

---

## 🔊 Motori di sintesi

| Motore | Rete | Lingue | Note |
|---|---|---|---|
| **Microsoft Edge** | ✅ necessaria | tutte e 9 | Qualità più alta, supporta tono/volume |
| **Kokoro (offline)** | ❌ non necessaria | IT, EN, FR, ES, PT, ZH | Per DE, JA, RU ricada su Edge |

Il **tono (pitch)** e il **volume** si applicano **solo al motore Edge**; i
cursori vengono nascosti automaticamente scegliendo Kokoro.

| Lingua | Voci Edge | Voci Kokoro |
|---|---|---|
| Italiano | 4 | 2 |
| English | 8 | 7 |
| Français | 5 | 1 |
| Español | 4 | 4 |
| Deutsch | 6 | — |
| Português | 5 | 4 |
| 日本語 | 2 | — |
| 中文 | 5 | 5 |
| Русский | 2 | — |

---

## 🌍 Traduzione

Catena automatica, con controllo di qualità su ogni frase:

```
1. Google Translate   → qualità massima (usato solo se la rete lo consente)
2. NLLB-200          → modello locale, 200 lingue
3. MarianMT          → modello locale di riserva (coppie IT↔EN)
```

Caratteristiche:
- **frase per frase**, per non perdere parti di testo;
- **validazione** dell'output: scarta risultati vuoti, corrotti o non tradotti e ripiega sul modello di riserva;
- **pulizia** di spazi, punteggiatura e maiuscole;
- **gratuita e privata**: senza Google, tutto avviene in locale.

> Se per una lingua non esiste un modello Marian dedicato si usa NLLB.

---

## 📤 Formati di output

| Formato | Caratteristiche |
|---|---|
| **WAV** | lossless, ~2,8 MB/min, normalizzato a −16 LUFS |
| **MP3** | 192 kbps, ~1,4 MB/min |
| **MP4** (video) | h264 1280×720 @ 24 fps + audio aac, sottotitoli incisi |
| **SRT** | file sottotitoli con tempi per frase |
| **WAV** (da video) | traccia audio del video |

Qualità video: **Veloce** (ultrafast 1,5M) · **Bilanciato** (medium 3M) · **Alta** (slow 5M).

---

## ⏱️ Limiti

- **Nessun limite di caratteri** imposed dall'app (verificato fino a 6.000+).
- Tempi indicativi su CPU (nessuna GPU richiesta):
  - Edge: ~40 s per 6.000 caratteri
  - Kokoro: ~21 s per 1.000 caratteri
- Nessun limite di tempo sulla generazione; l'interfaccia mostra l'avanzamento.
- L'anteprima usa le prime **100 caratteri** del testo.

---

## 🔒 Privacy

| Componente | Online? |
|---|---|
| Motore **Edge** | **Sì** — il testo è inviato ai server Microsoft |
| Motore **Kokoro** | No — tutto in locale |
| Traduzione **NLLB / MarianMT** | No — tutto in locale |
| Traduzione **Google** | Sì — solo se raggiungibile |
| Video, normalizzazione, sottotitoli | No — in locale |

Per una generazione **interamente in locale**: scegli il motore **Kokoro**.

---

## 📁 Struttura del progetto

```
kokoro_app.py      applicazione (unico file Python)
README.md          questa guida
requirements.txt   dipendenze
installa.bat       installazione (Windows)
avvia.bat          avvio (Windows)
installa.sh        installazione (Linux / macOS)
avvia.sh           avvio (Linux / macOS)
.venv/             ambiente virtuale Python 3.11 x64
server.log         log del server
server_err.log     errori del server
server.pid         PID del processo attivo
```

---

## ❓ Problemi frequenti

**`ModuleNotFoundError: No module named 'soundfile'`**
Stai usando il Python sbagliato. Lancia `avvia.bat`, non `python kokoro_app.py`.

**`ERROR: No matching distribution found for torch`**
Stai usando il Python ARM64. Serve Python **3.11 x64** (lo fa `installa.bat`).

**`ffmpeg non trovato nel PATH`**
Installa ffmpeg e assicurati che sia nel PATH. Senza ffmpeg resta disponibile
solo il WAV.

**Il giapponese non funziona con Kokoro**
`pyopenjtalk` richiede un compilatore e non è installabile su Windows. Usa il
motore **Edge** per il giapponese.

**Messaggi `PermissionError: espeak-ng.dll` all'uscita**
Normali e innocui: sono la pulizia dei file temporanei di eSpeak su Windows e
non influiscono sul funzionamento.

---

## 📄 Licenza e crediti

- Modello vocale: [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) — Apache 2.0
- Traduzione: [Helsinki-NLP MarianMT](https://huggingface.co/Helsinki-NLP) e [facebook/NLLB-200](https://huggingface.co/facebook/nllb-200-distilled-600M)
- Sintesi online: Microsoft Edge TTS
- Video: MoviePy · immagini: Pillow · interfaccia: Gradio

Tutti i componenti sono **gratuiti**.

Per chiudere: terminare il processo Python (oppure chiudere la finestra di
console). I log sono in `server.log` e `server_err.log`.

---
