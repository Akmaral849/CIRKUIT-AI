# Ищем, какие модели Gemini доступны твоему ключу и какие из них отвечают прямо сейчас.
# Запуск:  python models_scan.py   (сам закроется максимум через 4 минуты)
# Ключ берётся из .env и на экран НЕ выводится.
import json
import os
import threading
import time
import urllib.error
import urllib.request

threading.Timer(240, lambda: (print("\nСТОП: прошло 4 минуты."), os._exit(1))).start()
BASE = "https://generativelanguage.googleapis.com/v1beta"

key = None
for line in open(".env", encoding="utf-8"):
    if line.strip().startswith("GEMINI_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
if not key:
    print("В .env нет GEMINI_API_KEY")
    os._exit(1)
H = {"x-goog-api-key": key, "Content-Type": "application/json"}

# 1. Список моделей
names, token = [], ""
while True:
    url = BASE + "/models?pageSize=100" + (f"&pageToken={token}" if token else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20) as r:
        data = json.loads(r.read())
    for m in data.get("models", []):
        n = m["name"].replace("models/", "")
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        if any(bad in n for bad in ("embed", "imagen", "tts", "image", "live", "audio", "aqa", "learnlm", "gemma", "robotics", "computer")):
            continue
        if "gemini" in n:
            names.append(n)
    token = data.get("nextPageToken", "")
    if not token:
        break

# Сначала flash и flash-lite (быстрые и дешёвые), потом остальные; не больше 14 штук
names = sorted(set(names), key=lambda n: (0 if "flash" in n else 1, n), reverse=False)[:14]
print("Найдено подходящих моделей:", len(names))
print("-" * 70)

# 2. Проверка каждой
body = json.dumps({"contents": [{"parts": [{"text": "Ответь одним словом: работает?"}]}]}).encode()
ok = []
for n in names:
    t = time.time()
    try:
        req = urllib.request.Request(f"{BASE}/models/{n}:generateContent", data=body, headers=H)
        with urllib.request.urlopen(req, timeout=15) as r:
            json.loads(r.read())
        sec = time.time() - t
        ok.append((sec, n))
        print(f"OK          {sec:5.1f} с  {n}")
    except urllib.error.HTTPError as e:
        print(f"КОД {e.code}     {time.time() - t:5.1f} с  {n}")
    except Exception:
        print(f"НЕТ ОТВЕТА  {time.time() - t:5.1f} с  {n}")

print("-" * 70)
if ok:
    best = [n for _, n in sorted(ok)][:4]
    print("Работают сейчас (от быстрых к медленным):", ", ".join(n for _, n in sorted(ok)))
    print("\nПредлагаемая строка для .env (пришли её Claude перед тем, как вставлять):")
    print("GEMINI_MODELS=" + ",".join(best))
else:
    print("Сейчас не ответила ни одна модель.")
print("\nГотово. Пришли скриншот Claude.")
os._exit(0)
