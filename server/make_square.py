"""Кадры → квадрат без обрезки (для Teachable Machine).

Teachable Machine обрезает каждую картинку до квадрата по центру, и у вертикальных кадров
пропадают верх и низ (а там часто светодиоды и резисторы). Этот скрипт дополняет кадр
серыми полями до квадрата: вся плата остаётся в кадре.

Запуск (в папке server, с venv):
    python make_square.py
Берёт:   CIRKUIT-AI\\dataset\\m1\\ok\\*.jpg ...
Кладёт:  CIRKUIT-AI\\dataset_sq\\m1\\ok\\*.jpg ...   ← эти кадры загружаешь в Teachable Machine
Уже готовые кадры повторно не делает.
"""
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent.parent
SRC = ROOT / "dataset"
OUT = ROOT / "dataset_sq"
SIZE = 448
GRAY = 128   # такой же цвет полей сайт ставит при проверке с камеры


def square(img):
    h, w = img.shape[:2]
    k = SIZE / max(h, w)
    img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    canvas = np.full((SIZE, SIZE, 3), GRAY, np.uint8)
    y, x = (SIZE - h) // 2, (SIZE - w) // 2
    canvas[y:y + h, x:x + w] = img
    return canvas


def main():
    done = 0
    for f in sorted(SRC.rglob("*.jpg")):
        out = OUT / f.relative_to(SRC)
        if out.exists():
            continue
        img = cv2.imread(str(f))
        if img is None:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), square(img), [cv2.IMWRITE_JPEG_QUALITY, 92])
        done += 1
    print(f"Готово: новых квадратных кадров {done}. Папка: {OUT}")
    for d in sorted(p for p in OUT.glob("m*/*") if p.is_dir()):
        print(f"  {d.relative_to(OUT)}: {len(list(d.glob('*.jpg')))} кадров")


if __name__ == "__main__":
    main()
