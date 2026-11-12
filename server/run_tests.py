"""Прогон тестовых фото через дефектоскоп.

Как разложить фото (папка tests рядом с main.py):
    tests/1/ok/        правильные фото «Светофора»
    tests/1/no_gnd/    фото с ошибкой (название папки = название ошибки, любое)
    tests/2/ok/ ...    и так для каждого модуля

Запуск (в папке server, с включённым venv):
    python run_tests.py        все модули
    python run_tests.py 1      только модуль 1

Результат: таблица в терминале и файл tests_result.csv (открывается в Excel).
Верно = на фото из папки ok дефектоскоп не нашёл ошибок,
а на фото из папки с ошибкой нашёл хотя бы одну.
Какую именно ошибку он нашёл, смотри в столбце «Что нашёл» — это надо проверить глазами.
"""
import asyncio
import csv
import sys
from pathlib import Path

import main

TESTS = Path(__file__).parent / "tests"
OUT = Path(__file__).parent / "tests_result.csv"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


async def run(only_module=None):
    if not TESTS.exists():
        print("Нет папки tests. Создай её рядом с main.py и разложи фото, как написано в начале файла.")
        return

    rows = []
    for mod_dir in sorted(p for p in TESTS.iterdir() if p.is_dir() and p.name.isdigit()):
        module = int(mod_dir.name)
        if only_module and module != only_module:
            continue
        if module not in main.CHECK_READY:
            print(f"Модуль {module}: дефектоскоп для него не включён, пропускаю")
            continue
        for case_dir in sorted(p for p in mod_dir.iterdir() if p.is_dir()):
            expect_ok = case_dir.name.lower() == "ok"
            for photo in sorted(p for p in case_dir.iterdir() if p.suffix.lower() in MIME):
                result, code = await main.run_check(photo.read_bytes(), MIME[photo.suffix.lower()],
                                                    module, use_cache=False)
                if code != 200:
                    verdict = "сбой"
                else:
                    has_errors = bool(result.get("errors"))
                    verdict = "верно" if has_errors != expect_ok else "неверно"
                found_text = " | ".join(result.get("errors") or []) or "ошибок нет"
                rows.append({
                    "Модуль": module,
                    "Случай": case_dir.name,
                    "Фото": photo.name,
                    "Ожидалось": "без ошибок" if expect_ok else "есть ошибка",
                    "Что нашёл": found_text,
                    "Не разглядел": len(result.get("unclear") or []),
                    "Итог": verdict,
                    "Секунд": result.get("seconds", ""),
                    "Модель": result.get("model", ""),
                })
                print(f"[{module}] {case_dir.name}/{photo.name}: {verdict}, {result.get('seconds', '?')} с")

    if not rows:
        print("Фото не найдены.")
        return

    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    print("\nИтог по модулям:")
    for module in sorted({r["Модуль"] for r in rows}):
        part = [r for r in rows if r["Модуль"] == module]
        good = sum(r["Итог"] == "верно" for r in part)
        fails = sum(r["Итог"] == "сбой" for r in part)
        times = [r["Секунд"] for r in part if isinstance(r["Секунд"], (int, float)) and r["Итог"] != "сбой"]
        avg = f"{sum(times) / len(times):.1f}" if times else "-"
        print(f"  Модуль {module}: верно {good} из {len(part)}, сбоев {fails}, среднее время {avg} с")
    print(f"\nТаблица сохранена: {OUT.name}")


if __name__ == "__main__":
    arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    asyncio.run(run(arg))
