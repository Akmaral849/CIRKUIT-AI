"""Прогон всех фото из папки photos через дефектоскоп и таблица точности.

Запуск (в папке server, с включённым venv):
    python eval_photos.py              все модули
    python eval_photos.py 3            только модуль 3
    python eval_photos.py --rescore    не обращаться к ИИ, пересчитать таблицы по сохранённым ответам
    python eval_photos.py --fresh      заново спросить ИИ про все фото (старые ответы перезаписываются)

Как это работает:
- Фото берутся из папки photos рядом с папкой server: photos/m1_perekrestok/01_etalon/*.jpg и т.д.
  Номер модуля — по началу имени папки (m1 ... m7), тип случая — по имени подпапки.
  Папка 01_etalon = правильная сборка, остальные папки = одна известная ошибка.
- Ответ ИИ на каждое фото сохраняется в папку eval/raw. Повторный запуск не тратит запросы:
  фото, на которые ответ уже есть, второй раз не отправляются. Если вопросы в main.py поменялись,
  фото отправляются заново автоматически.
- Итог для каждого фото считает тот же код, что и на сайте (main.build_module_result).

Результаты (папка server/eval, открываются в Excel):
    eval/photos.csv       каждое фото: что ожидалось, что нашёл дефектоскоп, итог
    eval/by_module.csv    точность по модулям
    eval/by_error.csv     точность по типам ошибок (все модули вместе)
    eval/by_case.csv      точность по каждой папке (модуль + тип ошибки)

Что значат итоги:
    верно            эталон: ошибок не найдено; фото с ошибкой: найдена именно эта ошибка
    другая ошибка    фото с ошибкой: дефектоскоп нашёл ошибку, но не ту (или не только ту)
    пропуск          фото с ошибкой: ошибок не найдено
    ложная тревога   эталон: дефектоскоп нашёл ошибку, которой нет
    сбой             ИИ не ответил или ответ не разобрать (в точность не входит)
"""
import asyncio
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import main

SERVER = Path(__file__).parent
PHOTOS = SERVER.parent / "photos"
# Режим сравнения с эталоном (CHECK_COMPARE=1) пишет в отдельную папку, старые таблицы не трогаются
OUT = SERVER / ("eval_cmp" if main.COMPARE else "eval")
RAW = OUT / "raw"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
# Сколько фото проверяется одновременно. На бесплатном тарифе у Gemini лимит запросов в минуту,
# поэтому по умолчанию 1. После включения оплаты можно добавить в .env строку EVAL_PARALLEL=3.
PARALLEL = max(1, int(os.getenv("EVAL_PARALLEL", "1")))

# Для прогона спешить не нужно: каждой модели даём до 60 с, на одно фото до 150 с.
# На сайте действуют обычные пределы из .env (ATTEMPT_TIMEOUT, TOTAL_BUDGET).
main.ATTEMPT_TIMEOUT = 60
main.TOTAL_BUDGET = 150

# Какой тип ошибки (tag из main.py) считается «правильно найденным» для каждой папки
EXPECTED = {
    "02_net_gnd": {"gnd", "hanging"},
    "03_led_perevernut": {"polarity"},
    "04_net_rezistora": {"resistor"},
    "05_ne_tot_pin": {"pin", "trace"},
    "06_visyachiy_provod": {"hanging", "pin", "trace", "wire"},
    "07_knopka_povernuta": {"button"},
    "07_trig_echo_pereputany": {"trace"},
    "08_servo_signal_ne_v_pine": {"trace", "pin", "hanging"},
    "07_fotorezistor_ne_v_A0": {"trace", "pin"},
    "07_sda_scl_pereputany": {"trace"},
    "08_dht_ne_v_pine": {"trace", "pin"},
    "07_rgb_bez_rezistora": {"resistor"},
    "07_do_ne_v_tom_pine": {"trace", "pin"},
    "07_luch_mimo": {"beam"},
}
NAMES = {
    "01_etalon": "эталон (без ошибок)", "02_net_gnd": "нет GND", "03_led_perevernut": "светодиод перевёрнут",
    "04_net_rezistora": "нет резистора", "05_ne_tot_pin": "не тот пин", "06_visyachiy_provod": "висящий провод",
    "07_knopka_povernuta": "кнопка повёрнута", "07_trig_echo_pereputany": "Trig и Echo перепутаны",
    "08_servo_signal_ne_v_pine": "сигнал серво не в пине", "07_fotorezistor_ne_v_A0": "фоторезистор не в A0",
    "07_sda_scl_pereputany": "SDA и SCL перепутаны", "08_dht_ne_v_pine": "DHT не в пине",
    "07_rgb_bez_rezistora": "RGB без резистора", "07_do_ne_v_tom_pine": "датчик огня не в том пине",
    "07_luch_mimo": "луч мимо",
}


