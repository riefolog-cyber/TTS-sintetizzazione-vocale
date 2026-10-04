"""
Kokoro TTS Italiano — Audio & Video con sottotitoli
Sintesi vocale italiana + video MP4 con sottotitoli sincronizzati.
"""

__version__ = "3.3"  # v3.3: 9 lingue + controllo tono/pitch e volume

# ── Imports ──────────────────────────────────────────────────────────────────
import os
import re
import tempfile
import atexit
import subprocess
import time
import bisect
import urllib.request
import json
import base64
import threading
import unicodedata
from pathlib import Path
from importlib.metadata import version as _pkg_version, PackageNotFoundError

import numpy as np
import soundfile as sf
import gradio as gr
import asyncio
import edge_tts

# ── Costanti ─────────────────────────────────────────────────────────────────
SAMPLE_RATE = 24000
VIDEO_W, VIDEO_H = 1280, 720
BAR_H = 280
VIDEO_FPS = 24
CHARS_PER_SEC = 14
_UPDATE_CACHE_EXPIRY = 3600  # 1 ora
_ENC_THREADS = min(4, os.cpu_count() or 2)

_QUALITY_PRESETS = {
    "fast":     {"preset": "ultrafast", "bitrate": "1500k", "label": "Veloce"},
    "balanced": {"preset": "medium",    "bitrate": "3000k", "label": "Bilanciato"},
    "high":     {"preset": "slow",      "bitrate": "5000k", "label": "Alta"},
}

_MODIFIED = time.strftime("%d/%m/%Y %H:%M", time.localtime(os.path.getmtime(__file__)))

# ── Fix espeak-ng ────────────────────────────────────────────────────────────
try:
    import espeakng_loader
    dp = espeakng_loader.get_data_path()
    if dp and os.path.isdir(dp):
        os.environ.setdefault("ESPEAK_DATA_PATH", dp)
except Exception:
    pass

# ── Device detection ─────────────────────────────────────────────────────────
try:
    import torch
    _has_cuda = torch.cuda.is_available()
except ImportError:
    _has_cuda = False

# ── Kokoro TTS ───────────────────────────────────────────────────────────────
from kokoro import KPipeline

# ── ffmpeg check ─────────────────────────────────────────────────────────────
def _check_ffmpeg() -> bool:
    """Verifica che ffmpeg sia disponibile nel PATH."""
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

_has_ffmpeg = _check_ffmpeg()
if not _has_ffmpeg:
    print("ATTENZIONE: ffmpeg non trovato nel PATH. Video e MP3 non saranno disponibili.")

# ── Inizializzazione pipeline ────────────────────────────────────────────────
print("Inizializzazione Kokoro TTS...", flush=True)
try:
    _initial_pipeline = KPipeline(
        lang_code="i", repo_id="hexgrad/Kokoro-82M",
        device="cuda" if _has_cuda else "cpu",
    )
except TypeError:
    # KPipeline non supporta il parametro device
    _initial_pipeline = KPipeline(lang_code="i", repo_id="hexgrad/Kokoro-82M")

# ── Lingue / Motori / Voci ───────────────────────────────────────────────────
_LANG_LABELS = {
    "it": "Italiano", "en": "English", "fr": "Français", "es": "Español",
    "de": "Deutsch", "pt": "Português", "ja": "日本語", "zh": "中文",
    "ru": "Русский",
}
# codice lingua Kokoro (None = Kokoro non supporta questa lingua)
_LANG_CODES = {
    "it": "i", "en": "a", "fr": "f", "es": "e", "pt": "p", "zh": "z",
    "de": None, "ja": None, "ru": None,
}

# Voci Kokoro (offline) — solo lingue realmente supportate e verificate
_KOKORO_VOICES = {
    "it": [("Sara (F)", "if_sara"), ("Nicola (M)", "im_nicola")],
    "en": [
        ("Heart (F, US)", "af_heart"), ("Bella (F, US)", "af_bella"),
        ("Sarah (F, US)", "af_sarah"), ("Nicole (F, US)", "af_nicole"),
        ("Michael (M, US)", "am_michael"),
        ("Emma (F, UK)", "bf_emma"), ("George (M, UK)", "bm_george"),
    ],
    "fr": [("Siwis (F)", "ff_siwis")],
    "es": [
        ("Dora (F)", "ef_dora"), ("Sonia (F)", "ef_sonia"),
        ("Alex (M)", "em_alex"), ("Santa (M)", "em_santa"),
    ],
    "pt": [
        ("Dora (F, BR)", "pf_dora"), ("Surica (F, BR)", "pf_surica"),
        ("Alex (M, BR)", "pm_alex"), ("Santa (M, BR)", "pm_santa"),
    ],
    "zh": [
        ("Xiaobei (F)", "zf_xiaobei"), ("Xiaoxiao (F)", "zf_xiaoxiao"),
        ("Xiaoni (F)", "zf_xiaoni"), ("Yunjian (M)", "zm_yunjian"),
        ("Yunxi (M)", "zm_yunxi"),
    ],
}

# Voci Microsoft Edge (online, alta qualità) per lingua
_EDGE_VOICES = {
    "it": [
        ("Elsa (F)", "it-IT-ElsaNeural"),
        ("Isabella (F)", "it-IT-IsabellaNeural"),
        ("Diego (M)", "it-IT-DiegoNeural"),
        ("Giuseppe (M)", "it-IT-GiuseppeMultilingualNeural"),
    ],
    "en": [
        ("Aria (F, US)", "en-US-AriaNeural"),
        ("Emma (F, US)", "en-US-EmmaMultilingualNeural"),
        ("Jenny (F, US)", "en-US-JennyNeural"),
        ("Ava (F, US)", "en-US-AvaMultilingualNeural"),
        ("Guy (M, US)", "en-US-GuyNeural"),
        ("Andrew (M, US)", "en-US-AndrewMultilingualNeural"),
        ("Sonia (F, UK)", "en-GB-SoniaNeural"),
        ("Ryan (M, UK)", "en-GB-RyanNeural"),
    ],
    "fr": [
        ("Denise (F)", "fr-FR-DeniseNeural"),
        ("Eloise (F)", "fr-FR-EloiseNeural"),
        ("Vivienne (F)", "fr-FR-VivienneMultilingualNeural"),
        ("Rémy (M)", "fr-FR-RemyMultilingualNeural"),
        ("Henri (M)", "fr-FR-HenriNeural"),
    ],
    "es": [
        ("Elvira (F)", "es-ES-ElviraNeural"),
        ("Ximena (F)", "es-ES-XimenaNeural"),
        ("Álvaro (M)", "es-ES-AlvaroNeural"),
        ("Paloma (F, US)", "es-US-PalomaNeural"),
    ],
    "de": [
        ("Katja (F)", "de-DE-KatjaNeural"),
        ("Amala (F)", "de-DE-AmalaNeural"),
        ("Seraphina (F)", "de-DE-SeraphinaMultilingualNeural"),
        ("Killian (M)", "de-DE-KillianNeural"),
        ("Conrad (M)", "de-DE-ConradNeural"),
        ("Florian (M)", "de-DE-FlorianMultilingualNeural"),
    ],
    "pt": [
        ("Francisca (F, BR)", "pt-BR-FranciscaNeural"),
        ("Thalita (F, BR)", "pt-BR-ThalitaMultilingualNeural"),
        ("Antônio (M, BR)", "pt-BR-AntonioNeural"),
        ("Raquel (F, PT)", "pt-PT-RaquelNeural"),
        ("Duarte (M, PT)", "pt-PT-DuarteNeural"),
    ],
    "ja": [
        ("Nanami (F)", "ja-JP-NanamiNeural"),
        ("Keita (M)", "ja-JP-KeitaNeural"),
    ],
    "zh": [
        ("Xiaoxiao (F)", "zh-CN-XiaoxiaoNeural"),
        ("Xiaoyi (F)", "zh-CN-XiaoyiNeural"),
        ("Yunxi (M)", "zh-CN-YunxiNeural"),
        ("Yunyang (M)", "zh-CN-YunyangNeural"),
        ("Yunjian (M)", "zh-CN-YunjianNeural"),
    ],
    "ru": [
        ("Svetlana (F)", "ru-RU-SvetlanaNeural"),
        ("Dmitry (M)", "ru-RU-DmitryNeural"),
    ],
}


