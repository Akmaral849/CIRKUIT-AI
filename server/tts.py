"""Голоса тьюторов (Silero TTS): каждый тьютор всегда говорит одним и тем же голосом.

Работает только там, где установлены torch, numpy и omegaconf (ноутбук, venv в папке server).
На Render их нет — там сервер отвечает 503, и сайт говорит голосом браузера.

Голоса выбраны 16.11.2026 на слух:
    Декс  — dex_eugene_high_fast           (eugene, высота high, темп fast)
    Люми  — lumi_soft_baya_slow_k1.25      (baya, темп slow, запись ×1.25, мягкий звук)
    Ом    — om_new_eugene_medium_k1.08     (eugene, темп medium, запись ×1.08, мягкий звук)
"""
import io
import re
import threading
import wave
from collections import OrderedDict

import numpy as np
import torch

RATE = 48000

# voice — голос Silero, pitch/rate — настройки SSML, k — ускорение готовой записи,
# soft — граница смягчения высоких частот в Гц (None = без смягчения)
VOICES = {
    "dex": {"voice": "eugene", "pitch": "high", "rate": "fast", "k": 1.0, "soft": None},
    "lumi": {"voice": "baya", "pitch": None, "rate": "slow", "k": 1.25, "soft": 5500},
    "om": {"voice": "eugene", "pitch": None, "rate": "medium", "k": 1.08, "soft": 6500},
}

_model = None
_lock = threading.Lock()
_cache = OrderedDict()   # (тьютор, текст) -> wav, чтобы повторные фразы звучали сразу


def load():
    global _model
    if _model is None:
        print("Загружаю голоса Silero...")
        _model, _ = torch.hub.load(repo_or_dir="snakers4/silero-models", model="silero_tts",
                                   language="ru", speaker="v4_ru", trust_repo=True)
        print("Голоса Silero готовы")
    return _model


# ---------- Текст → то, что Silero умеет прочитать (только русские буквы) ----------
WORDS = {
    "arduino": "ардуино", "uno": "уно", "gnd": "земля", "vcc": "плюс", "led": "светодиод", "leds": "светодиоды",
    "dht11": "ди эйч ти одиннадцать", "dht": "ди эйч ти", "hc-sr04": "эйч си эс ар ноль четыре", "hc": "эйч си",
    "sr04": "эс ар ноль четыре", "trig": "триг", "echo": "эхо", "sda": "эс ди эй", "scl": "эс си эль",
    "rgb": "эр джи би", "lcd": "эл си ди", "i2c": "ай ту си", "usb": "ю эс би", "ao": "а о", "do": "ди о",
    "pwm": "шим", "ok": "окей", "servo": "серво", "sg90": "эс джи девяносто", "gemini": "джемини",
    "pinmode": "пин мод", "digitalwrite": "диджитал райт", "digitalread": "диджитал рид",
    "analogread": "аналог рид", "analogwrite": "аналог райт", "delay": "дилэй", "millis": "миллис",
    "serial": "сериал", "input_pullup": "инпут пул ап", "input": "инпут", "output": "аутпут", "high": "хай",
    "low": "лоу", "void": "войд", "setup": "сетап", "loop": "луп", "if": "иф", "else": "элс", "int": "инт",
    "tone": "тон", "notone": "ноу тон", "bro": "бро", "ide": "ай ди и", "ai": "эй ай", "wi-fi": "вай фай",
}
LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz",
                   ["а", "б", "к", "д", "е", "ф", "г", "х", "и", "ж", "к", "л", "м", "н", "о", "п", "к", "р", "с",
                    "т", "у", "в", "в", "кс", "й", "з"]))

ONES = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять",
        "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
        "семнадцать", "восемнадцать", "девятнадцать"]
TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]


