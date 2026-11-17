"""Проба голосов Silero для тьюторов (бесплатно, без интернета после первой загрузки).

Один раз установить (в папке server, с включённым venv):
    pip install torch numpy omegaconf

Запуск:
    python voice_test.py          все тьюторы
    python voice_test.py dex      только Декс (так же lumi или om)

Файлы .wav появляются в папке server/voice_test. Имя файла = тьютор_голос_высота_скорость.wav.
"""
import sys
import wave
from pathlib import Path

import torch

OUT = Path(__file__).parent / "voice_test"
OUT.mkdir(exist_ok=True)
RATE = 48000

TEXT = {
    "lumi": "Приветик! Я Люми! Ой, как здорово, что ты здесь! Давай вместе соберём схемку!",
    "dex": "Йоу, бро! Я Декс. Го чекнем твою схемку, найдём косяк за пару минут, изи!",
    "om": "Здравствуй. Я Ом. Итак, вопрос на размышление: куда течёт ток, когда цепь замкнута?",
}

# тьютор: [(голос, высота, скорость), ...]
VARIANTS = {
    "lumi": [(v, p, "medium") for v in ("xenia", "baya", "kseniya") for p in ("high", "x-high")],
    # Декс, раунд 2: голос моложе и мягче, без хрипа.
    # eugene выше; aidar выше; и женские голоса, опущенные вниз (так иногда звучит как парень-подросток).
    "dex": [
        ("eugene", "x-high", "fast"),
        ("eugene", "high", "medium"),
        ("aidar", "high", "fast"),
        ("aidar", "x-high", "fast"),
        ("baya", "low", "fast"),
        ("baya", "x-low", "fast"),
        ("kseniya", "x-low", "fast"),
        ("xenia", "x-low", "fast"),
    ],
    "om": [(v, p, "slow") for v in ("aidar", "eugene") for p in ("low", "medium")],
}

only = sys.argv[1] if len(sys.argv) > 1 else None

print("Загружаю модель Silero...")
model, _ = torch.hub.load(repo_or_dir="snakers4/silero-models", model="silero_tts",
                          language="ru", speaker="v4_ru", trust_repo=True)


def save_wav(path, audio):
    data = (audio.clamp(-1, 1).numpy() * 32767).astype("int16")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


for tutor, variants in VARIANTS.items():
    if only and tutor != only:
        continue
    for voice, pitch, speed in variants:
        ssml = f'<speak><prosody pitch="{pitch}" rate="{speed}">{TEXT[tutor]}</prosody></speak>'
        try:
            audio = model.apply_tts(ssml_text=ssml, speaker=voice, sample_rate=RATE,
                                    put_accent=True, put_yo=True)
        except Exception as e:
            print(f"Не получилось {tutor} {voice} {pitch} {speed}: {e}")
            continue
        name = f"{tutor}_{voice}_{pitch}_{speed}.wav"
        save_wav(OUT / name, audio)
        print("Готово:", name)

print(f"\nВсе файлы в папке {OUT}. Послушай и напиши, какие понравились.")
