"""Повёрнутые копии кадров, чтобы нейросеть не училась по серым полям.

Проблема: часть видео снята вертикально (серые поля слева и справа),
часть горизонтально (поля сверху и снизу). Например, в m6 все «ok» вертикальные,
а «ne_tot_pin» и «visyachiy_provod» горизонтальные. Нейросеть может запомнить
«поля сверху = ошибка» вместо того, чтобы смотреть на провода.

Решение: к каждому кадру добавляем копию, повёрнутую на 90°.
Тогда в каждом классе есть оба вида полей, и этот признак перестаёт что-то значить.

Запуск (в папке server, с venv):
    python add_rotations.py
Берёт и кладёт в ту же папку: CIRKUIT-AI\\dataset_sq\\mN\\<класс>\\*_r90.jpg
Повторный запуск ничего не дублирует.
"""
from pathlib import Path

import cv2

ROOT = Path(__file__).parent.parent
SQ = ROOT / "dataset_sq"


def main():
    done = 0
    for f in sorted(SQ.rglob("*.jpg")):
        if f.stem.endswith("_r90"):
            continue
        out = f.with_name(f.stem + "_r90.jpg")
        if out.exists():
            continue
        img = cv2.imread(str(f))
        if img is None:
            continue
        cv2.imwrite(str(out), cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        done += 1
    print(f"Готово: повёрнутых копий {done}. Папка: {SQ}")
    for d in sorted(p for p in SQ.glob("m*/*") if p.is_dir()):
        print(f"  {d.relative_to(SQ)}: {len(list(d.glob('*.jpg')))} кадров")


if __name__ == "__main__":
    main()
