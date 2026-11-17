"""Готовые фото МАКЕТА для защиты (гарантированный показ).

Запуск (в папке server, с включённым venv, ПОСЛЕ make_demo.py):
    python make_maket_demo.py

Подготовка:
    Сфотографируй платы на макете и разложи фото по папкам:
        CIRKUIT-AI\\maket_demo\\m1   (модуль 1)
        CIRKUIT-AI\\maket_demo\\m2   (модуль 2)
        ...
        CIRKUIT-AI\\maket_demo\\m7   (модуль 7)
    Имя файла любое. Можно фото без ошибок и фото с нарочно сделанной ошибкой.

Что делает:
1. Каждое новое фото отправляет в ИИ (до 3 попыток) и печатает результат.
2. Спрашивает: «Ответ верный?». Если да (д) — фото и ответ сохраняются.
   Если нет (н) — фото не берём (сфотографируй по-другому или выбери другую ошибку).
3. Все принятые ответы добавляет в server/demo_cache.json (сервер отдаёт их мгновенно,
   даже без Google), копирует фото в папку demo_photos и пишет demo_photos/list.json.
   По этому списку сайт показывает кнопки «Готовые фото этого модуля».

Уже принятые фото второй раз в ИИ не отправляются (запросы не тратятся).
make_demo.py очищает папку demo_photos — после него всегда запускай этот скрипт ещё раз.
"""
import asyncio
import json
import re
import shutil
from pathlib import Path

import main

SERVER = Path(__file__).parent
ROOT = SERVER.parent
SRC = ROOT / "maket_demo"
DEMO_DIR = ROOT / "demo_photos"
RECORD = SERVER / "maket_demo_record.json"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

CASE_NAMES = {
    "01_etalon": "Правильная сборка", "02_net_gnd": "Нет GND", "03_led_perevernut": "Светодиод перевёрнут",
    "04_net_rezistora": "Нет резистора", "05_ne_tot_pin": "Не тот пин", "06_visyachiy_provod": "Висящий провод",
}


def load_record():
    try:
        return json.loads(RECORD.read_text(encoding="utf-8"))
    except Exception:
        return {}


def short_label(result):
    if result.get("status") == "parts_ok":
        return "Макет: без ошибок"
    if result.get("errors"):
        text = str(result["errors"][0]).split(":")[0]
        return "Макет: " + text[:40]
    return "Макет: проверка"


def show(result):
    print("   Итог:", result.get("status"))
    for t in result.get("found") or []:
        print("   + найдено:", t)
    for t in result.get("errors") or []:
        print("   ! ошибка:", t)
    for t in result.get("unclear") or []:
        print("   ? не разглядел:", t)


async def check_photo(path, module):
    data = path.read_bytes()
    for attempt in range(1, 4):
        print(f"   попытка {attempt}...")
        try:
            raw, model, seconds = await main.ask_check(data, MIME[path.suffix.lower()], module)
        except Exception as e:
            print("   ответ не разобрать:", str(e)[:100])
            raw, model, seconds = None, None, 0
        if raw is not None:
            result = main.build_module_result(raw, module)
            result["model"] = model or ""
            print(f"   ответила модель {model} за {seconds} сек")
            return result
        await asyncio.sleep(5)
    return None


def write_list(record):
    """demo_photos/list.json: какие кнопки показывать на сайте по каждому модулю."""
    by_module = {}
    labels = {r["file"]: r["label"] for r in record.values()}
    for f in sorted(DEMO_DIR.glob("*")):
        if not f.is_file() or f.suffix.lower() not in MIME:
            continue
        m = re.match(r"(?:maket_)?m(\d)_", f.name)
        if not m:
            continue
        if f.name in labels:
            label = labels[f.name]
        else:
            case = re.sub(r"^m\d_\d+_", "", f.stem)
            label = CASE_NAMES.get(case, case.replace("_", " "))
        by_module.setdefault(m.group(1), []).append([f.name, label])
    # фото макета показываем первыми
    for k in by_module:
        by_module[k].sort(key=lambda x: (not x[0].startswith("maket_"), x[0]))
    (DEMO_DIR / "list.json").write_text(json.dumps(by_module, ensure_ascii=False, indent=1), encoding="utf-8")


async def run():
    if not SRC.exists():
        for n in range(1, 8):
            (SRC / f"m{n}").mkdir(parents=True, exist_ok=True)
        print(f"Создала папки {SRC}\\m1 ... m7. Положи туда фото макета и запусти скрипт снова.")
        return
    record = load_record()
    DEMO_DIR.mkdir(exist_ok=True)

    for n in range(1, 8):
        folder = SRC / f"m{n}"
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in MIME:
                continue
            key = main.cache_key(path.read_bytes(), n)
            if key in record:
                continue
            print(f"\nМодуль {n}: {path.name}")
            result = await check_photo(path, n)
            if result is None:
                print("   Google не ответил 3 раза. Это фото пропускаю, запусти скрипт позже.")
                continue
            show(result)
            answer = input("   Ответ верный? (д/н): ").strip().lower()
            if not answer.startswith(("д", "y", "l")):
                print("   Не беру это фото.")
                continue
            record[key] = {"module": n, "src": str(path.relative_to(ROOT)),
                           "file": f"maket_m{n}_{path.stem}{path.suffix.lower()}",
                           "label": short_label(result), "result": result}
            RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            print("   Принято:", record[key]["label"])

    # Добавляем в демо-кэш и копируем фото (каждый раз заново — на случай, если make_demo.py всё стёр)
    try:
        cache = json.loads(main.DEMO_FILE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    copied = 0
    for key, r in record.items():
        src = ROOT / r["src"]
        if not src.exists():
            continue
        cache[key] = r["result"]
        try:
            shutil.copy2(src, DEMO_DIR / r["file"])
            copied += 1
        except OSError as e:
            print("Не удалось скопировать", r["file"], e)
    main.DEMO_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    write_list(record)
    print(f"\nГотово. Фото макета в демо: {copied}. Всего проверок в демо-кэше: {len(cache)}.")
    print("Дальше: GitHub Desktop → Commit → Push (обновятся сайт и сервер на Render).")


if __name__ == "__main__":
    asyncio.run(run())
