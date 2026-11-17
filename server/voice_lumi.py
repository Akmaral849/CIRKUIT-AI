"""Голос Люми: нежный, звонкий, без хрипа (Silero, бесплатно, без интернета).

Запуск (в папке server, с включённым venv):
    python voice_lumi.py

Файлы появятся в папке server/voice_test, имена начинаются на lumi_soft_...

Как сделан голос:
1. Высоту в Silero не поднимаем: от этого появляется хрип.
2. Готовую запись ускоряем целиком (k): голос становится выше и звонче.
3. Срезаем самые резкие высокие частоты: звук становится мягче и меньше «железный».
"""
import wave
from pathlib import Path

import numpy as np
import torch

OUT = Path(__file__).parent / "voice_test"
OUT.mkdir(exist_ok=True)
RATE = 48000
TEXT = "Приветик! Я Люми! Ой... как здорово, что ты здесь! Давай вместе соберём схемку, хорошо?"

# (голос, скорость речи в Silero, ускорение записи k)
VARIANTS = [(v, r, k) for v in ("xenia", "kseniya", "baya")
            for r, k in (("medium", 1.1), ("medium", 1.18), ("slow", 1.25))]

print("Загружаю модель Silero...")
model, _ = torch.hub.load(repo_or_dir="snakers4/silero-models", model="silero_tts",
                          language="ru", speaker="v4_ru", trust_repo=True)


def soften(audio, cutoff=5500):
    """Мягкий звук: плавно убираем частоты выше cutoff Гц и выравниваем громкость."""
    x = audio.numpy().astype(np.float64)
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    gain = 1 / (1 + (freqs / cutoff) ** 4)
    y = np.fft.irfft(spec * gain, n=len(x))
    peak = np.max(np.abs(y)) or 1
    return y / peak * 0.85


def save_wav(path, samples, rate):
    data = (np.clip(samples, -1, 1) * 32767).astype("int16")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


for voice, speed, k in VARIANTS:
    ssml = f'<speak><prosody rate="{speed}">{TEXT}</prosody></speak>'
    try:
        audio = model.apply_tts(ssml_text=ssml, speaker=voice, sample_rate=RATE, put_accent=True, put_yo=True)
    except Exception as e:
        print(f"Не получилось {voice} {speed} {k}: {e}")
        continue
    name = f"lumi_soft_{voice}_{speed}_k{k}.wav"
    save_wav(OUT / name, soften(audio), int(RATE * k))
    print("Готово:", name)

print(f"\nФайлы в папке {OUT}. Слушай те, что начинаются на lumi_soft_.")
