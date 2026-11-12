# Проверка Gemini: какие модели отвечают и почему не отвечают.
# Запуск (в папке server, с включённым venv):  python test_gemini.py
# Ключ берётся из .env и на экран НЕ выводится.
import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
if not key:
    print("Ключ не найден: проверь, что файл .env лежит в папке server и в нём есть GEMINI_API_KEY=...")
    raise SystemExit

client = genai.Client(api_key=key)
models = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.7-flash").split(",") if m.strip()]

print("Проверяю модели:", ", ".join(models))
print("-" * 60)
for model in models:
    start = time.time()
    try:
        r = client.models.generate_content(model=model, contents="Ответь одним словом: работает?")
        print(f"OK    {model}: ответил за {time.time() - start:.1f} с -> {(r.text or '').strip()[:40]}")
    except Exception as error:
        text = str(error)
        if "429" in text or "RESOURCE_EXHAUSTED" in text:
            why = "ЛИМИТ (429): закончилась бесплатная квота. Лечится оплатой."
        elif "503" in text or "UNAVAILABLE" in text or "overloaded" in text.lower():
            why = "ПЕРЕГРУЗКА (503): у Google много запросов. Бывает и на платном, но реже."
        elif "403" in text or "PERMISSION_DENIED" in text or "API key not valid" in text or "400" in text:
            why = "КЛЮЧ (400/403): ключ неверный или выключен. Оплата НЕ поможет, нужен новый ключ."
        elif "404" in text or "NOT_FOUND" in text:
            why = "МОДЕЛЬ (404): такой модели нет. Нужно поменять имя модели."
        else:
            why = "ДРУГОЕ: пришли этот текст Claude."
        print(f"ОШИБКА {model} через {time.time() - start:.1f} с -> {why}")
        print("       текст ошибки:", text[:200])
print("-" * 60)
print("Сделай скриншот этого окна и пришли Claude.")