def prompt_hash(module):
    return hashlib.sha256(main.module_system(module).encode("utf-8")).hexdigest()[:12]


def collect(only_module=None):
    """Порядок: сначала по 1-му фото из каждой папки всех модулей, потом по 2-му и т.д.
    Так даже при маленьком лимите запросов проверяются все модули и все типы ошибок."""
    photos = []
    for mod_dir in sorted(p for p in PHOTOS.iterdir() if p.is_dir() and p.name[:1] == "m" and p.name[1:2].isdigit()):
        module = int(mod_dir.name[1])
        if only_module and module != only_module:
            continue
        for case_dir in sorted(p for p in mod_dir.iterdir() if p.is_dir()):
            for photo in sorted(p for p in case_dir.iterdir() if p.suffix.lower() in MIME):
                if main.compare_on(module) and photo.read_bytes() == main.etalon_image(module):
                    continue   # само эталонное фото с собой не сравниваем
                photos.append((module, mod_dir.name, case_dir.name, photo))
    index = {}
    order = []
    for item in photos:
        key = (item[0], item[2])
        index[key] = index.get(key, 0) + 1
        order.append((index[key], item[0], item[2], item))
    return [o[3] for o in sorted(order, key=lambda o: o[:3])]


def raw_path(mod_name, case, photo):
    return RAW / mod_name / case / (photo.stem + ".json")


async def get_raw(module, mod_name, case, photo, mode, sem, state=None):
    """Сохранённый ответ ИИ или новый запрос. Возвращает словарь с полями raw/model/seconds/error."""
    path = raw_path(mod_name, case, photo)
    phash = prompt_hash(module)
    if path.exists() and mode != "fresh":
        saved = json.loads(path.read_text(encoding="utf-8"))
        if mode == "rescore" or (saved.get("prompt") == phash and saved.get("raw") is not None):
            return saved
    if mode == "rescore":
        return {"raw": None, "error": "нет сохранённого ответа"}

    data = photo.read_bytes()
    async with sem:
        if state and state.get("stopped"):
            return {"raw": None, "error": "прогон остановлен: ИИ не отвечает"}
        try:
            raw, model, seconds = await main.ask_check(data, MIME[photo.suffix.lower()], module)
            error = None if raw is not None else "ИИ не ответил"
        except Exception as e:
            raw, model, seconds, error = None, None, 0, f"ответ не разобрать: {str(e)[:100]}"
    saved = {"raw": raw, "model": model, "seconds": seconds, "error": error, "prompt": phash,
             "time": datetime.now().isoformat(timespec="seconds")}
    if raw is not None:   # неудачные ответы не сохраняем, чтобы в следующий раз спросить снова
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return saved


def verdict(case, result):
    if result is None:
        return "сбой"
    tags = set(result.get("error_tags") or [])
    if case == "01_etalon":
        return "ложная тревога" if tags else "верно"
    if not tags:
        return "пропуск"
    return "верно" if tags & EXPECTED.get(case, set()) else "другая ошибка"


def summarize(rows, key_name, key_func):
    groups = {}
    for r in rows:
        groups.setdefault(key_func(r), []).append(r)
    table = []
    for key, part in groups.items():
        done = [r for r in part if r["Итог"] != "сбой"]
        count = lambda v: sum(r["Итог"] == v for r in done)
        right = count("верно")
        table.append({
            key_name: key,
            "Фото": len(part),
            "Сбой": len(part) - len(done),
            "Верно": right,
            "Другая ошибка": count("другая ошибка"),
            "Пропуск": count("пропуск"),
            "Ложная тревога": count("ложная тревога"),
            "Точность, %": round(100 * right / len(done), 1) if done else "",
        })
    return table


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def print_table(title, rows, key_name):
    print("\n" + title)
    print(f"  {key_name:<34} фото  верно  другая  пропуск  ложн.  сбой  точность")
    for r in rows:
        acc = f"{r['Точность, %']}%" if r["Точность, %"] != "" else "-"
        print(f"  {str(r[key_name]):<34} {r['Фото']:>4}  {r['Верно']:>5}  {r['Другая ошибка']:>6}  {r['Пропуск']:>7}"
              f"  {r['Ложная тревога']:>5}  {r['Сбой']:>4}  {acc:>8}")