def voices_for(engine: str, lang: str) -> list:
    """Voci (etichetta, id) per motore e lingua. Lista vuota = non supportata."""
    table = _KOKORO_VOICES if engine == "kokoro" else _EDGE_VOICES
    return list(table.get(lang, []))


def engine_supports(engine: str, lang: str) -> bool:
    """True se il motore ha almeno una voce per quella lingua."""
    return bool(voices_for(engine, lang))


# Unione di tutte le voci: usata dal menu "Voce" così il valore inviato al
# server è sempre valido (evita errori di validazione se si genera durante
# il cambio di motore/lingua).
_ALL_VOICES: list = []
for _eng_name, _table in (("Edge", _EDGE_VOICES), ("Kokoro", _KOKORO_VOICES)):
    for _lg, _lname in _LANG_LABELS.items():
        for _lbl, _vid in _table.get(_lg, []):
            _ALL_VOICES.append((f"{_lbl} · {_lname} · {_eng_name}", _vid))


# Compatibilità con il resto del codice (default: Edge italiano)
_VOICE_LIST = voices_for("edge", "it")

# Pre-carica le voci Kokoro italiane all'avvio
print("Pre-caricamento voci...", end=" ", flush=True)
for _label, v in _KOKORO_VOICES["it"]:
    try:
        _initial_pipeline.load_voice(v)
    except Exception as e:
        print(f"\nAttenzione: impossibile caricare '{v}': {e}")
print("OK!")
print("Kokoro TTS pronto!")

# ── Pipeline management (Kokoro, per lingua e device) ────────────────────────
_pipelines: dict = {}
if _initial_pipeline is not None:
    _pipelines[("it", "cuda" if _has_cuda else "cpu")] = _initial_pipeline


def get_pipeline(device: str = "auto", lang: str = "it"):
    """Restituisce la pipeline Kokoro per lingua/device richiesti (con cache)."""
    if device == "auto":
        device = "cuda" if _has_cuda else "cpu"
    key = (lang, device)
    if key not in _pipelines:
        print(f"Carico pipeline Kokoro lang={lang} device={device}...", flush=True)
        code = _LANG_CODES.get(lang) or "i"
        try:
            p = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M", device=device)
        except TypeError:
            # KPipeline non supporta il parametro device
            p = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M")
        for _label, v in _KOKORO_VOICES.get(lang, []):
            try:
                p.load_voice(v)
            except Exception:
                pass
        _pipelines[key] = p
    return _pipelines[key]

# ── MoviePy + PIL ────────────────────────────────────────────────────────────
from moviepy.video.VideoClip import VideoClip
from PIL import Image, ImageDraw, ImageFont

# ── Font cache ───────────────────────────────────────────────────────────────
_font_cache: dict = {}

def _get_font(size: int):
    """Restituisce un font della dimensione specificata (con cache)."""
    if size not in _font_cache:
        for f in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"]:
            if os.path.exists(f):
                try:
                    _font_cache[size] = ImageFont.truetype(f, size)
                    break
                except Exception:
                    pass
        if size not in _font_cache:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]

# ── Aggiornamenti ────────────────────────────────────────────────────────────
_update_cache: dict = {}

