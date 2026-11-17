"""Демо-кэш для защиты.

Запуск (в папке server, ПОСЛЕ eval_photos.py):
    python make_demo.py

Что делает:
1. Берёт сохранённые ответы ИИ из папки eval/raw (их делает eval_photos.py) и считает итог
   тем же кодом, что и сайт. Новых запросов к ИИ не делает.
2. Записывает всё в server/demo_cache.json. Сервер отдаёт эти результаты мгновенно,
   даже если Google не отвечает. Файл загружается в GitHub, поэтому работает и на Render.
   В кэш попадают только фото, на которых дефектоскоп ответил верно.
3. Выбирает фото для показа: по каждому модулю 1 эталон и до 2 фото с ошибкой,
   на которых дефектоскоп ответил верно. Копирует их в папку demo_photos (в корне проекта).
   На защите загружай на сайте именно эти файлы кнопкой «Загрузить фото».
"""
import json
import shutil
from pathlib import Path

import main
import eval_photos as ev

SERVER = Path(__file__).parent
DEMO_DIR = SERVER.parent / "demo_photos"
PER_MODULE_ERRORS = 2


def main_run():
    photos = ev.collect()
    cache, picked = {}, []
    by_module = {}
    for module, mod_name, case, photo in photos:
        path = ev.raw_path(mod_name, case, photo)
        if not path.exists():
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("raw") is None:
            continue
        try:
            result = main.build_module_result(saved["raw"], module)
        except Exception:
            continue
        result["model"] = saved.get("model") or ""
        v = ev.verdict(case, result)
        by_module.setdefault(module, []).append((case, photo, v))
        # В демо-кэш кладём только ВЕРНЫЕ ответы. Фото с ложной тревогой или пропуском
        # в кэш не попадают: сервер проверит их заново через ИИ, а не выдаст старую ошибку.
        # (Честная таблица точности при этом не меняется — её считает eval_photos.py.)
        if v == "верно":
            cache[main.cache_key(photo.read_bytes(), module)] = result

    if not cache:
        print("Нет сохранённых ответов. Сначала запусти: python eval_photos.py")
        return

    main.DEMO_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"Записано в {main.DEMO_FILE.name}: {len(cache)} проверок")

    # Папку не удаляем целиком: Windows/OneDrive может её держать (ошибка «Отказано в доступе»).
    # Удаляем только старые фото внутри; если какой-то файл занят — просто пропускаем его.
    DEMO_DIR.mkdir(exist_ok=True)
    for old in DEMO_DIR.glob("*"):
        if old.is_file():
            try:
                old.unlink()
            except OSError:
                print(f"Не удалось удалить {old.name} (файл открыт?) — пропускаю")
    for module in sorted(by_module):
        items = by_module[module]
        etalon = [p for c, p, v in items if c == "01_etalon" and v == "верно"]
        errors, used = [], set()
        for c, p, v in items:
            if c != "01_etalon" and v == "верно" and c not in used and len(errors) < PER_MODULE_ERRORS:
                errors.append((c, p))
                used.add(c)
        chosen = ([("01_etalon", etalon[0])] if etalon else []) + errors
        for n, (case, photo) in enumerate(chosen, 1):
            name = f"m{module}_{n}_{case}{photo.suffix.lower()}"
            try:
                shutil.copy2(photo, DEMO_DIR / name)
            except OSError as e:
                print(f"Не удалось скопировать {name}: {e}")
                continue
            picked.append((module, name, ev.NAMES.get(case, case)))
        if not chosen:
            print(f"Модуль {module}: нет фото, на которых дефектоскоп ответил верно")

    print(f"\nФото для показа (папка {DEMO_DIR}):")
    for module, name, title in picked:
        print(f"  Модуль {module}: {name}  — {title}")
    print("\nНа сайте выбери нужный модуль и загрузи файл кнопкой «Загрузить фото».")


if __name__ == "__main__":
    main_run()
