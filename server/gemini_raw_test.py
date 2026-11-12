# Прямой запрос к Gemini без библиотеки google-genai: видно точный ответ Google.
# Запуск:  python gemini_raw_test.py   (сам закроется максимум через 80 секунд)
# Ключ берётся из .env и на экран НЕ выводится.
import json
import os
import threading
import time
import urllib.error
import urllib.request

threading.Timer(80, lambda: (print("\nСТОП: зависло больше 80 секунд."), os._exit(1))).start()

key, models = None, "gemini-3.8-flash,gemini-3.7-flash"
try:
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if line.startswith("GEMINI_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
        if line.startswith("GEMINI_MODELS="):
            models = line.split("=", 1)[1].strip()
except FileNotFoundError:
    print("Файл .env не найден в папке server")
    os._exit(1)
if not key:
    print("В .env нет строки GEMINI_API_KEY=...")
    os._exit(1)
print(f"Ключ найден (длина {len(key)} символов). Модели: {models}")
print("-" * 60)

body = json.dumps({"contents": [{"parts": [{"text": "Ответь одним словом: работает?"}]}]}).encode()
for model in [m.strip() for m in models.split(",") if m.strip()]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            text = data["candidates"][0]["content"]["parts"][0].get("text", "")
            print(f"OK     {model}: {time.time() - t:.1f} с -> {text.strip()[:40]}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read()).get("error", {})
            msg = f"{err.get('status', '')}: {err.get('message', '')[:160]}"
        except Exception:
            msg = ""
        print(f"КОД {e.code} {model}: {time.time() - t:.1f} с -> {msg}")
    except Exception as e:
        print(f"НЕТ ОТВЕТА {model}: {time.time() - t:.1f} с -> {type(e).__name__}: {str(e)[:100]}")
print("-" * 60)
print("Готово. Пришли скриншот Claude.")
os._exit(0)