def _check_kokoro_pkg():
    """Controlla PyPI per aggiornamenti del pacchetto kokoro."""
    try:
        installed = _pkg_version("kokoro")
    except PackageNotFoundError:
        installed = "?"
    try:
        url = "https://pypi.org/pypi/kokoro/json"
        req = urllib.request.Request(url, headers={"User-Agent": f"KokoroApp/{__version__}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        latest = data["info"]["version"]
        needs = (installed != "?" and installed != latest)
        return installed, latest, needs, None
    except Exception as e:
        return installed, "?", False, str(e)

def _check_kokoro_model():
    """Controlla Hugging Face per aggiornamenti del modello."""
    try:
        url = "https://huggingface.co/api/models/hexgrad/Kokoro-82M"
        req = urllib.request.Request(url, headers={"User-Agent": f"KokoroApp/{__version__}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        lm = data.get("lastModified", "?")
        s  = data.get("sha", "?")[:7]
        return lm, s, None
    except Exception as e:
        return "?", "?", str(e)

def _build_update_html() -> str:
    """Esegue i check e restituisce HTML per il banner aggiornamenti."""
    cached = _update_cache.get("html")
    cached_ts = _update_cache.get("ts", 0)
    if cached and (time.time() - cached_ts) < _UPDATE_CACHE_EXPIRY:
        return cached

    # Esegui i due check in parallelo
    results = {}
    def _run_pypi():
        results["pypi"] = _check_kokoro_pkg()
    def _run_hf():
        results["hf"] = _check_kokoro_model()
    t1 = threading.Thread(target=_run_pypi, daemon=True)
    t2 = threading.Thread(target=_run_hf, daemon=True)
    t1.start(); t2.start()
    t1.join(timeout=10); t2.join(timeout=10)
    installed, latest, needs, err1 = results.get("pypi", ("?", "?", False, "timeout"))
    lm, sha, err2 = results.get("hf", ("?", "?", "timeout"))
    parts = ['<div style="border:1px solid #334155;border-radius:10px;padding:12px 18px;background:#1e293b;font-size:0.85rem;line-height:1.6;color:#e2e8f0">',
             '<strong style="font-size:0.92rem;color:#f1f5f9">🔍 Stato aggiornamenti</strong><br>']
    if not err1:
        if needs:
            parts.append(f'<span style="color:#fbbf24">⚠️</span> <b style="color:#f1f5f9">kokoro</b>: v{installed} → <b style="color:#fbbf24">v{latest}</b> disponibile! '
                         f'<code style="background:#0f172a;color:#fbbf24;padding:2px 6px;border-radius:4px">pip install --upgrade kokoro</code><br>')
        else:
            parts.append(f'<span style="color:#4ade80">✅</span> <b style="color:#f1f5f9">kokoro</b>: v{installed} (aggiornato)<br>')
    else:
        parts.append(f'<span style="color:#94a3b8">❓</span> <b style="color:#f1f5f9">kokoro</b>: impossibile controllare ({err1})<br>')
    if not err2:
        parts.append(f'<span style="color:#94a3b8">📦</span> <b style="color:#f1f5f9">Modello HF</b>: {lm} <span style="color:#94a3b8">(sha: {sha})</span><br>')
    else:
        parts.append(f'<span style="color:#94a3b8">❓</span> <b style="color:#f1f5f9">Modello HF</b>: impossibile controllare ({err2})<br>')
    parts.append(f'<span style="color:#64748b;font-size:0.78rem">📋 App: v{__version__} ({_MODIFIED})</span>')
    parts.append('</div>')
    html = "".join(parts)
    _update_cache["html"] = html
    _update_cache["ts"] = time.time()
    return html

def _refresh_updates():
    """Pulisce la cache e riesegue i check."""
    global _update_cache
    _update_cache = {}
    return _build_update_html()

# ── Cleanup ──────────────────────────────────────────────────────────────────
_TEMP_FILES: list[str] = []

def _cleanup():
    for p in _TEMP_FILES:
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass

atexit.register(_cleanup)

def _cleanup_old_temps(max_age_seconds: int = 3600):
    """Rimuove i file temporanei più vecchi di max_age_seconds."""
    now = time.time()
    for p in list(_TEMP_FILES):
        try:
            if os.path.exists(p) and (now - os.path.getmtime(p)) > max_age_seconds:
                os.remove(p)
                _TEMP_FILES.remove(p)
        except OSError:
            pass

# ── Helper functions ─────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    text = text.strip()
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    return text.strip()

def _make_gradient(bg_top: tuple, bg_bottom: tuple,
                   W: int = VIDEO_W, H: int = VIDEO_H) -> Image.Image:
    """Precomputa l'immagine di sfondo gradiente (una sola volta)."""
    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        ratio = y / H
        r = int(bg_top[0] * (1 - ratio) + bg_bottom[0] * ratio)
        g = int(bg_top[1] * (1 - ratio) + bg_bottom[1] * ratio)
        b = int(bg_top[2] * (1 - ratio) + bg_bottom[2] * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img

def _parse_color(hex_color: str) -> tuple[int, int, int, int]:
    """Converte un colore hex in tuple RGBA."""
    if not hex_color:
        return (255, 255, 255, 255)
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b, 255)
    return (255, 255, 255, 255)

def _to_numpy(audio) -> np.ndarray:
    """Converte torch.Tensor o numpy array in numpy float32."""
    if hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()
    arr = np.asarray(audio)
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return arr

def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _build_srt(times: list, texts: list) -> str:
    """Costruisce contenuto SRT da lista di (start, end) e testi."""
    lines = []
    for i, ((st, et), txt) in enumerate(zip(times, texts), 1):
        lines.append(str(i))
        lines.append(f"{_format_srt_time(st)} --> {_format_srt_time(et)}")
        lines.append(txt)
        lines.append("")
    return "\n".join(lines)

# ── Draw frame with subtitles ────────────────────────────────────────────────
def _draw_frame(
    bg_img: Image.Image,
    texts: list[str],
    active_idx: int,
    W: int = VIDEO_W,
    H: int = VIDEO_H,
    bar_h: int = BAR_H,
    font=None,
    font_size: int = 40,
    text_color: tuple = (255, 255, 255, 255),
    shadow_color: tuple = (0, 0, 0, 180),
    bar_color: tuple = (0, 0, 0, 160),
) -> np.ndarray:
    # Copia sfondo precomputato (molto più veloce di ridisegnare il gradiente)
    img = bg_img.copy()
    draw2 = ImageDraw.Draw(img, "RGBA")

    # Subtitle bar
    bar = Image.new("RGBA", (W, bar_h), bar_color)
    img.paste(bar, (0, H - bar_h), bar)

    # Active sentence
    if 0 <= active_idx < len(texts):
        txt = texts[active_idx]
        # Wrap long text
        words = txt.split()
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            bb = font.getbbox(test)
            if bb and (bb[2] - bb[0]) < W - 120:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)

        # Centra verticalmente nella barra
        line_h = int(font_size * 1.2)
        total_h = len(lines) * line_h
        y_start = H - bar_h + (bar_h - total_h) // 2

        y = y_start
        for line in lines:
            bb = font.getbbox(line)
            tw = (bb[2] - bb[0]) if bb else 0
            x = (W - tw) // 2
            draw2.text((x + 2, y + 2), line, font=font, fill=shadow_color)
            draw2.text((x, y), line, font=font, fill=text_color)
            y += line_h

    return np.array(img)

# ── Audio helpers ────────────────────────────────────────────────────────────
def _run_async(coro):
    """Esegue una coroutine in un thread dedicato (sicuro dentro Gradio)."""
    box: dict = {}

    def _worker():
        try:
            box["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001
            box["e"] = e

    th = threading.Thread(target=_worker)
    th.start()
    th.join()
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _decode_to_pcm(path: str) -> np.ndarray:
    """Decodifica un file audio in PCM numpy float32 mono a SAMPLE_RATE."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le",
           "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode != 0 or not r.stdout:
        err = r.stderr.decode(errors="ignore")[:200]
        raise gr.Error(f"Errore decodifica audio: {err}")
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _loudnorm_wav(wav_path: str, target_lufs: float = -16.0) -> str:
    """Normalizza il loudness (EBU R128, come i servizi cloud). Ritorna il nuovo WAV."""
    if not _has_ffmpeg:
        return wav_path
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-af",
           f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
           "-ar", str(SAMPLE_RATE), out]
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    if r.returncode != 0:
        return wav_path
    _TEMP_FILES.append(out)
    return out


# ── Sintesi ──────────────────────────────────────────────────────────────────
def _edge_synthesize(text: str, voice: str, speed: float,
                     pitch: float = 0.0, volume: float = 0.0):
    """Sintesi con Microsoft Edge TTS. Ritorna (audio float32, segmenti)."""
    rate_pct = int(round((speed - 1.0) * 100))
    pitch_hz = int(round(pitch))
    volume_pct = int(round(volume))
    mp3_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    segments: list = []

    async def _run():
        communicate = edge_tts.Communicate(
            text, voice,
            rate=f"{rate_pct:+d}%",
            pitch=f"{pitch_hz:+d}Hz",
            volume=f"{volume_pct:+d}%",
            boundary="SentenceBoundary",
        )
        with open(mp3_path, "wb") as f:
            async for chunk in communicate.stream():
                ctype = chunk["type"]
                if ctype == "audio":
                    f.write(chunk["data"])
                elif ctype == "SentenceBoundary":
                    st = chunk["offset"] / 1e7
                    en = (chunk["offset"] + chunk["duration"]) / 1e7
                    segments.append((chunk["text"], st, en))

    _run_async(_run())
    _TEMP_FILES.append(mp3_path)
    audio = _decode_to_pcm(mp3_path)
    return audio, segments


def _kokoro_synthesize(text: str, voice: str, speed: float, device: str, progress=None):
    """Sintesi con Kokoro (offline). Ritorna (audio float32, segmenti)."""
    pipe = get_pipeline(device)
    clean = _normalize(text)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    n_est = max(1, len(sentences))
    gen = pipe(clean, voice=voice, speed=speed, split_pattern=r'(?<=[.!?])\s+')
    texts, audios = [], []
    for i, (gs, _ps, audio) in enumerate(gen):
        if progress:
            progress((i + 1) / n_est * 0.9, desc=f"Sintesi audio {i+1}/{n_est}...")
        texts.append(gs)
        audios.append(_to_numpy(audio))
    if not audios:
        raise gr.Error("Nessun audio generato.")
    full = np.concatenate(audios)
    segments, cursor = [], 0.0
    for t, a in zip(texts, audios):
        d = len(a) / SAMPLE_RATE
        segments.append((t, cursor, cursor + d))
        cursor += d
    return full, segments


def synthesize(text: str, voice: str, speed: float, device: str, engine: str,
                progress=None, pitch: float = 0.0, volume: float = 0.0):
    """Sintetizza con il motore scelto. Ritorna (audio float32, segmenti)."""
    if engine == "kokoro":
        return _kokoro_synthesize(text, voice, speed, device, progress)
    full, segments = _edge_synthesize(text, voice, speed, pitch, volume)
    if not segments:
        segments = [(text.strip(), 0.0, len(full) / SAMPLE_RATE)]
    return full, segments


# ── Traduzione: cascata Google -> NLLB -> MarianMT (tutto validato) ─────────
_mt_cache: dict = {}
_nllb_cache: dict = {}
_google_ok: bool | None = None   # None = non ancora verificato

# codici lingua NLLB-200
_NLLB_CODES = {
    "it": "ita_IT", "en": "eng_Latn", "fr": "fra_Latn", "es": "spa_Latn",
    "de": "deu_Latn", "pt": "por_Latn", "ja": "jpn_Jpan", "zh": "zho_Hans",
    "ru": "rus_Cyrl",
}
_GOOGLE_CODES = {
    "it": "it", "en": "en", "fr": "fr", "es": "es", "de": "de",
    "pt": "pt", "ja": "ja", "zh": "zh-CN", "ru": "ru",
}
# coppie per cui esiste un modello MarianMT dedicato
_MARIAN_PAIRS = {("it", "en"), ("en", "it")}
_NLLB_NAME = "facebook/nllb-200-distilled-600M"


def _get_translator(src: str, tgt: str):
    key = (src, tgt)
    if key not in _mt_cache:
        from transformers import MarianMTModel, MarianTokenizer
        name = f"Helsinki-NLP/opus-mt-{src}-{tgt}"
        print(f"Carico modello di traduzione {name}...", flush=True)
        tok = MarianTokenizer.from_pretrained(name)
        model = MarianMTModel.from_pretrained(name)
        model.eval()
        _mt_cache[key] = (tok, model)
    return _mt_cache[key]


def _looks_broken(out: str, src_text: str = "") -> bool:
    """Rileva output non valido (vuoto, spazzatura, troncato)."""
    t = (out or "").strip()
    if len(t) < 2:
        return True
    letters = sum(ch.isalpha() for ch in t)
    if letters < max(2, len(t) * 0.35):
        return True
    # simboli/emoji/selector: tipici output corrotti
    weird = sum(1 for ch in t
                if unicodedata.category(ch) in ("So", "Cs", "Co") or ch == "️")
    if weird > 2:
        return True
    # troncamento eccessivo rispetto al testo sorgente
    if src_text and len(t) < len(src_text.strip()) * 0.35:
        return True
    # non tradotto: output identico all'originale su frasi significative
    if src_text:
        no = re.sub(r"\W+", "", t.lower())
        ns = re.sub(r"\W+", "", src_text.lower())
        if no and no == ns and len(src_text.split()) >= 4:
            return True
    return False


def _postprocess(txt: str) -> str:
    """Pulisce l'output: spazi, punteggiatura, maiuscole."""
    t = re.sub(r"\s+", " ", txt).strip()
    t = re.sub(r"\s+([.,!?;:])", r"\1", t)
    t = re.sub(r"([.!?]\s+)([a-zà-öø-ÿ])",
               lambda m: m.group(1) + m.group(2).upper(), t)
    if t:
        t = t[0].upper() + t[1:]
    return t


def _translate_marian(sentences: list, src: str, tgt: str) -> list:
    """Traduce frase per frase con MarianMT (evita perdita di contenuto)."""
    import torch
    tok, model = _get_translator(src, tgt)
    out = []
    for s in sentences:
        batch = tok([s], return_tensors="pt", padding=True, truncation=True, max_length=512)
        with torch.no_grad():
            gen = model.generate(
                **batch, max_new_tokens=512,
                num_beams=4, no_repeat_ngram_size=3,
            )
        txt = tok.batch_decode(gen, skip_special_tokens=True)[0].strip()
        # sicurezza: se l'output e' rotto o vuoto si tiene il testo originale
        out.append(txt if not _looks_broken(txt, s) else s)
    return out


def _get_nllb():
    if "model" not in _nllb_cache:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        print(f"Carico modello di traduzione {_NLLB_NAME}...", flush=True)
        _nllb_cache["tok"] = AutoTokenizer.from_pretrained(_NLLB_NAME)
        _nllb_cache["model"] = AutoModelForSeq2SeqLM.from_pretrained(_NLLB_NAME)
        _nllb_cache["model"].eval()
    return _nllb_cache["tok"], _nllb_cache["model"]


def _translate_nllb(sentences: list, src: str, tgt: str) -> list:
    """Traduce con NLLB-200 (qualita' superiore a Marian su IT->EN)."""
    import torch
    tok, model = _get_nllb()
    tok.src_lang = _NLLB_CODES.get(src, "ita_IT")
    bos = tok.convert_tokens_to_ids(_NLLB_CODES.get(tgt, "eng_Latn"))
    out = []
    for s in sentences:
        enc = tok([s], return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            gen = model.generate(
                **enc, forced_bos_token_id=bos, max_new_tokens=512,
                num_beams=4, no_repeat_ngram_size=3,
            )
        out.append(tok.batch_decode(gen, skip_special_tokens=True)[0].strip())
    return out


def _google_reachable() -> bool:
    """Verifica una volta sola se Google Translate e' utilizzabile."""
    global _google_ok
    if _google_ok is None:
        try:
            from deep_translator import GoogleTranslator
            r = GoogleTranslator(source="it", target="en").translate("Prova.")
            _google_ok = bool(r and r.strip())
        except Exception:
            _google_ok = False
        if not _google_ok:
            print("Google Translate non disponibile: uso MarianMT offline.", flush=True)
    return bool(_google_ok)


def _nllb_validated(sentences: list, src: str, tgt: str, use_marian: bool) -> list:
    """NLLB con validazione; le frasi non valide tornano a Marian o all'originale."""
    try:
        cand = _translate_nllb(sentences, src, tgt)
    except Exception:  # noqa: BLE001
        cand = [None] * len(sentences)
    bad = [i for i, t in enumerate(cand) if not t or _looks_broken(t, sentences[i])]
    if bad:
        if use_marian:
            fixed = _translate_marian([sentences[i] for i in bad], src, tgt)
            for i, f in zip(bad, fixed):
                cand[i] = f
        else:
            for i in bad:
                cand[i] = sentences[i]
    return [c for c in cand if c]


def translate_text(text: str, src: str, tgt: str) -> str:
    """Traduce con la miglior qualita' disponibile, senza perdere contenuto."""
    global _google_ok
    if src == tgt or not text.strip():
        return text
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
    if not sentences:
        return text

    # 1) Google Translate: qualita' massima (se la rete lo permette)
    if _google_reachable():
        try:
            from deep_translator import GoogleTranslator
            tr = GoogleTranslator(
                source=_GOOGLE_CODES.get(src, src),
                target=_GOOGLE_CODES.get(tgt, tgt),
            )
            out = []
            for s in sentences:
                try:
                    r = (tr.translate(s) or "").strip()
                except Exception:
                    r = ""
                out.append(r if not _looks_broken(r, s) else s)
            return _postprocess(" ".join(out))
        except Exception:
            _google_ok = False   # da qui in poi solo offline

    # 2) Motore offline migliore (misurato):
    #    - IT->EN : NLLB-200 nettamente superiore (Marian come riserva)
    #    - EN->IT : MarianMT piu' affidabile (NLLB lascia frasi in inglese)
    #    - altre  : solo NLLB (nessun modello Marian dedicato)
    if (src, tgt) in _MARIAN_PAIRS:
        if src == "it":
            return _postprocess(" ".join(
                _nllb_validated(sentences, src, tgt, use_marian=True)))
        return _postprocess(" ".join(_translate_marian(sentences, src, tgt)))

    return _postprocess(" ".join(
        _nllb_validated(sentences, src, tgt, use_marian=False)))


# ── Lettore sincronizzato (karaoke) ──────────────────────────────────────────
_HEAD_HTML = """
<style>
.kokoro-player audio { width: 100%; margin-bottom: 10px; }
.kokoro-transcript { max-height: 300px; overflow-y: auto; line-height: 2.0;
                     font-size: 1.05rem; padding: 6px 2px; }
.kokoro-transcript span { padding: 2px 6px; border-radius: 6px;
                          transition: background .15s, color .15s; }
.kokoro-transcript span.kokoro-active { background: #2563eb; color: #ffffff;
                                        font-weight: 600; }
</style>
<script>
window.kokoroSetup = function () {
  document.querySelectorAll('.kokoro-player').forEach(function (root) {
    if (root.dataset.kokoroReady === '1') return;
    var audio = root.querySelector('audio');
    var spans = root.querySelectorAll('.kokoro-transcript span');
    if (!audio || !spans.length) return;
    root.dataset.kokoroReady = '1';
    var segs = [];
    try { segs = JSON.parse(root.getAttribute('data-segs') || '[]'); } catch (e) { segs = []; }
    var last = -1;
    function update() {
      var t = audio.currentTime, active = -1;
      for (var i = 0; i < segs.length; i++) {
        if (t >= segs[i].s - 0.05 && t < segs[i].e) { active = i; break; }
      }
      if (active === last) return;
      last = active;
      spans.forEach(function (sp) {
        var on = parseInt(sp.getAttribute('data-i'), 10) === active;
        sp.classList.toggle('kokoro-active', on);
        if (on) { sp.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
      });
    }
    audio.addEventListener('timeupdate', update);
    audio.addEventListener('seeked', update);
    audio.addEventListener('play', update);
    update();
  });
};
</script>
"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _audio_to_b64(path: str, bitrate: str = "64k") -> str:
    """Restituisce l'audio in base64 (MP3 compatto) per l'embed nel browser."""
    src = path
    if _has_ffmpeg:
        mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        r = subprocess.run(["ffmpeg", "-y", "-i", path, "-c:a", "libmp3lame",
                            "-b:a", bitrate, "-ac", "1", mp3],
                           capture_output=True, timeout=180)
        if r.returncode == 0:
            _TEMP_FILES.append(mp3)
            src = mp3
    with open(src, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _build_player_html(segments: list, audio_path: str):
    """Costruisce il lettore con testo evidenziato in sincrono con l'audio."""
    if not segments or not audio_path or not os.path.exists(audio_path):
        return ""
    try:
        b64 = _audio_to_b64(audio_path)
    except Exception:  # noqa: BLE001
        return ""
    seg_json = json.dumps([{"s": round(s, 3), "e": round(e, 3)} for _t, s, e in segments])
    spans = "".join(
        f"<span data-i='{i}'>{_html_escape(t)}</span> "
        for i, (t, _s, _e) in enumerate(segments)
    )
    return (
        f"<div class='kokoro-player' data-segs='{seg_json}'>"
        f"<audio controls preload='metadata' src='data:audio/mpeg;base64,{b64}'></audio>"
        f"<div class='kokoro-transcript'>{spans}</div>"
        f"</div>"
    )


def _pct_to_db(pct: float) -> float:
    """Converte la percentuale di volume in dB (+30% = 1.3× ≈ +2.3 dB)."""
    gain = max(0.05, 1.0 + float(pct) / 100.0)
    return float(20.0 * np.log10(gain))


def _apply_gain(wav_path: str, volume_pct: float) -> str:
    """Applica il volume richiesto DOPO la normalizzazione (che altrimenti lo annullerebbe)."""
    if not volume_pct:
        return wav_path
    try:
        data, sr = sf.read(wav_path, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        gain = max(0.05, 1.0 + float(volume_pct) / 100.0)
        data = np.clip(data * gain, -1.0, 1.0)
        out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        sf.write(out, data, sr)
        _TEMP_FILES.append(out)
        return out
    except Exception:  # noqa: BLE001
        return wav_path


# ── Generate Video ───────────────────────────────────────────────────────────
def generate_video(
    text: str,
    voice: str,
    speed: float,
    bg_image=None,
    video_quality: str = "fast",
    sub_font_size: int = 40,
    sub_text_color: str = "#ffffff",
    sub_bg_opacity: int = 160,
    device: str = "auto",
    engine: str = "edge",
    pitch: float = 0.0,
    volume: float = 0.0,
    progress=gr.Progress(),
) -> tuple[str, str | None, str, list]:
    """Ritorna (video_path, srt_path, wav_path, segmenti)."""
    if not text.strip():
        raise gr.Error("Inserisci del testo.")

    try:
        _cleanup_old_temps()
        progress(0, desc="Sintesi audio...")
        full_audio, segments = synthesize(text, voice, speed, device, engine,
                                         progress, pitch, volume)
        texts = [s[0] for s in segments]
        times = [(s[1], s[2]) for s in segments]
        duration = len(full_audio) / SAMPLE_RATE

        # --- Sfondo: immagine o gradiente (precomputato una sola volta) ---
        bg_pil = None
        if bg_image is not None:
            bg_pil = bg_image.convert("RGB").resize(
                (VIDEO_W, VIDEO_H - BAR_H),
                getattr(Image, "Resampling", Image).LANCZOS,
            )

        # --- Palette colore (fallback se no immagine) ---
        if voice.startswith("if_sara"):
            palette = [(20, 30, 50), (40, 60, 100)]   # blu
        else:
            palette = [(30, 40, 30), (50, 70, 50)]     # verde (Nicola)

        # Precomputa sfondo
        if bg_pil is not None:
            bg_precomputed = Image.new("RGB", (VIDEO_W, VIDEO_H), (10, 10, 15))
            bg_precomputed.paste(bg_pil, (0, 0))
            bar_color = (15, 15, 25, sub_bg_opacity)
        else:
            bg_precomputed = _make_gradient(palette[0], palette[1])
            bar_color = (0, 0, 0, sub_bg_opacity)

        # Font e colori sottotitoli
        font = _get_font(sub_font_size)
        text_color_rgba = _parse_color(sub_text_color)

        # Ricerca attiva con bisect (O(log n) invece di O(n))
        starts = [st for st, _ in times]

        def make_frame(t):
            active = bisect.bisect_right(starts, t) - 1
            if active < 0:
                active = 0
            if active >= len(times):
                active = len(times) - 1
            return _draw_frame(
                bg_precomputed, texts, active,
                font=font, font_size=sub_font_size,
                text_color=text_color_rgba,
                bar_color=bar_color,
            )

        # Scrivi WAV intermedio (int16, 24000 Hz)
        wav_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        full_int16 = np.clip(full_audio * 32767, -32768, 32767).astype(np.int16)
        sf.write(wav_path, full_int16, SAMPLE_RATE)
        _TEMP_FILES.append(wav_path)

        # Genera video SENZA audio
        progress(0.4, desc="Rendering video...")
        try:
            # MoviePy 2.x usa 'frame_function'
            clip = VideoClip(frame_function=make_frame, duration=duration)
        except TypeError:
            # MoviePy 1.x usa 'make_frame'
            clip = VideoClip(make_frame=make_frame, duration=duration)
        video_no_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        qset = _QUALITY_PRESETS.get(video_quality, _QUALITY_PRESETS["fast"])
        clip.write_videofile(
            video_no_audio, fps=VIDEO_FPS, codec="libx264",
            preset=qset["preset"], bitrate=qset["bitrate"],
            threads=_ENC_THREADS, logger=None, audio_codec=None,
        )
        clip.close()
        _TEMP_FILES.append(video_no_audio)

        # Merge video + WAV con ffmpeg
        progress(0.8, desc="Merge audio-video...")
        out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_no_audio,
            "-i", wav_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-ar", str(SAMPLE_RATE),
            "-b:a", "192k",
            # normalizza l'audio del video e poi applica il volume scelto
            "-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,volume={_pct_to_db(volume):.2f}dB",
            "-shortest",
            out.name,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            err = result.stderr.decode(errors="ignore")[:300]
            raise gr.Error(f"Errore encoding audio: {err}")
        _TEMP_FILES.append(out.name)

        # --- SRT ---
        srt_path = None
        if texts and times:
            srt_content = _build_srt(times, texts)
            srt_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt")
            Path(srt_tmp.name).write_text(srt_content, encoding="utf-8")
            srt_path = srt_tmp.name
            _TEMP_FILES.append(srt_path)

        progress(1.0, desc="Completato!")
        return out.name, srt_path, wav_path, segments

    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Errore video ({type(e).__name__}): {e}")

# ── Generate Audio ───────────────────────────────────────────────────────────
def generate_audio(
    text: str,
    voice: str,
    speed: float,
    audio_fmt: str = "wav",
    device: str = "auto",
    engine: str = "edge",
    pitch: float = 0.0,
    volume: float = 0.0,
    progress=gr.Progress(),
) -> tuple[str, list]:
    if not text.strip():
        raise gr.Error("Inserisci del testo.")
    try:
        _cleanup_old_temps()
        progress(0, desc="Sintesi audio...")
        full, _segments = synthesize(text, voice, speed, device, engine,
                                     progress, pitch, volume)
        full_int16 = np.clip(full * 32767, -32768, 32767).astype(np.int16)
        wav_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        sf.write(wav_path, full_int16, SAMPLE_RATE)
        _TEMP_FILES.append(wav_path)
        # Normalizzazione loudness (qualità tipo servizi cloud)
        wav_path = _loudnorm_wav(wav_path)
        # Poi il volume scelto dall'utente (la normalizzazione lo annullerebbe)
        wav_path = _apply_gain(wav_path, volume)

        if audio_fmt == "mp3":
            progress(0.9, desc="Conversione MP3...")
            mp3_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
            result = subprocess.run([
                "ffmpeg", "-y", "-i", wav_path,
                "-c:a", "libmp3lame", "-b:a", "192k",
                mp3_path,
            ], capture_output=True, timeout=60)
            if result.returncode != 0:
                err = result.stderr.decode(errors="ignore")[:200]
                raise gr.Error(f"Errore conversione MP3: {err}")
            _TEMP_FILES.append(mp3_path)
            progress(1.0, desc="Completato!")
            return mp3_path, _segments
        progress(1.0, desc="Completato!")
        return wav_path, _segments
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Errore: {e}")

# ── Preview vocale ───────────────────────────────────────────────────────────
_preview_cache: dict = {}

def generate_preview(voice: str, text: str = "", device: str = "auto",
                     engine: str = "edge", pitch: float = 0.0,
                     volume: float = 0.0) -> str:
    """Genera un breve sample audio di anteprima."""
    try:
        # Usa le prime ~100 caratteri del testo utente, o fallback default
        preview_text = text.strip()[:100] if text.strip() else "Ciao, questa è un'anteprima vocale."

        # Cache solo per anteprima default
        if not text.strip():
            cache_key = (voice, device, engine)
            if cache_key in _preview_cache and os.path.exists(_preview_cache[cache_key]):
                return _preview_cache[cache_key]

        full, _segments = synthesize(preview_text, voice, 1.0, device, engine,
                                      None, pitch, volume)
        full_int16 = np.clip(full * 32767, -32768, 32767).astype(np.int16)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        sf.write(tmp.name, full_int16, SAMPLE_RATE)
        _TEMP_FILES.append(tmp.name)

        if not text.strip():
            _preview_cache[(voice, device, engine)] = tmp.name
        return tmp.name
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"Errore anteprima: {e}")

# ── Character counter ────────────────────────────────────────────────────────
def update_stats(text: str, speed: float) -> str:
    """Restituisce HTML con conteggio caratteri, frasi e stima durata."""
    n = len(text.strip())
    if n == 0:
        return "📝 Inserisci del testo..."
    clean = _normalize(text)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    n_sents = len(sentences)
    secs = n / CHARS_PER_SEC / speed
    if secs < 60:
        time_str = f"{secs:.0f}s"
    else:
        m = int(secs // 60)
        s = int(secs % 60)
        time_str = f"{m}min {s}s"
    return f"📝 **{n}** caratteri &nbsp;·&nbsp; 📄 **{n_sents}** frasi &nbsp;·&nbsp; ⏱ **~{time_str}**"

# ── Handler ──────────────────────────────────────────────────────────────────
def handle_generate(text, voice, speed, fmt, audio_fmt, bg_image,
                    video_quality, sub_font_size, sub_text_color, sub_bg_opacity,
                    device, engine, lang, translate, src, pitch, volume):
    # Voce coerente con motore/lingua (menu con tutte le voci).
    # Se il motore non supporta la lingua -> ripiega su Edge.
    valid = [v for _lbl, v in voices_for(engine, lang)]
    if not valid:
        engine = "edge"
        valid = [v for _lbl, v in voices_for("edge", lang)]
    if not valid:
        raise gr.Error(f"Lingua non supportata: {lang}")
    if voice not in valid:
        voice = valid[0]
    if translate and text.strip() and src != lang:
        try:
            text = translate_text(text, src, lang)
        except Exception as e:  # noqa: BLE001
            raise gr.Error(f"Errore traduzione: {e}")
    if fmt == "audio":
        path, segments = generate_audio(text, voice, speed, audio_fmt, device,
                                       engine, pitch, volume)
        player = _build_player_html(segments, path)
        return (gr.update(value=path, visible=True),        # audio_out
                gr.update(value=None, visible=False),       # video_out
                gr.update(value=None, visible=False),       # srt_out
                gr.update(value=None, visible=False),       # wav_out
                gr.update(value=None, visible=False),       # preview_audio
                player)                                     # player_out
    else:
        video_path, srt_path, wav_path, segments = generate_video(
            text, voice, speed, bg_image,
            video_quality, sub_font_size, sub_text_color, sub_bg_opacity,
            device, engine, pitch, volume,
        )
        player = _build_player_html(segments, wav_path)
        return (gr.update(value=None, visible=False),                      # audio_out
                gr.update(value=video_path, visible=True),                 # video_out
                gr.update(value=srt_path, visible=srt_path is not None),   # srt_out
                gr.update(value=wav_path, visible=True),                   # wav_out
                gr.update(value=None, visible=False),                      # preview_audio
                player)                                                    # player_out

def toggle_output(fmt):
    if fmt == "audio":
        return (gr.update(visible=True),   # audio_out
                gr.update(visible=False),  # video_out
                gr.update(visible=False),  # srt_out
                gr.update(visible=False),  # wav_out
                gr.update(visible=True),   # audio_fmt_r
                gr.update(visible=False),  # bg_image
                gr.update(visible=False),  # video_quality_r
                gr.update(visible=False))  # subtitle_accordion
    return (gr.update(visible=False),  # audio_out
            gr.update(visible=True),   # video_out
            gr.update(visible=True),   # srt_out
            gr.update(visible=True),   # wav_out
            gr.update(visible=False),  # audio_fmt_r
            gr.update(visible=True),   # bg_image
            gr.update(visible=True),   # video_quality_r
            gr.update(visible=True))   # subtitle_accordion

def update_voices(engine, lang):
    """Seleziona la voce predefinita del motore/lingua scelti.

    Se il motore non ha voci per quella lingua (es. Kokoro + tedesco)
    si ripiega su Edge senza rompere l'interfaccia.
    """
    vs = voices_for(engine, lang)
    if not vs:
        vs = voices_for("edge", lang) or voices_for("edge", "en")
    return gr.update(value=vs[0][1])


def toggle_tone(engine):
    """Tono e volume si applicano solo al motore Edge."""
    vis = engine == "edge"
    return gr.update(visible=vis), gr.update(visible=vis)


# ── Device options ───────────────────────────────────────────────────────────
_device_options = [("Auto", "auto")]
if _has_cuda:
    _device_options.append(("GPU (CUDA)", "cuda"))
_device_options.append(("CPU", "cpu"))

# ── UI ───────────────────────────────────────────────────────────────────────
with gr.Blocks(title="Sintesi Vocale Multilingua", head=_HEAD_HTML) as demo:
    gr.Markdown("""
    # Sintesi Vocale Multilingua (Kokoro + Microsoft Edge)
    Genera audio o video con sottotitoli sincronizzati, in **italiano** o **inglese**, con **traduzione automatica**.
    """)

    with gr.Row():
        with gr.Column(scale=1):
            text_in = gr.Textbox(
                label="Testo", lines=5,
                value="Ciao a tutti! Benvenuti nell'applicazione di sintesi vocale. Questo programma permette di generare audio e video con sottotitoli sincronizzati.",
                placeholder="Scrivi il testo in italiano...",
            )
            with gr.Row():
                src_r = gr.Dropdown(
                    [(f"{n}", k) for k, n in _LANG_LABELS.items()],
                    value="it", label="🌐 Lingua del testo",
                )
                lang_r = gr.Dropdown(
                    [(f"{n}", k) for k, n in _LANG_LABELS.items()],
                    value="it", label="🔊 Lingua della lettura",
                )
                engine_r = gr.Radio(
                    [("🎙️ Edge online", "edge"), ("💻 Kokoro offline", "kokoro")],
                    value="edge", label="Motore voce",
                )
            translate_cb = gr.Checkbox(
                value=False,
                label="🌍 Traduci automaticamente il testo nella lingua di lettura",
            )
            stats_md = gr.Markdown("📝 Inserisci del testo...")
            with gr.Row():
                with gr.Column(scale=3):
                    voice_r = gr.Dropdown(_ALL_VOICES, value="it-IT-ElsaNeural", label="Voce")
                with gr.Column(scale=1):
                    preview_btn = gr.Button("🔊 Anteprima", variant="secondary", size="sm")
                    preview_audio = gr.Audio(label="Anteprima", interactive=False, visible=False)
            speed_r = gr.Slider(0.5, 2.0, 1.0, 0.05, label="Velocità")
            with gr.Row():
                pitch_r = gr.Slider(-20, 20, 0, 1, step=1,
                                    label="🎚️ Tono (pitch Hz)", info="Solo Edge")
                volume_r = gr.Slider(-50, 50, 0, 5, step=5,
                                     label="🔈 Volume (%)", info="Solo Edge")
            device_r = gr.Radio(_device_options, value="auto", label="Device")
            fmt_r = gr.Radio(
                [("Solo Audio", "audio"), ("Video + Sottotitoli", "video")],
                value="audio", label="Formato output",
            )
            with gr.Row():
                audio_fmt_r = gr.Radio(
                    [("WAV", "wav"), ("MP3", "mp3")],
                    value="wav", label="Formato audio", visible=True,
                )
                bg_image = gr.Image(label="Sfondo video (opzionale)", type="pil", visible=False)
            video_quality_r = gr.Radio(
                [(v["label"], k) for k, v in _QUALITY_PRESETS.items()],
                value="fast", label="Qualità video", visible=False,
            )
            with gr.Accordion("Stile sottotitoli", open=False, visible=False) as subtitle_accordion:
                sub_font_size = gr.Slider(20, 60, 40, 1, label="Dimensione font")
                sub_text_color = gr.ColorPicker(value="#ffffff", label="Colore testo")
                sub_bg_opacity = gr.Slider(0, 255, 160, 1, label="Opacità barra sottotitoli")
            gen_btn = gr.Button("Genera", variant="primary")

        with gr.Column(scale=1):
            audio_out = gr.Audio(label="Audio generato", interactive=False, visible=True)
            video_out = gr.Video(label="Video con sottotitoli", interactive=False, visible=False)
            srt_out = gr.File(label="Sottotitoli SRT", interactive=False, visible=False)
            wav_out = gr.Audio(label="Audio (WAV)", interactive=False, visible=False)
            with gr.Accordion("🔤 Testo pronunciato (evidenziato in sincrono)", open=True):
                player_out = gr.HTML()
            with gr.Accordion("Info", open=False):
                gr.Markdown(f"""
                **Lingue:** {' · '.join(_LANG_LABELS.values())} (9)

                **Kokoro offline:** supporta {' · '.join(k.upper() for k, v in _LANG_CODES.items() if v)} — per le altre lingue serve Edge

                **Tono:** cursori Pitch (Hz) e Volume, disponibili con il motore Edge

                **Motori voce:** Microsoft Edge (online, voci neurali qualità quasi‑Google) · Kokoro (offline)

                **Voci Edge IT:** {', '.join(l for l, _ in _EDGE_VOICES['it'])}

                **Voci Kokoro IT:** {', '.join(l for l, _ in _KOKORO_VOICES['it'])}

                **Traduzione:** Google (se raggiungibile) → NLLB-200 / MarianMT offline · gratuita, frase per frase con controllo qualità

                **Velocità:** 0.5x – 2.0x per regolare il ritmo del parlato

                **Audio:** WAV (lossless, loudness normalizzato a -16 LUFS) o MP3 192k

                **Video:** sfondo gradiente o immagine personalizzata + sottotitoli sincronizzati + file SRT

                **Qualità video:** Veloce (ultrafast 1.5M), Bilanciato (medium 3M), Alta (slow 5M)

                **Device:** {"GPU CUDA disponibile" if _has_cuda else "Solo CPU"}

                **Punteggiatura:** usa . ! ? per pause naturali
                """)

    gen_inputs = [text_in, voice_r, speed_r, fmt_r, audio_fmt_r, bg_image,
                  video_quality_r, sub_font_size, sub_text_color, sub_bg_opacity,
                  device_r, engine_r, lang_r, translate_cb, src_r, pitch_r, volume_r]

    # ── Event bindings ──────────────────────────────────────────────────
    gen_btn.click(
        fn=handle_generate, inputs=gen_inputs,
        outputs=[audio_out, video_out, srt_out, wav_out, preview_audio, player_out],
    ).then(fn=None, js="() => window.kokoroSetup && window.kokoroSetup()")
    text_in.submit(
        fn=handle_generate, inputs=gen_inputs,
        outputs=[audio_out, video_out, srt_out, wav_out, preview_audio, player_out],
    ).then(fn=None, js="() => window.kokoroSetup && window.kokoroSetup()")
    fmt_r.change(
        fn=toggle_output, inputs=fmt_r,
        outputs=[audio_out, video_out, srt_out, wav_out,
                 audio_fmt_r, bg_image, video_quality_r, subtitle_accordion],
    )
    text_in.change(fn=update_stats, inputs=[text_in, speed_r], outputs=[stats_md])
    speed_r.change(fn=update_stats, inputs=[text_in, speed_r], outputs=[stats_md])
    engine_r.change(fn=update_voices, inputs=[engine_r, lang_r], outputs=[voice_r])
    lang_r.change(fn=update_voices, inputs=[engine_r, lang_r], outputs=[voice_r])
    engine_r.change(fn=toggle_tone, inputs=[engine_r],
                    outputs=[pitch_r, volume_r])
    preview_btn.click(
        fn=generate_preview,
        inputs=[voice_r, text_in, device_r, engine_r, pitch_r, volume_r],
        outputs=[preview_audio],
    ).then(
        fn=lambda: gr.update(visible=True), outputs=[preview_audio],
    )

    with gr.Row():
        update_banner = gr.HTML(
            value='<div style="border:1px solid #334155;border-radius:10px;padding:12px 18px;background:#1e293b;font-size:0.85rem;color:#e2e8f0;line-height:1.6">🔍 Controllo aggiornamenti in corso...</div>',
            scale=20,
        )
        refresh_btn = gr.Button("🔄 Ricontrolla", variant="secondary", scale=1, size="sm")

    gr.HTML(f"""<footer style="text-align:center;color:#9ca3af;font-size:0.8rem;margin:2rem">
    Motori: Microsoft Edge TTS &middot; <a href="https://huggingface.co/hexgrad/Kokoro-82M">hexgrad/Kokoro-82M</a> &middot; Traduzione: <a href="https://huggingface.co/Helsinki-NLP">Helsinki-NLP/MarianMT</a> &middot; Apache 2.0</footer>""")

    demo.load(fn=_build_update_html, outputs=[update_banner])
    refresh_btn.click(fn=_refresh_updates, outputs=[update_banner])

if __name__ == "__main__":
    print(f"\n=== Kokoro TTS - Audio & Video v{__version__} ===\nApri: http://localhost:8885\n")
    demo.launch(server_name="127.0.0.1", server_port=8885, share=False, theme=gr.themes.Soft())