"""Видео → кадры для обучения своей нейросети.

Куда класть видео: в папку ситуации, имя файла ЛЮБОЕ (как пришло из Telegram):
    CIRKUIT-AI\\dataset_video\\m1\\ok\\любое_имя.mp4
    CIRKUIT-AI\\dataset_video\\m1\\net_rezistora\\...
    ...
Первый запуск создаёт все папки m1…m7 с папками ситуаций внутри.

Запуск (в папке server, с включённым venv; нужен opencv: pip install opencv-python):
    python video_to_frames.py
Результат:
    CIRKUIT-AI\\dataset\\m1\\ok\\ok_0001.jpg ... — по ~60 чётких кадров с каждого видео
Размытые кадры (телефон дёрнулся) выкидываются сами.
"""
import re
from pathlib import Path

import cv2

ROOT = Path(__file__).parent.parent
SRC = ROOT / "dataset_video"
OUT = ROOT / "dataset"
PER_VIDEO = 60       # сколько кадров брать с одного видео
SIZE = 640           # длинная сторона кадра в пикселях
VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".3gp", ".webm"}


def sharpness(img):
    return cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


def frames_of(path):
    cap = cv2.VideoCapture(str(path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    step = max(1, total // (PER_VIDEO * 2)) if total else 5   # берём вдвое больше и оставляем самые чёткие
    picked, i = [], 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if i % step == 0:
            h, w = img.shape[:2]
            k = SIZE / max(h, w)
            img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
            picked.append((sharpness(img), len(picked), img))
        i += 1
    cap.release()
    best = sorted(picked, key=lambda x: -x[0])[:PER_VIDEO]
    return [img for _, _, img in sorted(best, key=lambda x: x[1])]   # обратно по порядку видео


CLASSES = {
    "m1": ["ok", "net_detali", "net_rezistora", "visyachiy_provod"],
    "m2": ["ok", "net_detali", "trig_echo", "visyachiy_provod"],
    "m3": ["ok", "net_detali", "net_rezistora", "visyachiy_provod"],
    "m4": ["ok", "net_detali", "sda_scl", "visyachiy_provod"],
    "m5": ["ok", "net_detali", "net_gnd", "visyachiy_provod"],
    "m6": ["ok", "net_detali", "ne_tot_pin", "visyachiy_provod"],
    "m7": ["ok", "net_detali", "net_rezistora", "visyachiy_provod"],
}


def main():
    first = not SRC.exists()
    for m, classes in CLASSES.items():
        for c in classes:
            (SRC / m / c).mkdir(parents=True, exist_ok=True)
    if first:
        print(f"Создала папки в {SRC}. Перетащи туда видео и запусти снова.")
        return
    total = 0
    for video in sorted(p for p in SRC.rglob("*") if p.suffix.lower() in VIDEO):
        rel = video.relative_to(SRC).parts           # dataset_video/m1/ok/видео.mp4 — класс = папка
        if len(rel) >= 3:
            module, label = rel[0], rel[1].lower()
        else:                                        # dataset_video/m1/ok.mp4 — класс = имя файла
            module, label = rel[0], re.sub(r"_\d+$", "", video.stem).lower()
        out = OUT / module / label
        out.mkdir(parents=True, exist_ok=True)
        done = out / ".done.txt"
        seen = done.read_text(encoding="utf-8").splitlines() if done.exists() else []
        if video.name in seen:
            continue                                  # это видео уже нарезано
        start = len(list(out.glob("*.jpg")))
        frames = frames_of(video)
        for j, img in enumerate(frames, start + 1):
            cv2.imwrite(str(out / f"{label}_{j:04d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        with done.open("a", encoding="utf-8") as f:
            f.write(video.name + "\n")
        total += len(frames)
        print(f"{module}/{video.name}: кадров {len(frames)} → {out}")
    print(f"\nГотово. Всего кадров: {total}. Папка: {OUT}")


if __name__ == "__main__":
    main()