def _under_1000(n, female=False):
    words = []
    if n >= 100:
        words.append(HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        words.append(TENS[n // 10])
        n %= 10
        if n == 0:
            return words
    if n or not words:
        w = ONES[n]
        if female and n == 1:
            w = "одна"
        elif female and n == 2:
            w = "две"
        words.append(w)
    return words


def number_words(n):
    if n >= 1_000_000:
        return " ".join(ONES[int(d)] for d in str(n))
    words = []
    th, rest = divmod(n, 1000)
    if th == 1:
        words.append("тысяча")
    elif th:
        words += _under_1000(th, female=True)
        last = th % 100
        if 11 <= last <= 14:
            words.append("тысяч")
        elif th % 10 == 1:
            words.append("тысяча")
        elif 2 <= th % 10 <= 4:
            words.append("тысячи")
        else:
            words.append("тысяч")
    if rest or not words:
        words += _under_1000(rest)
    return " ".join(words)


def _latin(m):
    word = m.group(0)
    low = word.lower()
    if low in WORDS:
        return " " + WORDS[low] + " "
    out = re.sub(r"(\d+)", r" \1 ", "".join(LETTERS.get(c, c if c.isdigit() else "") for c in low))
    return " " + out + " "


def prepare(text):
    t = str(text or "")
    t = re.sub(r"[*_#`>\[\]{}|~^\\]", " ", t)
    t = t.replace("&", " и ").replace("<", " меньше ").replace(">", " больше ").replace("%", " процентов")
    t = t.replace("°C", " градусов").replace("°", " градусов").replace("Ω", " ом").replace("→", ", ")
    t = re.sub(r"(\d)[.,](\d)", r"\1 и \2", t)                               # 3.5 -> 3 и 5
    t = re.sub(r"[A-Za-z][A-Za-z0-9_\-]*", _latin, t)                        # латиница -> русские буквы
    t = re.sub(r"\d+", lambda m: " " + number_words(int(m.group(0))) + " ", t)
    t = re.sub(r"[^А-Яа-яЁё0-9 .,!?:;\-—–()\"«»'…]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def split(text, limit=500):
    parts, cur = [], ""
    for s in re.findall(r"[^.!?…]+[.!?…]*", text) or [text]:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + len(s) + 1 > limit:
            parts.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        parts.append(cur)
    out = []
    for p in parts:   # совсем длинное предложение режем по запятым
        while len(p) > limit:
            cut = p.rfind(",", 0, limit)
            cut = cut if cut > 50 else limit
            out.append(p[:cut])
            p = p[cut + 1:]
        out.append(p)
    return [p.strip() for p in out if p.strip()]


def _soften(x, cutoff):
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(spec / (1 + (freqs / cutoff) ** 4), n=len(x))


def synth(tutor, text):
    """Возвращает WAV (bytes) или None, если читать нечего."""
    cfg = VOICES.get(tutor, VOICES["dex"])
    clean = prepare(text)
    if not clean:
        return None
    key = (tutor, clean)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    model = load()
    chunks = []
    pause = np.zeros(int(RATE * 0.12))
    with _lock:
        for part in split(clean):
            attrs = f'rate="{cfg["rate"]}"' + (f' pitch="{cfg["pitch"]}"' if cfg["pitch"] else "")
            ssml = f"<speak><prosody {attrs}>{part}</prosody></speak>"
            try:
                audio = model.apply_tts(ssml_text=ssml, speaker=cfg["voice"], sample_rate=RATE,
                                        put_accent=True, put_yo=True)
            except Exception as e:
                print("Silero не прочитал кусок:", part[:60], e)
                continue
            chunks += [audio.numpy().astype(np.float64), pause]
    if not chunks:
        return None
    x = np.concatenate(chunks)
    if cfg["soft"]:
        x = _soften(x, cfg["soft"])
    x = x / (np.max(np.abs(x)) or 1) * 0.85

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(RATE * cfg["k"]))   # больше частота = выше и быстрее
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("int16").tobytes())
    data = buf.getvalue()
    _cache[key] = data
    while len(_cache) > 200:
        _cache.popitem(last=False)
    return data