async def run(only_module, mode):
    if not PHOTOS.exists():
        print("Не нашла папку photos рядом с папкой server.")
        return
    photos = collect(only_module)
    if not photos:
        print("Фото не найдены.")
        return
    print(f"Фото к проверке: {len(photos)}. Режим: {mode}. Выключенные типы проверок: {sorted(main.CHECK_OFF) or 'нет'}")

    sem = asyncio.Semaphore(PARALLEL)
    begin = time.time()
    done_count = 0
    state = {"fails_in_row": 0, "stopped": False}
    STOP_AFTER = 8   # столько сбоев подряд = квота кончилась или Google лежит, дальше не тратим время

    async def one(item):
        nonlocal done_count
        module, mod_name, case, photo = item
        saved = await get_raw(module, mod_name, case, photo, mode, sem, state)
        if (saved.get("error") or "").startswith("прогон остановлен"):
            pass
        else:
            if saved.get("raw") is None and mode != "rescore":
                state["fails_in_row"] += 1
                if state["fails_in_row"] >= STOP_AFTER and not state["stopped"]:
                    state["stopped"] = True
                    print(f"\n!!! {STOP_AFTER} сбоев подряд: скорее всего, кончилась дневная квота Gemini (ошибка 429) "
                          "или Google перегружен. Остальные фото пропускаю. Запусти прогон позже.\n")
            else:
                state["fails_in_row"] = 0
        result = None
        if saved.get("raw") is not None:
            try:
                result = main.build_module_result(saved["raw"], module)
            except Exception as e:
                saved["error"] = f"итог не посчитать: {e}"
        done_count += 1
        v = verdict(case, result)
        print(f"[{done_count}/{len(photos)}] m{module} {case}/{photo.name}: {v}")
        return {
            "Модуль": module,
            "Папка": case,
            "Случай": NAMES.get(case, case),
            "Фото": photo.name,
            "Ожидалось": "без ошибок" if case == "01_etalon" else "есть ошибка",
            "Типы найденных ошибок": ", ".join(result["error_tags"]) if result else "",
            "Что нашёл": " | ".join(result["errors"]) if result and result["errors"] else ("ошибок нет" if result else ""),
            "Не разглядел": len(result["unclear"]) if result else "",
            "Итог": v,
            "Секунд": saved.get("seconds", ""),
            "Модель": saved.get("model") or "",
            "Сбой": saved.get("error") or "",
        }

    rows = await asyncio.gather(*(one(p) for p in photos))
    rows.sort(key=lambda r: (r["Модуль"], r["Папка"], r["Фото"]))

    OUT.mkdir(exist_ok=True)
    by_module = summarize(rows, "Модуль", lambda r: f"Модуль {r['Модуль']}")
    by_module += summarize(rows, "Модуль", lambda r: "ВСЕГО")
    by_error = summarize(rows, "Тип случая", lambda r: r["Случай"])
    by_case = summarize(rows, "Модуль и случай", lambda r: f"m{r['Модуль']} {r['Случай']}")
    write_csv(OUT / "photos.csv", rows)
    write_csv(OUT / "by_module.csv", by_module)
    write_csv(OUT / "by_error.csv", by_error)
    write_csv(OUT / "by_case.csv", by_case)

    etalon = [r for r in rows if r["Папка"] == "01_etalon" and r["Итог"] != "сбой"]
    broken = [r for r in rows if r["Папка"] != "01_etalon" and r["Итог"] != "сбой"]
    print_table("Точность по модулям:", by_module, "Модуль")
    print_table("Точность по типам случаев:", by_error, "Тип случая")
    if etalon:
        clean = sum(r["Итог"] == "верно" for r in etalon)
        print(f"\nЭталоны без ложной тревоги: {clean} из {len(etalon)} ({100 * clean / len(etalon):.1f}%)")
    if broken:
        exact = sum(r["Итог"] == "верно" for r in broken)
        anyerr = sum(r["Итог"] in ("верно", "другая ошибка") for r in broken)
        print(f"Фото с ошибкой: нужная ошибка найдена {exact} из {len(broken)} ({100 * exact / len(broken):.1f}%), "
              f"хоть какая-то ошибка — {anyerr} из {len(broken)} ({100 * anyerr / len(broken):.1f}%)")
    times = [r["Секунд"] for r in rows if isinstance(r["Секунд"], (int, float)) and r["Секунд"] > 0]
    if times:
        print(f"Среднее время ответа ИИ: {sum(times) / len(times):.1f} с")
    print(f"\nГотово за {time.time() - begin:.0f} с. Таблицы лежат в папке {OUT}")


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = "rescore" if "--rescore" in args else "fresh" if "--fresh" in args else "normal"
    nums = [int(a) for a in args if a.isdigit()]
    asyncio.run(run(nums[0] if nums else None, mode))
