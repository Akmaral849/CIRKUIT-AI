"""Голос Ома: чёткая дикция, спокойный, но НЕ старый. Плюс фирменная особенность — совиное «уху».

Запуск (в папке server, с включённым venv):
    python voice_om.py

Файлы появятся в папке server/voice_test, имена начинаются на om_new_...
    om_new_<голос>_<скорость>_k<ускорение>.wav        — Ом говорит «Уху!» сам
    om_new_hoot_<голос>_<скорость>_k<ускорение>.wav   — перед речью звучит мягкий совиный звук «у-ху»
"""
import wave
from pathlib import Path

import numpy as np
import torch

OUT = Path(__file__).parent / "voice_test"
OUT.mkdir(exist_ok=True)
RATE = 48000
TEXT_SAY = "Уху! Здравствуй, я Ом. Итак... вопрос на размышление: куда течёт ток, когда цепь замкнута?"
TEXT = "Здравствуй, я Ом. Итак... вопрос на размышление: куда течёт ток, когда цепь замкнута?"

# (голос, скорость речи в Silero, ускорение записи k). Ускорение чуть больше 1 делает голос моложе.
VARIANTS = [(v, r, k) for v in ("aidar", "eugene")
            for r, k in (("medium", 1.0), ("medium", 1.08), ("slow", 1.15))]
HOOT_VARIANTS = [("aidar", "medium", 1.08), ("eugene", "medium", 1.08)]

print("Загружаю модель Silero...")
model, _ = torch.hub.load(repo_or_dir="snakers4/silero-models", model="silero_tts",
                          language="ru", speaker="v4_ru", trust_repo=True)


def soften(x, cutoff=6500):
    """Убираем резкие высокие частоты, чтобы голос был мягче и меньше «железный»."""
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    y = np.fft.irfft(spec / (1 + (freqs / cutoff) ** 4), n=len(x))
    return y / (np.max(np.abs(y)) or 1) * 0.85


def hoot(base=420.0):
    """Мягкое совиное «у-ху»: два тёплых звука, второй чуть выше и короче."""
    parts = []
    for f, dur in ((base, 0.28), (base * 1.12, 0.38)):
        t = np.arange(int(RATE * dur)) / RATE
        glide = f * (1 + 0.06 * np.sin(np.pi * t / dur))          # звук слегка поднимается и опускается
        phase = 2 * np.pi * np.cumsum(glide) / RATE
        tone = np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.08 * np.sin(3 * phase)
        env = np.sin(np.pi * t / dur) ** 1.5                       # плавное начало и конец
        parts += [tone * env * 0.5, np.zeros(int(RATE * 0.08))]
    return np.concatenate(parts + [np.zeros(int(RATE * 0.15))])


def speak(text, voice, speed):
    ssml = f'<speak><prosody rate="{speed}">{text}</prosody></speak>'
    audio = model.apply_tts(ssml_text=ssml, speaker=voice, sample_rate=RATE, put_accent=True, put_yo=True)
    return audio.numpy().astype(np.float64)


def save_wav(path, samples, rate):
    data = (np.clip(samples, -1, 1) * 32767).astype("int16")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


for voice, speed, k in VARIANTS:
    try:
        x = speak(TEXT_SAY, voice, speed)
    except Exception as e:
        print(f"Не получилось {voice} {speed}: {e}")
        continue
    name = f"om_new_{voice}_{speed}_k{k}.wav"
    save_wav(OUT / name, soften(x), int(RATE * k))
    print("Готово:", name)

for voice, speed, k in HOOT_VARIANTS:
    try:
        x = soften(speak(TEXT, voice, speed))
    except Exception as e:
        print(f"Не получилось {voice} {speed}: {e}")
        continue
    name = f"om_new_hoot_{voice}_{speed}_k{k}.wav"
    save_wav(OUT / name, np.concatenate([hoot(), x]), int(RATE * k))
    print("Готово:", name)

print(f"\nФайлы в папке {OUT}. Слушай те, что начинаются на om_new_.")
