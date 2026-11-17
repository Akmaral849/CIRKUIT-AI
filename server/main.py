import asyncio
import hashlib
import json
import os
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

load_dotenv()
BASE_DIR = Path(__file__).parent

# ================== Голоса тьюторов (Silero, файл tts.py) ==================
# Работают там, где установлены torch, numpy и omegaconf (ноутбук). На Render их нет:
# тогда /tts отвечает 503, а сайт говорит голосом браузера.
try:
    import tts
    import threading
    threading.Thread(target=tts.load, daemon=True).start()   # голоса грузятся в фоне, сервер стартует сразу
    TTS_READY = True
except Exception as _tts_error:
    tts = None
    TTS_READY = False
    print("Голоса Silero выключены (нет torch/numpy/omegaconf):", _tts_error)

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    # Предел одного запроса к Google, в миллисекундах. Было 30 000: проверка фото с длинным
    # заданием иногда идёт дольше 30 с и обрывалась. Короткие пределы ниже (ATTEMPT_TIMEOUT) всё равно действуют.
    http_options=types.HttpOptions(timeout=int(os.getenv("HTTP_TIMEOUT_MS", "120000"))),
)

# ================== Настройки скорости ==================
# Платный ключ: ждём недолго и не крутим много кругов.
# Список моделей можно поменять в .env без правки кода:
# GEMINI_MODELS=gemini-3.8-flash,gemini-3.7-flash
# Дефектоскоп: сначала самые точные модели (3.8 лучше всех нашла ошибки на тестах), дальше запасные.
# 11.11 проверка models_scan.py: 3.8 и 3.7 перегружены (503), 3.6 и 3-flash-preview отвечали.
MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS",
          "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,gemini-3-flash-preview").split(",") if m.strip()]
# Чат: важнее быстро ответить, поэтому свой список из моделей, которые отвечали за 2-4 секунды.
CHAT_MODELS = [m.strip() for m in os.getenv("CHAT_MODELS",
               "gemini-3.6-flash,gemini-3-flash-preview,gemini-flash-lite-latest,gemini-3.5-flash").split(",") if m.strip()]
CHAT_ATTEMPT_TIMEOUT = float(os.getenv("CHAT_ATTEMPT_TIMEOUT", "10"))  # сек на одну модель в чате
CHAT_BUDGET = float(os.getenv("CHAT_BUDGET", "25"))                    # сек на весь ответ чата
# CHAT_MODE=ai (по умолчанию): на все вопросы, и на кнопки тоже, отвечает ИИ; заготовка — только если ИИ не ответил.
# CHAT_MODE=fast: на кнопки отвечает база знаний мгновенно, ИИ — только на свободные вопросы.
CHAT_MODE = os.getenv("CHAT_MODE", "ai").strip().lower()
ATTEMPT_TIMEOUT = float(os.getenv("ATTEMPT_TIMEOUT", "20"))  # сек на одну попытку
TOTAL_BUDGET = float(os.getenv("TOTAL_BUDGET", "35"))        # сек на всю проверку, дольше не ждём
gemini_lock = asyncio.Semaphore(int(os.getenv("MAX_PARALLEL", "4")))

# Уровень «размышления» модели. Пусто = как по умолчанию у модели.
# Можно попробовать в .env: GEMINI_THINKING=low (обычно быстрее). Проверять тестами run_tests.py.
THINKING = None
_level = os.getenv("GEMINI_THINKING", "").strip().lower()
if _level:
    try:
        THINKING = types.ThinkingConfig(thinking_level=_level)
    except Exception as error:
        print("GEMINI_THINKING не включился, работаю без него:", error)

# ================== Память сервера ==================
# Кэш хранится в файле check_cache.json: то же фото того же модуля проверяется мгновенно,
# даже после перезапуска сервера и даже если Google не отвечает (запасной режим для показа).
CACHE_FILE = BASE_DIR / "check_cache.json"
CACHE_SIZE = 300
LOG_FILE = BASE_DIR / "checks_log.jsonl"  # журнал всех проверок (для таблиц и будущей панели учителя)


def load_cache():
    try:
        return OrderedDict(json.loads(CACHE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return OrderedDict()


CHECK_CACHE = load_cache()


def save_cache():
    try:
        CACHE_FILE.write_text(json.dumps(CHECK_CACHE, ensure_ascii=False), encoding="utf-8")
    except Exception as error:
        print("Не удалось сохранить кэш:", error)


def log_check(entry):
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as error:
        print("Не удалось записать журнал:", error)


app = FastAPI()

# Какие сайты могут обращаться к серверу. Адрес выложенного сайта добавляется
# в настройках хостинга в переменной ALLOWED_ORIGINS (через запятую), код менять не нужно.
ORIGINS = ["http://127.0.0.1:5500", "http://localhost:5500"]
ORIGINS += [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_PHOTO_BYTES = 8 * 1024 * 1024

# Для каких модулей включён дефектоскоп (проверка по фото).
# 14.11: эталоны написаны по эталонным фото всех 7 модулей, проверка включена.
CHECK_READY = {1, 2, 3, 4, 5, 6, 7}

# Модули, у которых эталон ещё не сверен с собранным железом
UNVERIFIED = set()

# ================== База знаний 7 модулей ==================
# Файл modules_qa.json лежит рядом с main.py: название, зона, детали, подключение
# и быстрые вопросы с готовыми ответами. Править текст — только в этом файле.
QA_FILE = BASE_DIR / "modules_qa.json"


def load_qa():
    try:
        data = json.loads(QA_FILE.read_text(encoding="utf-8"))
        result = {m["id"]: m for m in data.get("modules", [])}
        print(f"База знаний: загружено модулей — {len(result)}")
        return result
    except Exception as error:
        print("Не удалось прочитать modules_qa.json:", error)
        return {}


QA = load_qa()


def norm(text):
    """Упрощаем текст для сравнения: маленькие буквы, ё -> е, без знаков препинания."""
    text = (text or "").lower().replace("ё", "е")
    keep = [ch if ch.isalnum() or ch == " " else " " for ch in text]
    return " ".join("".join(keep).split())


def qa_exact(module, message):
    """Ответ на быстрый вопрос модуля, если вопрос совпадает с кнопкой (или почти совпадает)."""
    msg = norm(message)
    if not msg:
        return None
    for item in QA.get(module, {}).get("quick", []):
        q = norm(item["q"])
        if msg == q or (len(msg) >= 15 and (msg in q or q in msg)):
            return item["a"]
    return None


def qa_closest(module, message):
    """Ближайший готовый ответ по общим словам — запасной вариант, когда ИИ не ответил."""
    words = {w for w in norm(message).split() if len(w) > 3}
    best, best_score = None, 0
    for item in QA.get(module, {}).get("quick", []):
        q_words = {w for w in norm(item["q"]).split() if len(w) > 3}
        # совпадение по началу слова: «резистор» и «резистора» считаем одним словом
        score = sum(1 for w in words if any(w[:5] == x[:5] for x in q_words))
        if score > best_score:
            best, best_score = item["a"], score
    return best if best_score >= 1 else None


def qa_context(module):
    """Текст о модуле для ИИ: что за модуль, как подключён и готовые объяснения."""
    m = QA.get(module)
    if not m:
        return ""
    lines = [f"Модуль № {m['id']} «{m['name']}», зона города «{m['zone']}».",
             "Детали: " + ", ".join(m.get("parts", [])) + "."]
    if m.get("pins"):
        lines.append("Подключение: " + m["pins"])
    lines.append("База знаний модуля (это проверенные объяснения: опирайся на них, не противоречь им, "
                 "но отвечай своими словами и в своём характере):")
    for item in m.get("quick", []):
        lines.append(f"Вопрос: {item['q']}\nОтвет: {item['a']}")
    return "\n".join(lines)

CHAT_SYSTEM = """Ты помощник учебной платформы Circuit AI. Ты помогаешь школьникам разбираться в Arduino и электронике.
Правила:
- Отвечай по-русски, простым языком, как доброжелательный наставник. Объясняй сложное через понятные примеры из жизни.
- Отвечай коротко: обычно 3-6 предложений. Если ученик просит подробнее, отвечай подробнее.
- Тебе можно отвечать на вопросы про Arduino, электронику, электричество, датчики, программирование микроконтроллеров, как работают устройства и технологии вокруг нас.
- Если вопрос совсем не по теме (политика, домашка по другим предметам, личные темы), вежливо скажи, что ты помогаешь с Arduino и электроникой, и предложи вопрос по теме.
- Если ученик спрашивает про свою схему и для модуля есть результат дефектоскопа, опирайся на него. Объясни, что не так, где это на схеме и как исправить, по шагам. Не выдумывай того, чего в результате нет. Предлагать сфотографировать схему и нажать «Проверить схему» можно только там, где ниже сказано, что проверка по фото для модуля доступна.
- Ты не видишь фото сам, ты знаешь только эталон модуля и результат проверки, если он есть.
- Не используй разметку: никаких звёздочек, решёток и markdown. Пиши обычным текстом. Примеры кода пиши просто строками.
- Если ученик просит готовое решение задачи, сначала дай подсказку, а потом при необходимости пример.
- Ответ могут озвучивать голосом, поэтому пиши короткими предложениями, без списков со звёздочками и без длинных формул.
Как отвечать хорошо (как сильный инженер-наставник):
- Сначала про себя разберись, в чём суть вопроса и какая физика или логика программы за этим стоит. Потом отвечай.
- Объясняй причинно-следственной цепочкой: что происходит → почему → к чему это приводит.
- Используй реальное подключение модуля ниже: называй конкретные пины, детали и строки программы этого модуля.
- Если ученик описывает поломку, назови 1–3 самые вероятные причины по порядку и как проверить каждую
  (посмотреть провод, проверить контакт, вывести значение в Монитор порта).
- Если описание неясное, задай один уточняющий вопрос.
- Если в базе знаний ниже есть ответ на этот вопрос, он проверен на настоящем железе: не противоречь ему, но объясняй своими словами и глубже.
- Если чего-то не знаешь точно, скажи об этом честно, а не выдумывай."""


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    defect_result: dict | None = None
    module: int = 1
    avatar: str = "dex"


# Характер каждого аватара (тот же id, что в avatars.js на сайте).
# Знания одинаковые, меняется только манера объяснять.
AVATAR_STYLES = {
    "dex": ("Тебя зовут Декс, ты робот-подросток, «свой парень», говоришь как современный школьник. Говори на ты, бодро, коротко "
            "и с юмором. Часто начинай с «Йоу!» или «Опа», используй школьный сленг: «бро», «изи», «го», «чекнем», «косяк», "
            "«пофиксим», «имба», «рил», «жиза», «кайф». Сленг — 2–3 слова на ответ, чтобы смысл оставался понятным. "
            "Без мата, грубости и оскорблений. Ошибку называй прямо, но всегда доводи до решения."),
    "lumi": ("Тебя зовут Люми, ты милая весёлая девочка-лампочка. Говори игриво, тепло и восторженно: «Приветик!», «Ой!», "
             "«Ура-ура!», «Вау!», уменьшительные слова («схемка», «проводочек», «ошибочка»). Подбадривай, никогда не ругай "
             "за ошибки, хвали за каждый шаг и объясняй просто. Без смайликов."),
    "om": ("Тебя зовут Ом, ты мудрый спокойный совёнок-профессор. Говори размеренно и уважительно, любишь слова «Итак», "
           "«Любопытно», «Заметь», «Подумай». Твоя фирменная фраза — совиное «Уху!»: иногда (не в каждом ответе) "
           "начинай с неё. Сначала задай один наводящий вопрос, чтобы ученик догадался сам. "
           "Если он не понял или просит прямо, объясни ответ и почему всё работает именно так."),
}
AVATAR_STYLES["volt"] = AVATAR_STYLES["dex"]   # старые имена из прошлой версии сайта
AVATAR_STYLES["iskra"] = AVATAR_STYLES["lumi"]


def make_config(system_prompt, as_json=False):
    options = {"system_instruction": system_prompt}
    if as_json:
        options["response_mime_type"] = "application/json"
        options["temperature"] = 0
    if THINKING is not None:
        options["thinking_config"] = THINKING
    return types.GenerateContentConfig(**options)


async def ask_gemini(contents, config, models=None, attempt_timeout=None, budget=None):
    """Каждая модель пробуется по одному разу, потом ещё раз первая.
    Возвращает (ответ, имя модели) или (None, None), если Google не ответил за TOTAL_BUDGET секунд."""
    models = models or MODELS
    attempt_timeout = attempt_timeout or ATTEMPT_TIMEOUT
    budget = budget or TOTAL_BUDGET
    begin = time.time()
    tries = models + models[:1]
    for i, model in enumerate(tries):
        left = budget - (time.time() - begin)
        if left < 4:
            print("Время на ответ закончилось")
            break
        if i == len(models):
            await asyncio.sleep(1.5)  # короткая пауза перед последней попыткой
            left -= 1.5
        start = time.time()
        try:
            async with gemini_lock:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(model=model, contents=contents, config=config),
                    timeout=min(attempt_timeout, left),
                )
            if not response or not response.text:
                raise ValueError("пустой ответ")
            print(f"[{model}] ответил за {time.time() - start:.1f} сек")
            return response, model
        except asyncio.TimeoutError:
            print(f"[{model}] не успел за {time.time() - start:.1f} сек")
        except Exception as error:
            print(f"[{model}] ошибка через {time.time() - start:.1f} сек: {str(error)[:200]}")
    return None, None


# ================== Дефектоскоп: 7 модулей Smart City Lab ==================
# Эталоны написаны по эталонным фото из папки photos (снимки 13-14.11.2026).
# Важно: модули стоят парами на одной макетной плате (плата 1: модули 1 и 2,
# плата 3: модули 4 и 5, плата 4: модули 6 и 7). Поэтому на фото всегда видны детали
# соседнего модуля. ИИ получает их описание и не должен считать их ошибкой.
#
# Как устроена проверка:
# 1) ИИ отвечает на узкие вопросы по фото (есть ли деталь, сколько резисторов,
#    в какое гнездо Arduino приходит провод) и к каждому ответу пишет evidence.
# 2) Итог считает код (build_module_result): ошибка ставится только если ИИ описал,
#    что именно видит. Нет описания — пункт уходит в «Не удалось рассмотреть».
# 3) У каждой ошибки есть тип (tag). По типам скрипт eval_photos.py считает точность.
#
# Типы ошибок (tag):
#   part      — нет нужной детали
#   resistor  — не хватает резистора
#   polarity  — светодиод перевёрнут
#   pin       — провод не в том гнезде Arduino (по списку занятых гнёзд)
#   trace     — провод от конкретной ножки детали идёт не в то гнездо
#   wire      — к детали подходят не все провода
#   button    — кнопка стоит не поперёк канавки
#   beam      — излучатель не направлен на фоторезистор
#   gnd       — нет провода из GND Arduino
#   hanging   — висящий провод (в том числе висящая земля)
# Тип можно временно выключить без правки кода: в .env строка CHECK_OFF=polarity,pin

# CHECK_COMPARE=1 в .env: ИИ получает два фото — эталон (папка server/etalons, m1.jpg … m7.jpg) и фото ученика —
# и сравнивает. CHECK_COMPARE=0 (или нет строки) — старая проверка по одному фото.
# Ключ кэша не меняется, поэтому демо-кэш работает в обоих режимах.
COMPARE = os.getenv("CHECK_COMPARE", "0").strip().lower() in ("1", "true", "yes", "on")
ETALON_DIR = BASE_DIR / "etalons"
_ETALON_BYTES = {}


def etalon_image(module):
    """Эталонное фото модуля (байты) или None, если файла нет."""
    if module not in _ETALON_BYTES:
        path = ETALON_DIR / f"m{module}.jpg"
        _ETALON_BYTES[module] = path.read_bytes() if path.exists() else None
    return _ETALON_BYTES[module]


def compare_on(module):
    return COMPARE and etalon_image(module) is not None


COMPARE_RULES = """Тебе дают ДВА фото.
ФОТО 1 — ЭТАЛОН: этот же модуль собран правильно. На нём видно, где стоят все детали и резисторы, куда идут провода
и в какие гнёзда Arduino они воткнуты.
ФОТО 2 — СБОРКА УЧЕНИКА. Все ответы, evidence и рамки box — только про ФОТО 2.
Как пользоваться эталоном:
- Сначала найди на ФОТО 2 те же места, что на эталоне: каждую деталь, каждый резистор, каждый провод, гнёзда Arduino.
- Сравни место за местом. Если на ФОТО 2 детали или резистора нет там, где он есть на эталоне, если провод идёт в другое
  гнездо, если провода из GND нет или его конец висит, если деталь развёрнута иначе — это ошибка, отвечай по ФОТО 2.
- Ракурс, свет, масштаб, цвет проводов и положение платы на фото могут отличаться — это НЕ ошибка.
- Не переноси ответы с эталона: если на ФОТО 2 место не видно, отвечай cannot_see или null."""

CHECK_VERSION = "v5-7mod"   # меняется при изменении вопросов, чтобы не отдавать старые ответы из кэша
CHECK_OFF = {t.strip() for t in os.getenv("CHECK_OFF", "").split(",") if t.strip()}

# Какие гнёзда Arduino заняты сигнальными проводами на каждой плате (GND и 5V не считаем).
# SDA и SCL у Arduino Uno — это те же A4 и A5, поэтому код считает их одним гнездом.
PLATES = {
    1: {"name": "Плата 1 «Транспорт»", "digital": {"2", "3", "4", "5", "6", "8", "9", "10"}, "analog": set()},
    2: {"name": "Плата 2 «Энергия»", "digital": {"5", "6", "7"}, "analog": {"A0"}},
    3: {"name": "Плата 3 «Экология»", "digital": {"2", "9", "10", "11"}, "analog": {"A0", "A4", "A5"}},
    4: {"name": "Плата 4 «Безопасность»", "digital": {"5", "6", "8"}, "analog": {"A0", "A1"}},
}

# Описание деталей каждого модуля так, как они выглядят на фото
LOOKS = {
    1: ("светодиоды светофора (красный, жёлтый, зелёный) в один ряд и резисторы с цветными полосками; "
        "круглая синяя кнопка пешехода; чёрный круглый зуммер с наклейкой или отверстием сверху"),
    2: ("датчик расстояния HC-SR04 (синяя плата с двумя серебристыми цилиндрами-«глазами», 4 ножки: VCC, Trig, Echo, Gnd); "
        "синий сервопривод SG90 на длинном кабеле из трёх проводов (коричневый, красный, оранжевый), "
        "кабель подключён к перемычкам через чёрный разъём. Резисторов у этого модуля нет"),
    3: ("светодиоды-фонари в один ряд и резисторы с цветными полосками; "
        "фоторезистор (маленький круглый диск с рисунком-змейкой, две тонкие ножки) без отдельного резистора"),
    4: ("датчик температуры и влажности DHT11 (голубой корпус с решёткой, 4 ножки) на макетной плате; "
        "экран LCD 1602 (зелёная плата с синим экраном) с чёрной платой I2C сзади, от неё 4 провода: GND, VCC, SDA, SCL"),
    5: ("красная плата звукового датчика с микрофоном (чёрный цилиндр) и синим подстроечным резистором, "
        "4 контакта, подключена проводами; маленький чёрный модуль RGB-светодиода с прозрачным светодиодом, "
        "без отдельных резисторов"),
    6: ("голый ИК-диод (чёрный корпус как у светодиода, две ножки, без платы-модуля); красный светодиод тревоги; "
        "чёрный круглый зуммер"),
    7: ("фоторезистор (маленький круглый диск с рисунком-змейкой); зелёные светодиоды: "
        "один — излучатель луча, светит на фоторезистор, второй — светодиод тревоги. "
        "Модуль пользуется тем же зуммером, что и пожарная сигнализация"),
}


def q_status(key, label, tag, q, ok=("yes",), bad=("no",), options="yes / no / cannot_see"):
    return {"key": key, "kind": "status", "label": label, "tag": tag, "ok": set(ok), "bad": set(bad),
            "q": f"{q} status: {options}."}


def q_count(key, label, tag, q, expected, allowed=None):
    # Прогон 14.11: когда ИИ просто называл число, он «досчитывал» до ожидаемого (видел 3 резистора там, где их 2).
    # Поэтому просим сначала перечислить каждую найденную деталь по месту, а число считает код.
    return {"key": key, "kind": "count", "label": label, "tag": tag, "expected": expected,
            "allowed": set(allowed or [expected]),
            "q": (f"{q} Посмотри внимательно на каждое место отдельно. found: список, в котором КАЖДАЯ реально видимая деталь "
                  "описана отдельной строкой (где стоит, рядом с чем). Не добавляй деталь, если не видишь её на фото. "
                  "value: сколько строк в found, или null, если не можешь сосчитать.")}


def q_trace(key, label, tag, q, expected):
    return {"key": key, "kind": "trace", "label": label, "tag": tag, "expected": set(expected),
            "q": (f"{q} Проследи провод (он может идти через ряд макетной платы) и прочитай подпись гнезда Arduino, "
                  "в которое он воткнут. value: подпись гнезда, например \"9\" или \"A0\", или null, если провод не проследить "
                  "или подпись не прочитать.")}


POLARITY_Q = ("у светодиодов этого модуля видно, какой стороной они стоят? Длинная ножка (анод) или сторона корпуса без среза "
              "должна быть в ряду, куда приходит провод от пина Arduino. Отвечай reversed только если ясно видишь, "
              "что хотя бы один светодиод стоит наоборот.")

MODULES = {
    1: {
        "title": "Умный перекрёсток", "plate": 1, "neighbor": 2,
        "pins": {"2", "4", "5", "6", "8"},
        "items": [
            q_status("leds", "Светодиоды", "part", "есть ли на макетной плате три светодиода светофора: красный, жёлтый, зелёный?"),
            q_count("resistor_count", "Резисторы", "resistor",
                    "сколько резисторов стоят рядом со светодиодами светофора (ножка резистора в одном ряду с ножкой светодиода)?", 3),
            q_status("led_polarity", "Полярность светодиодов", "polarity", POLARITY_Q, ok=("ok",), bad=("reversed",),
                     options="ok / reversed / cannot_see"),
            q_status("button", "Кнопка", "part", "есть ли на макетной плате круглая синяя кнопка пешехода?"),
            q_status("button_across", "Кнопка через канавку", "button",
                     "стоит ли кнопка поперёк центральной канавки макетной платы: две ножки по одну сторону канавки, две по другую?"),
            q_status("buzzer", "Зуммер", "part", "есть ли на макетной плате чёрный круглый зуммер?"),
        ],
        "manual": [
            "Красный светодиод — пин 4, жёлтый — пин 5, зелёный — пин 6 (провода не перепутаны между собой)",
            "У каждого светодиода длинная ножка идёт к пину, короткая через резистор к GND",
            "Кнопка: один провод — пин 2, второй — GND, к ножкам по диагонали",
            "Зуммер: плюс — пин 8, минус — GND",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу: светофор должен переключаться, а кнопка — включать звук для пешехода.",
    },
    2: {
        "title": "Умная парковка", "plate": 1, "neighbor": 1,
        "pins": {"3", "9", "10"},
        "pairs": [("trig", "echo", "Trig и Echo")],
        "items": [
            q_status("sensor", "Датчик HC-SR04", "part", "есть ли на фото датчик расстояния HC-SR04?"),
            q_count("sensor_wires", "Провода датчика", "wire",
                    "к скольким из четырёх ножек датчика HC-SR04 подходят провода (прямо или через ряд макетной платы)?", 4),
            q_trace("trig", "Trig", "trace", "в какое гнездо Arduino приходит провод от ножки Trig датчика?", ["9"]),
            q_trace("echo", "Echo", "trace", "в какое гнездо Arduino приходит провод от ножки Echo датчика?", ["10"]),
            q_trace("servo_signal", "Сигнал сервопривода", "trace",
                    "в какое гнездо Arduino приходит оранжевый (сигнальный) провод сервопривода "
                    "(через разъём и перемычку)?", ["3"]),
        ],
        "manual": [
            "VCC датчика — к плюсу (5V), Gnd датчика — к минусу, не перепутаны",
            "Сервопривод: коричневый — минус, красный — плюс, оранжевый — пин 3",
            "Перед «глазами» датчика нет проводов",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу и поднеси ладонь к датчику ближе 10 см: шлагбаум должен подняться.",
    },
    3: {
        "title": "Уличное освещение", "plate": 2, "neighbor": None,
        "pins": {"5", "6", "7", "A0"},
        "items": [
            q_count("led_count", "Фонари", "part", "сколько светодиодов-фонарей на макетной плате?", 3),
            q_count("resistor_count", "Резисторы", "resistor",
                    "сколько резисторов с цветными полосками стоят рядом со светодиодами? Фоторезистор не считай.", 3),
            q_status("led_polarity", "Полярность светодиодов", "polarity", POLARITY_Q, ok=("ok",), bad=("reversed",),
                     options="ok / reversed / cannot_see"),
            q_status("photoresistor", "Фоторезистор", "part", "есть ли на макетной плате фоторезистор?"),
            q_trace("photo_pin", "Провод фоторезистора", "trace",
                    "в какое гнездо Arduino приходит провод из ряда одной из ножек фоторезистора (не GND)?", ["A0"]),
        ],
        "manual": [
            "Вторая ножка фоторезистора соединена с GND",
            "В программе pinMode(A0, INPUT_PULLUP): внешний резистор для фоторезистора не нужен",
            "У каждого светодиода длинная ножка к пину (5, 6, 7), короткая через резистор к GND",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу, подожди 2 секунды и закрой фоторезистор ладонью: фонари должны включиться.",
    },
    4: {
        "title": "Метеостанция", "plate": 3, "neighbor": 5,
        "pins": {"2", "A4", "A5"},
        "pairs": [("sda", "scl", "SDA и SCL")],
        "items": [
            q_status("dht", "Датчик DHT11", "part", "есть ли на макетной плате датчик DHT11 (голубой корпус с решёткой)?"),
            q_status("lcd", "Экран LCD", "part", "есть ли на фото экран LCD 1602 с платой I2C?"),
            q_count("lcd_wires", "Провода экрана", "wire",
                    "к скольким из четырёх контактов платы I2C экрана (GND, VCC, SDA, SCL) подходят провода?", 4),
            q_trace("dht_data", "Сигнал DHT11", "trace",
                    "в какое гнездо Arduino приходит провод от сигнальной ножки DATA датчика DHT11 "
                    "(вторая слева, если смотреть на решётку)?", ["2"]),
            q_trace("sda", "SDA экрана", "trace", "в какое гнездо Arduino приходит провод от контакта SDA платы I2C?", ["A4"]),
            q_trace("scl", "SCL экрана", "trace", "в какое гнездо Arduino приходит провод от контакта SCL платы I2C?", ["A5"]),
        ],
        "manual": [
            "DHT11: VCC — 5V, GND — GND, не перепутаны",
            "Экран: VCC — 5V, GND — GND, SDA — A4, SCL — A5",
            "Если экран светится, но букв нет, покрути синий винт контраста на плате I2C",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу: на экране должны появиться температура и влажность.",
    },
    5: {
        "title": "Шумомер улицы", "plate": 3, "neighbor": 4,
        "pins": {"9", "10", "11", "A0"},
        "items": [
            q_status("mic", "Звуковой датчик", "part", "есть ли на фото красная плата звукового датчика с микрофоном?"),
            q_trace("mic_out", "Выход AO датчика", "trace",
                    "в какое гнездо Arduino приходит провод от контакта AO (аналоговый выход) звукового датчика?", ["A0"]),
            q_status("rgb", "RGB-модуль", "part", "есть ли на фото маленький чёрный модуль RGB-светодиода?"),
            q_count("rgb_wires", "Провода RGB", "wire",
                    "к скольким из четырёх контактов RGB-модуля подходят провода (прямо или через ряд макетной платы)?", 4),
        ],
        "manual": [
            "Звуковой датчик: плюс — 5V, G — GND",
            "RGB-модуль: общий контакт — GND, R — пин 9, G — пин 10, B — пин 11",
            "Пока Arduino 2 секунды слушает тишину после включения, не шуми",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу, подожди 2 секунды и хлопни в ладоши: RGB должен стать красным.",
    },
    6: {
        "title": "Пожарная сигнализация", "plate": 4, "neighbor": 7,
        "pins": {"5", "8", "A1"},
        "items": [
            q_status("ir", "ИК-диод", "part", "есть ли на макетной плате голый ИК-диод (чёрный корпус, две ножки)?"),
            q_trace("ir_pin", "Провод ИК-диода", "trace",
                    "в какое гнездо Arduino приходит провод из ряда ножки ИК-диода (не GND)?", ["A1"]),
            q_status("fire_led", "Светодиод тревоги", "part", "есть ли на макетной плате красный светодиод пожарной тревоги?"),
            q_status("fire_resistor", "Резистор светодиода", "resistor",
                     "стоит ли рядом с красным светодиодом резистор (ножка резистора в одном ряду с ножкой светодиода)?"),
            q_status("led_polarity", "Полярность светодиода", "polarity", POLARITY_Q, ok=("ok",), bad=("reversed",),
                     options="ok / reversed / cannot_see"),
            q_status("buzzer", "Зуммер", "part", "есть ли на макетной плате чёрный круглый зуммер?"),
        ],
        "manual": [
            "Вторая ножка ИК-диода соединена с GND",
            "Красный светодиод: длинная ножка — пин 5, короткая через резистор к GND",
            "Зуммер: плюс — пин 8, минус — GND",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу и поднеси зажигалку или пульт от телевизора к ИК-диоду: должна сработать тревога.",
    },
    7: {
        "title": "Охрана здания", "plate": 4, "neighbor": 6,
        "pins": {"6", "A0"},
        "items": [
            q_status("photoresistor", "Фоторезистор", "part", "есть ли на макетной плате фоторезистор?"),
            q_count("green_leds", "Зелёные светодиоды", "part", "сколько зелёных светодиодов на макетной плате?", 2),
            q_count("resistor_count", "Резисторы", "resistor",
                    "сколько резисторов стоят рядом с зелёными светодиодами (ножка резистора в одном ряду с ножкой светодиода)?", 2),
            q_status("beam", "Луч на фоторезистор", "beam",
                     "направлен ли один из зелёных светодиодов (излучатель) головкой прямо на фоторезистор с расстояния "
                     "нескольких сантиметров? aimed — смотрит прямо на фоторезистор, off — явно смотрит мимо.",
                     ok=("aimed",), bad=("off",), options="aimed / off / cannot_see"),
            q_trace("photo_pin", "Провод фоторезистора", "trace",
                    "в какое гнездо Arduino приходит провод из ряда одной из ножек фоторезистора (не GND)?", ["A0"]),
        ],
        "manual": [
            "Вторая ножка фоторезистора соединена с GND",
            "Излучатель горит всегда: через резистор к 5V",
            "Светодиод тревоги: длинная ножка — пин 6, короткая через резистор к GND",
        ],
        "ok": "Детали, земля и пины выглядят правильно. Загрузи программу, подожди 2 секунды и проведи рукой между излучателем и фоторезистором: должен засчитаться проход.",
    },
}

# Правило про рамки: по ним сайт рисует на фото, где деталь или ошибка
BOX_RULE = ("- В каждом пункте добавь box: рамку вокруг этой детали или провода на фото в виде "
            "[ymin, xmin, ymax, xmax], числа от 0 до 1000 (доля высоты и ширины фото). "
            "Если пункт про несколько деталей, обведи их все одной рамкой. Если не видно или не уверен, ставь null.")

COMMON_RULES = """Строгие правила:
- Описывай только то, что реально видишь. Если не видно, ставь "cannot_see" или null. Не достраивай «как обычно бывает».
- В каждом evidence коротко объясни, что именно видишь и где (по цвету провода, по положению).
- Провод считается висящим, если один его конец явно не воткнут и торчит в воздухе или лежит на столе. Если конец провода просто уходит за край кадра, это не «висит», а "cannot_see". Провода, воткнутые в разъём кабеля (например кабеля сервопривода), не висят.
- Подписи гнёзд напечатаны на плате Arduino у колодок: цифровые 0–13 (у некоторых значок ~), аналоговые A0–A5, питание 5V, 3.3V, GND, VIN. Гнёзда SDA и SCL рядом с AREF пиши как SDA и SCL.
""" + BOX_RULE


def module_system(module):
    """Текст задания для ИИ по модулю: что на плате, на какие вопросы ответить и в каком виде."""
    cfg = MODULES[module]
    plate = PLATES[cfg["plate"]]
    items = [it for it in cfg["items"] if it["tag"] not in CHECK_OFF]

    about = f"Проверяемый модуль «{cfg['title']}» ({plate['name']}). Его детали: {LOOKS[module]}."
    if cfg["neighbor"]:
        nb = cfg["neighbor"]
        about += (f"\nНа этой же макетной плате и к этой же Arduino подключён соседний модуль «{MODULES[nb]['title']}»: "
                  f"{LOOKS[nb]}. Детали соседнего модуля — это НЕ ошибка и НЕ лишние детали. "
                  "В вопросах про детали считай только детали проверяемого модуля. "
                  "Вопросы pins, gnd_pin, gnd_other_end и hanging_wires относятся ко всей плате.")
    about += ("\nПлюс и минус на макетной плате подведены через отдельные столбцы (узел питания), "
              "а не только через боковые линии: это правильно.")

    lines = [f"{i}. {it['key']}: {it['q']}" for i, it in enumerate(items, 1)]
    n = len(lines)
    if "pin" not in CHECK_OFF:
        n += 1
        lines.append(f"{n}. pins: перечисли подписи всех гнёзд Arduino, в которые воткнуты провода: "
                     "digital — в цифровой колодке (0–13), analog — в колодке ANALOG IN (A0–A5) и гнёзда SDA, SCL. "
                     "GND, 5V, 3.3V, VIN, AREF не перечисляй. Если колодку не видно или подписи не прочитать, "
                     "ставь null вместо списка этой колодки.")
    lines.append(f"{n+1}. power_wires: посмотри на колодку POWER Arduino (гнёзда IOREF, RESET, 3.3V, 5V, GND, GND, VIN) "
                 "и на гнездо GND в цифровой колодке рядом с 13. Перечисли ТОЛЬКО те гнёзда, в которых реально торчит "
                 "штекер провода: [{\"socket\": \"5V\", \"color\": \"красный\"}]. Пустые гнёзда не пиши. "
                 "Если колодку POWER не видно, ставь null.")
    lines.append(f"{n+2}. gnd_other_end: куда воткнут второй конец провода из гнезда GND (если он есть)? status: rail (в отверстие макетной платы: "
                 "в боковую линию, ряд или столбец) / hanging (висит в воздухе, никуда не воткнут) / cannot_see.")
    lines.append(f"{n+3}. hanging_wires: список проводов, у которых явно висит конец в воздухе, как массив объектов "
                 "{\"color\": \"...\", \"evidence\": \"...\", \"box\": [...]}. Пустой массив, если таких нет или не видно.")

    box = '"box": [ymin, xmin, ymax, xmax]'
    example = ['"no_circuit": false']
    for it in items:
        if it["kind"] == "count":
            example.append(f'"{it["key"]}": {{"found": ["..."], "value": N, "evidence": "...", {box}}}')
        elif it["kind"] == "trace":
            example.append(f'"{it["key"]}": {{"value": "...", "evidence": "...", {box}}}')
        else:
            example.append(f'"{it["key"]}": {{"status": "...", "evidence": "...", {box}}}')
    if "pin" not in CHECK_OFF:
        example.append('"pins": {"digital": ["..."], "analog": ["..."], "evidence": "...", ' + box + '}')
    example.append('"power_wires": [{"socket": "...", "color": "..."}]')
    example.append('"gnd_other_end": {"status": "...", "evidence": "...", ' + box + '}')
    example.append('"hanging_wires": [{"color": "...", "evidence": "...", ' + box + '}]')

    compare = ("\n\n" + COMPARE_RULES) if compare_on(module) else ""
    return ("Ты проверяющий на учебной платформе Circuit AI. Ты смотришь на фото схемы на Arduino Uno и макетной плате "
            "и отвечаешь на конкретные вопросы.\n\n" + about + compare + "\n\n" + COMMON_RULES
            + "\n\nВопросы:\n" + "\n".join(lines)
            + "\n\nЕсли на фото нет электронной схемы, верни {\"no_circuit\": true}.\n\n"
            "Верни ТОЛЬКО JSON:\n{" + ",\n ".join(example) + "}")


# Чат знает эталон того модуля, который открыт у ученика (кратко, из тех же данных)
ETALONS = {m: f"Модуль «{cfg['title']}», {PLATES[cfg['plate']]['name']}. Детали: {LOOKS[m]}."
           for m, cfg in MODULES.items()}


def text_of(item, key="evidence"):
    return ((item or {}).get(key) or "").strip() if isinstance(item, dict) else ""


def valid_box(box):
    """Рамка [ymin, xmin, ymax, xmax] от 0 до 1000, иначе None."""
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        y1, x1, y2, x2 = [int(round(float(v))) for v in box]
    except (TypeError, ValueError):
        return None
    if not (0 <= y1 < y2 <= 1000 and 0 <= x1 < x2 <= 1000):
        return None
    return [y1, x1, y2, x2]


def pin_label(value):
    """Приводит подпись гнезда к одному виду: '~9', 'D9', 'pin 9' -> '9'; 'a0' -> 'A0'; SDA -> A4, SCL -> A5."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().upper().replace("~", "").replace(" ", "")
    for prefix in ("PIN", "D"):
        if text.startswith(prefix) and text[len(prefix):].isdigit():
            text = text[len(prefix):]
    if text == "SDA":
        return "A4"
    if text == "SCL":
        return "A5"
    if text.isdigit() and 0 <= int(text) <= 13:
        return str(int(text))
    if len(text) == 2 and text[0] == "A" and text[1] in "012345":
        return text
    return None


def pin_list(values):
    """Список подписей или None, если ИИ не смог прочитать колодку."""
    if not isinstance(values, list):
        return None
    out = []
    for v in values:
        p = pin_label(v)
        if p and p not in out:
            out.append(p)
    return out


class Collector:
    """Собирает итог проверки, типы ошибок и рамки для подсветки на фото."""

    def __init__(self):
        self.found, self.errors, self.unclear, self.marks, self.tags = [], [], [], [], []

    def add(self, kind, label, text, item=None, tag=None):
        {"ok": self.found, "error": self.errors, "unclear": self.unclear}[kind].append(text)
        if kind == "error":
            self.tags.append(tag or "other")
        box = valid_box((item or {}).get("box")) if isinstance(item, dict) else None
        if box and kind != "unclear":
            self.marks.append({"kind": kind, "label": label, "box": box})


NO_CIRCUIT = {"status": "no_circuit", "found": [], "missing": [], "errors": [], "error_tags": [],
              "unclear": [], "manual": [], "marks": [],
              "message": "Я не вижу на фото электронную схему. Сними её сверху, при хорошем свете."}


def finish(c, manual, ok_message):
    if c.errors:
        status = "errors"
        message = "Нашла возможные ошибки. Проверь пункты в «Ошибках», поправь схему и сфотографируй снова."
    elif c.unclear:
        status = "unclear"
        message = "Часть схемы по фото подтвердить не получилось. Попробуй переснять сверху и ближе."
    else:
        status = "parts_ok"
        message = ok_message
    return {"status": status, "found": c.found, "missing": [], "errors": c.errors, "error_tags": c.tags,
            "unclear": c.unclear, "manual": manual, "marks": c.marks, "message": message}


def check_item(c, it, raw):
    item = raw.get(it["key"])
    item = item if isinstance(item, dict) else {}
    label, tag = it["label"], it["tag"]

    if it["kind"] == "count":
        value = item.get("value")
        found = item.get("found")
        if isinstance(found, list):
            value = len([f for f in found if str(f).strip()])
        if isinstance(value, int) and not isinstance(value, bool) and text_of(item):
            if value in it["allowed"]:
                c.add("ok", label, f"{label} ({value}): " + text_of(item), item)
            elif 0 <= value < min(it["allowed"]):
                c.add("error", label, f"{label}: видно {value}, а нужно {it['expected']}. " + text_of(item), item, tag)
            else:
                c.add("unclear", label, f"{label}: насчитано {value}, проверь сам")
        else:
            c.add("unclear", label, f"{label}: сосчитать по фото не получилось")

    elif it["kind"] == "trace":
        value = pin_label(item.get("value"))
        expected = sorted(it["expected"])
        if value and text_of(item):
            same_header = value.startswith("A") == expected[0].startswith("A")
            if value in it["expected"]:
                c.add("ok", label, f"{label}: провод в гнезде {value}. " + text_of(item), item)
            elif same_header:
                # Прогон 14.11: ИИ часто ошибается на одно-два гнезда при чтении подписей,
                # поэтому промах внутри одной колодки — не ошибка, а «проверь сам».
                c.add("unclear", label, f"{label}: по фото похоже на гнездо {value}, а нужно {' или '.join(expected)}. "
                      "Подписи гнёзд читаются неточно — проверь это место сам")
            else:
                c.add("error", label, f"{label}: провод пришёл в гнездо {value}, а нужно {' или '.join(expected)}. "
                      + text_of(item), item, tag)
        else:
            c.add("unclear", label, f"{label}: проследить провод до гнезда Arduino не получилось, проверь сам "
                  f"(нужно {' или '.join(expected)})")

    else:
        status = item.get("status")
        if status in it["ok"] and text_of(item):
            c.add("ok", label, f"{label}: " + text_of(item), item)
        elif status in it["bad"] and text_of(item):
            c.add("error", label, f"{label}: " + text_of(item), item, tag)
        elif tag == "polarity":
            pass  # полярность по фото обычно не видна, она уже есть в списке «Проверь сам»
        else:
            c.add("unclear", label, f"{label}: по фото подтвердить не получилось")


def pin_order(label):
    """Порядковый номер гнезда для сравнения: 9 < 10, A4 < A5."""
    return int(label[1:]) if label.startswith("A") else int(label)


def check_pair(c, cfg, raw, first, second, title):
    """Два провода, которые легко перепутать (Trig/Echo, SDA/SCL).
    Прогон 14.11: ИИ читает подписи гнёзд со сдвигом на одно (Trig 10, Echo 11 вместо 9 и 10),
    но порядок проводов видит верно. Поэтому сравниваем порядок, а не точные номера."""
    items = {it["key"]: it for it in cfg["items"]}
    a_item = raw.get(first) if isinstance(raw.get(first), dict) else {}
    b_item = raw.get(second) if isinstance(raw.get(second), dict) else {}
    a, b = pin_label(a_item.get("value")), pin_label(b_item.get("value"))
    exp_a, exp_b = sorted(items[first]["expected"])[0], sorted(items[second]["expected"])[0]
    if not (a and b and text_of(a_item) and text_of(b_item)) or a == b \
            or a.startswith("A") != b.startswith("A"):
        c.add("unclear", title, f"{title}: проследить оба провода не получилось, проверь сам ({items[first]['label']} — "
              f"{exp_a}, {items[second]['label']} — {exp_b})")
        return
    if (pin_order(a) < pin_order(b)) == (pin_order(exp_a) < pin_order(exp_b)):
        c.add("ok", title, f"{title}: провода стоят в правильном порядке. " + text_of(a_item), a_item)
    else:
        c.add("error", title, f"{title} перепутаны местами: {items[first]['label']} должен идти в {exp_a}, "
              f"{items[second]['label']} — в {exp_b}. " + text_of(a_item) + " " + text_of(b_item), a_item, "trace")


def check_pins(c, raw, module):
    """Сверяет занятые гнёзда Arduino со схемой всей платы."""
    cfg = MODULES[module]
    plate = PLATES[cfg["plate"]]
    item = raw.get("pins")
    item = item if isinstance(item, dict) else {}
    digital, analog = pin_list(item.get("digital")), pin_list(item.get("analog"))
    if not text_of(item) or (digital is None and analog is None):
        c.add("unclear", "Пины", "Пины Arduino: подписи гнёзд по фото прочитать не получилось, проверь сам")
        return

    # гнёзда A4/A5 могут оказаться в любом из списков (SDA/SCL), поэтому сверяем каждую колодку отдельно
    seen_digital = set(p for p in (digital or []) if not p.startswith("A"))
    seen_analog = set(p for p in (analog or []) + (digital or []) if p.startswith("A"))
    extra, missing = [], []
    if digital is not None:
        extra += sorted(seen_digital - plate["digital"], key=int)
        missing += sorted((cfg["pins"] & plate["digital"]) - seen_digital, key=int)
    if analog is not None:
        extra += sorted(seen_analog - plate["analog"])
        missing += sorted((cfg["pins"] & plate["analog"]) - seen_analog)

    # Правило против ложных тревог (проверено на фото под углом 14.11):
    # - больше 2 «лишних» гнёзд — значит, ИИ не прочитал подписи, а перечислил их подряд;
    # - ошибка только когда одно гнездо модуля пустое И рядом занято лишнее:
    #   так выглядит провод, переставленный в соседний пин.
    if len(extra) > 2:
        c.add("unclear", "Пины", "Пины Arduino: подписи гнёзд по фото прочитать надёжно не получилось, проверь сам")
    elif extra and missing:
        c.add("error", "Пины", f"Пины Arduino: гнездо {', '.join(missing)} пустое, а провод есть в гнезде {', '.join(extra)}. "
              "Похоже, провод переставлен не в то гнездо. " + text_of(item), item, "pin")
    elif extra or missing:
        what = (f"в гнезде {', '.join(extra)} есть провод, по схеме оно свободно" if extra
                else f"гнездо {', '.join(missing)} по фото выглядит пустым")
        c.add("unclear", "Пины", f"Пины Arduino: {what}. Проверь это место сам")
    else:
        shown = sorted(seen_digital, key=int) + sorted(seen_analog)
        c.add("ok", "Пины", "Пины Arduino: провода стоят в гнёздах " + ", ".join(shown) + ", как по схеме.", item)
        if digital is None or analog is None:
            c.add("unclear", "Пины", "Пины Arduino: одну из колодок по фото не видно, проверь её сам")


def check_ground(c, raw):
    gp = raw.get("gnd_pin") if isinstance(raw.get("gnd_pin"), dict) else {}
    pw = raw.get("power_wires")
    if isinstance(pw, list) and not gp:
        # новый формат: список занятых гнёзд питания -> переводим в старый gnd_pin
        gnd = [w for w in pw if isinstance(w, dict) and "GND" in str(w.get("socket", "")).upper()]
        listed = ", ".join(f"{w.get('socket')} ({w.get('color', '')})" for w in pw if isinstance(w, dict))
        if gnd:
            gp = {"status": "yes", "wire_color": gnd[0].get("color", ""),
                  "evidence": "В гнезде GND есть провод (" + (gnd[0].get("color") or "цвет не указан") + ")."}
        else:
            gp = {"status": "no", "evidence": "Ни в одном гнезде GND нет провода. Заняты гнёзда: " + (listed or "никакие") + "."}
    ge = raw.get("gnd_other_end") if isinstance(raw.get("gnd_other_end"), dict) else {}
    if gp.get("status") == "no" and text_of(gp):
        c.add("error", "GND", "Провод в гнездо GND на Arduino не воткнут: " + text_of(gp), gp, "gnd")
    elif gp.get("status") == "yes" and ge.get("status") == "hanging" and text_of(ge):
        color = gp.get("wire_color") or "провод"
        c.add("error", "Земля висит", f"Земля никуда не доходит ({color}): " + text_of(ge),
              ge if valid_box(ge.get("box")) else gp, "hanging")
    elif gp.get("status") == "yes" and ge.get("status") == "rail" and text_of(gp) and text_of(ge):
        c.add("ok", "GND", "Земля: " + text_of(gp) + " " + text_of(ge), gp)
    else:
        c.add("unclear", "GND", "Земля (GND): по фото подтвердить не получилось, проверь сам")

    # Висящие провода (кроме уже описанного провода земли)
    gnd_color = (gp.get("wire_color") or "").lower()
    wires = raw.get("hanging_wires") if isinstance(raw.get("hanging_wires"), list) else []
    for w in wires:
        if not isinstance(w, dict):
            continue
        color = (w.get("color") or "").strip()
        ev = (w.get("evidence") or "").strip()
        if not ev:
            continue
        if gnd_color and color.lower() == gnd_color and any("Земля никуда не доходит" in e for e in c.errors):
            continue
        c.add("error", "Висит провод", f"Провод ({color or 'без цвета'}) возможно висит в воздухе: {ev}", w, "hanging")


def build_module_result(raw, module):
    """Итог проверки считает код: подтверждаем только то, что ИИ описал с evidence."""
    if not isinstance(raw, dict):
        raise ValueError("ответ не JSON-объект")
    if raw.get("no_circuit"):
        return dict(NO_CIRCUIT)
    cfg = MODULES[module]
    c = Collector()
    paired = {k for pair in cfg.get("pairs", []) for k in pair[:2]}
    for it in cfg["items"]:
        if it["tag"] not in CHECK_OFF and it["key"] not in paired:
            check_item(c, it, raw)
    if "trace" not in CHECK_OFF:
        for first, second, title in cfg.get("pairs", []):
            check_pair(c, cfg, raw, first, second, title)
    if "pin" not in CHECK_OFF:
        check_pins(c, raw, module)
    check_ground(c, raw)
    return finish(c, cfg["manual"], cfg["ok"])


def parse_json(text):
    """Достаёт JSON из ответа, даже если модель обернула его в ```json ... ```."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def cache_key(data, module):
    return hashlib.sha256(data).hexdigest() + f":{module}:{CHECK_VERSION}"


# ================== Демо-кэш для защиты ==================
# demo_cache.json делает скрипт make_demo.py из результатов прогона eval_photos.py.
# Он лежит в GitHub вместе с кодом, поэтому есть и на Render. Фото из этого файла
# проверяются мгновенно, даже если Google не отвечает. Из кэша ничего не удаляется.
DEMO_FILE = BASE_DIR / "demo_cache.json"


def load_demo():
    try:
        data = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
        print(f"Демо-кэш: сохранённых проверок — {len(data)}")
        return data
    except Exception:
        return {}


DEMO_CACHE = load_demo()


async def ask_check(data, media_type, module):
    """Один запрос к ИИ по фото. Возвращает (сырой JSON, модель, секунды) или (None, None, секунды)."""
    begin = time.time()
    if compare_on(module):
        contents = ["ФОТО 1 — ЭТАЛОН (правильная сборка):",
                    types.Part.from_bytes(data=etalon_image(module), mime_type="image/jpeg"),
                    "ФОТО 2 — СБОРКА УЧЕНИКА (проверяй её):",
                    types.Part.from_bytes(data=data, mime_type=media_type),
                    "Сравни ФОТО 2 с эталоном и ответь на вопросы про ФОТО 2."]
    else:
        contents = [types.Part.from_bytes(data=data, mime_type=media_type), "Ответь на вопросы по этому фото."]
    response, model = await ask_gemini(contents, make_config(module_system(module), as_json=True))
    seconds = round(time.time() - begin, 1)
    if response is None:
        return None, None, seconds
    return parse_json(response.text), model, seconds


async def run_check(data, media_type, module, use_cache=True):
    """Проверяет одно фото. Возвращает (результат, код ответа)."""
    key = cache_key(data, module)
    if use_cache and key in DEMO_CACHE:
        print("Фото из демо-кэша, отдаю сохранённый результат")
        result = dict(DEMO_CACHE[key])
        result.update({"seconds": 0, "cached": True})
        return result, 200
    if use_cache and key in CHECK_CACHE:
        print("Это фото уже проверяли, отдаю сохранённый результат")
        CHECK_CACHE.move_to_end(key)
        result = dict(CHECK_CACHE[key])
        result.update({"seconds": 0, "cached": True})
        return result, 200

    try:
        raw, model, seconds = await ask_check(data, media_type, module)
    except Exception as error:
        print("Не удалось разобрать ответ:", error)
        return {"status": "bad_answer", "seconds": 0,
                "message": "Не получилось разобрать ответ. Нажми «Повторить»."}, 502

    if raw is None:
        log_check({"time": datetime.now().isoformat(timespec="seconds"), "module": module,
                   "status": "api_error", "seconds": seconds})
        return {"status": "api_error", "seconds": seconds,
                "message": "ИИ сейчас не ответил. Нажми «Повторить» — обычно со второго раза всё работает."}, 502

    try:
        print("Ответ модели:", json.dumps(raw, ensure_ascii=False))
        result = build_module_result(raw, module)
    except Exception as error:
        print("Не удалось разобрать ответ:", error)
        return {"status": "bad_answer", "seconds": seconds,
                "message": "Не получилось разобрать ответ. Нажми «Повторить»."}, 502

    CHECK_CACHE[key] = result
    while len(CHECK_CACHE) > CACHE_SIZE:
        CHECK_CACHE.popitem(last=False)
    save_cache()
    log_check({"time": datetime.now().isoformat(timespec="seconds"), "module": module,
               "status": result["status"], "errors": len(result["errors"]),
               "error_tags": result["error_tags"], "seconds": seconds, "model": model})

    answer = dict(result)
    answer.update({"seconds": seconds, "cached": False, "model": model})
    return answer, 200


@app.get("/")
def home():
    # Этот адрес используется как «будильник»: сайт стучится сюда при открытии страницы
    return {"status": "Circuit AI сервер работает"}


@app.get("/health")
def health():
    # Быстрая проверка перед показом: открой в браузере адрес_сервера/health
    return {"status": "ok", "models": MODELS, "chat_models": CHAT_MODELS, "saved_results": len(CHECK_CACHE),
            "demo_results": len(DEMO_CACHE), "check_ready": sorted(CHECK_READY), "check_off": sorted(CHECK_OFF),
            "check_version": CHECK_VERSION, "compare": COMPARE, "key_loaded": bool(os.getenv("GEMINI_API_KEY")), "tts": TTS_READY,
            "chat_mode": CHAT_MODE}


@app.post("/check")
async def check(photo: UploadFile = File(...), module: int = Form(1)):
    if module not in CHECK_READY:
        return JSONResponse(status_code=501, content={
            "status": "not_ready", "message": "Проверка по фото для этого модуля пока не готова."})

    data = await photo.read()
    media_type = photo.content_type or "image/jpeg"
    if not media_type.startswith("image/"):
        return JSONResponse(status_code=400, content={
            "status": "bad_file", "message": "Нужна фотография (картинка)."})
    if len(data) > MAX_PHOTO_BYTES:
        return JSONResponse(status_code=413, content={
            "status": "too_big", "message": "Фото слишком большое. Попробуй сделать его заново."})

    result, code = await run_check(data, media_type, module)
    return JSONResponse(status_code=code, content=result)


# ================== Запасной ответ чата без ИИ ==================
# Если Google не ответил, помощник всё равно отвечает: по результату дефектоскопа
# и по заготовленным ответам на готовые вопросы модуля.

ERROR_TIPS = [
    (("пины", "гнезд"), "Пины: сравни, в какие гнёзда Arduino воткнуты провода, со схемой модуля. Скорее всего, один провод стоит в соседнем гнезде: переставь его."),
    (("trig", "echo"), "Trig должен идти в пин 9, Echo в пин 10. Если они перепутаны, датчик всё время показывает 999."),
    (("сервопривод",), "Сервопривод: оранжевый (сигнальный) провод должен приходить в пин 3, коричневый к минусу, красный к плюсу."),
    (("dht",), "DHT11: сигнальная ножка DATA идёт в пин 2, VCC к 5V, GND к GND."),
    (("sda", "scl", "экран"), "Экран: SDA идёт в A4, SCL в A5. Если их поменять местами, экран не найдётся."),
    (("ao ", "звуков"), "Звуковой датчик: контакт AO идёт в A0, плюс к 5V, G к GND."),
    (("rgb",), "RGB-модуль: R к пину 9, G к пину 10, B к пину 11, общий контакт к GND."),
    (("ик-диод",), "ИК-диод: одна ножка в ряду с проводом A1, другая к GND."),
    (("луч", "излучател"), "Луч: светодиод-излучатель должен смотреть головкой прямо на фоторезистор с 2–4 см."),
    (("полярн",), "Светодиод: длинная ножка к пину Arduino, короткая через резистор к GND. Переверни его."),
    (("земля", "gnd"), "Земля (GND): проверь, что провод из пина GND на Arduino воткнут до конца и второй конец стоит в той же половине синей линии или в том же ряду, что и минусы деталей. Без земли ток не возвращается в Arduino, и ничего не работает."),
    (("резистор",), "Резистор: у каждого светодиода должен быть свой резистор, стоящий последовательно с ним. Посмотри, все ли резисторы на месте и не выскочили ли ножки из платы."),
    (("висит",), "Висящий провод: найди провод, у которого конец не воткнут в плату, и вставь его в нужный ряд. Иногда провод кажется воткнутым, но держится только краем."),
    (("светодиод",), "Светодиоды: проверь, что все на месте и стоят правильной стороной. Длинная ножка (плюс) идёт к пину Arduino, короткая к GND."),
    (("кнопк",), "Кнопка: она должна стоять поперёк канавки посередине платы, а провода идут к ножкам по диагонали."),
    (("фоторезистор",), "Фоторезистор: одна ножка идёт к A0, другая к GND. Проверь, что обе ножки стоят в разных рядах."),
    (("датчик", "hc-sr04"), "Датчик HC-SR04: VCC к 5V, Trig к пину 9, Echo к пину 10, GND к GND. Датчик должен стоять прямо, «глазами» вперёд."),
    (("пищалк", "зуммер"), "Зуммер: плюс (длинная ножка) к пину 8, вторая ножка к GND."),
]

# Старые заготовленные ответы для 4 прежних модулей убраны: теперь ответы берутся из modules_qa.json.


def fallback_reply(req, with_note=True):
    msg = (req.message or "").lower()
    note = ("\n\n(Сейчас ИИ-помощник не ответил, поэтому отвечаю заготовленной подсказкой. Спроси чуть позже, и я отвечу подробнее.)"
            if with_note else "")

    if req.defect_result and any(w in msg for w in ("результат", "ошибк", "исправ", "что не так")):
        res = req.defect_result
        errors = res.get("errors") or []
        if not errors:
            unclear = res.get("unclear") or []
            text = "Ошибок дефектоскоп не нашёл."
            if unclear:
                text += " Но часть схемы по фото не видно: " + "; ".join(unclear[:3]) + "."
            text += " Пройди по списку «Проверь сам» и загрузи программу."
            return text + note
        lines = ["Дефектоскоп нашёл возможные ошибки. Начни с первой:"]
        for i, e in enumerate(errors[:4], 1):
            low = e.lower()
            tip = next((t for keys, t in ERROR_TIPS if any(k in low for k in keys)), "Проверь это место на схеме и сравни с шагами сборки.")
            lines.append(f"{i}. {e}\nЧто сделать: {tip}")
        lines.append("Когда исправишь, сфотографируй схему ещё раз и нажми «Проверить схему».")
        return "\n\n".join(lines) + note

    exact = qa_exact(req.module, req.message)
    if exact:
        return exact + note
    closest = qa_closest(req.module, req.message)
    if closest:
        return "Похоже, твой вопрос связан с этим. " + closest + note

    if "результат" in msg:
        return "Сначала сфотографируй схему и нажми «Проверить схему». После проверки я объясню, что нашёл дефектоскоп." + note

    return ("Сейчас ИИ-помощник не ответил на этот вопрос. "
            "Попробуй готовые вопросы под чатом: на них я отвечу сразу. Или спроси ещё раз через минуту.")


GENERAL_FAQ = {
    "чем ты можешь помочь": "Я твой тьютор по Arduino и электронике. Могу объяснить, как работает схема или программа, разобрать ошибку, которую нашёл дефектоскоп, и подсказать, что проверить, если что-то не работает. Спрашивай голосом или текстом.",
    "как пользоваться дефектоскопом": "Открой раздел «Дефектоскоп», выбери модуль и включи камеру или загрузи фото. Снимай сверху, чтобы были видны Arduino и вся макетная плата. Нажми «Проверить схему»: ошибки появятся в красных рамках на снимке, а я объясню, как их исправить.",
    "что такое arduino": "Arduino — это маленькая плата с микроконтроллером, то есть крошечным компьютером. В неё загружают программу, и она управляет светодиодами, моторами, пищалками и читает датчики. Пины — это контакты, через которые Arduino подаёт напряжение или считывает сигнал.",
    "зачем нужен резистор": "Резистор ограничивает ток. Без него через светодиод пойдёт слишком большой ток, и он может сгореть. Неважно, с какой стороны светодиода стоит резистор: в одной цепочке ток везде одинаковый.",
}


# Заготовленные ответы (база знаний) одинаковые для всех, поэтому добавляем начало и конец
# в стиле выбранного тьютора — чтобы у каждого была своя манера и без ИИ.
TUTOR_FRAMES = {
    "dex": (["Йоу, бро! ", "Опа, смотри. ", "Короче, бро, ", "Го разберёмся. "],
            ["Изи, го дальше!", "Чекни и пиши, если что.", "Всё, бро, ты справишься.", "Имба, погнали дальше!"]),
    "lumi": (["Приветик! ", "Ой, хороший вопросик! ", "Ура, давай разберёмся! ", "Смотри, как всё просто! "],
             ["У тебя всё-всё получится!", "Ты большой молодец!", "Если что, я рядышком!", "Ура, вперёд!"]),
    "om": (["Уху! Любопытный вопрос. ", "Итак. ", "Уху! Заметь: ", "Хороший вопрос. "],
           ["Подумай, почему это работает именно так.", "Любопытно, правда?", "Проверь себя: сможешь объяснить это другу?",
            "Знание приходит к тому, кто проверяет."]),
}
TUTOR_FRAMES["volt"] = TUTOR_FRAMES["dex"]
TUTOR_FRAMES["iskra"] = TUTOR_FRAMES["lumi"]


def in_style(avatar, text):
    if not text:
        return text
    starts, ends = TUTOR_FRAMES.get(avatar, TUTOR_FRAMES["dex"])
    n = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)   # одна и та же фраза — одно и то же начало
    note = ""
    if "\n\n(" in text:          # пометку «ИИ не ответил» оставляем в самом конце
        text, note = text.split("\n\n(", 1)
        note = "\n\n(" + note
    return starts[n % len(starts)] + text.strip() + " " + ends[(n // 7) % len(ends)] + note


def quick_reply(req):
    """Мгновенный ответ из базы знаний на типовые вопросы (кнопки под чатом) — без ожидания ИИ."""
    msg = (req.message or "").lower().strip(" ?!.")
    if len(msg) > 80:
        return None
    if req.defect_result and msg.startswith("что значит мой результат"):
        return fallback_reply(req, with_note=False)
    answer = qa_exact(req.module, req.message)
    if answer:
        return answer
    for key, answer in GENERAL_FAQ.items():
        if key in msg:
            return answer
    return None


@app.post("/chat")
async def chat(req: ChatRequest):
    quick = quick_reply(req)
    if quick and CHAT_MODE == "fast":
        return {"reply": in_style(req.avatar, quick), "quick": True}

    if req.module in QA:
        context = "\n\nМодуль, который сейчас проходит ученик:\n" + qa_context(req.module)
    else:
        names = ", ".join(f"{m['id']} {m['name']}" for m in QA.values())
        context = ("\n\nУченик сейчас не в конкретном модуле. Модули макета Smart City Lab "
                   "(4 зоны города: Транспорт, Энергия, Экология, Безопасность): " + names + ".")

    if req.module in CHECK_READY:
        context += "\n\nДля этого модуля проверка схемы по фото доступна. Как модуль выглядит на фото: " + ETALONS[req.module]
        if req.defect_result:
            short = {k: v for k, v in req.defect_result.items() if k not in ("marks", "model", "seconds", "cached")}
            context += ("\n\nПоследний результат дефектоскопа для этого ученика (JSON):\n"
                        + json.dumps(short, ensure_ascii=False))
        else:
            context += "\n\nУченик ещё не проверял схему дефектоскопом."
        if req.module in UNVERIFIED:
            context += ("\n\nЭталон этого модуля ещё не сверен с собранным железом. Номера пинов бери из программы модуля. "
                        "Если ученик говорит, что собрал так, как написано, а не работает, "
                        "не настаивай, что он ошибся: предложи проверить соединения по одному.")
    elif req.module in QA:
        context += ("\n\nДля этого модуля проверка схемы по фото пока недоступна, не предлагай её. "
                    "Помогай по эталону выше: объясняй, как собрать, как работает программа, и подсказывай, "
                    "что проверить, если схема не работает.")

    if quick:
        context += ("\n\nПроверенный ответ на этот вопрос из базы знаний (опирайся на него, объясни своими словами "
                    "и в своём характере, можно глубже):\n" + quick)

    contents = []
    for m in req.history[-10:]:
        role = "user" if m.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=m.text[:2000])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=req.message[:1000])]))

    style = AVATAR_STYLES.get(req.avatar, AVATAR_STYLES["dex"])
    response, model = await ask_gemini(contents, make_config(CHAT_SYSTEM + "\n\nТвой характер: " + style + context),
                                       models=CHAT_MODELS, attempt_timeout=CHAT_ATTEMPT_TIMEOUT, budget=CHAT_BUDGET)

    if response is None or not response.text:
        if quick:   # ИИ не ответил, но на этот вопрос есть проверенный ответ
            return {"reply": in_style(req.avatar, quick), "quick": True}
        return {"reply": in_style(req.avatar, fallback_reply(req)), "offline": True}
    return {"reply": response.text.strip()}


class TTSRequest(BaseModel):
    tutor: str = "dex"
    text: str


@app.post("/tts")
async def speak(req: TTSRequest):
    """Озвучка ответа голосом тьютора. Возвращает WAV."""
    if not TTS_READY:
        return JSONResponse({"error": "голоса Silero не установлены на этом сервере"}, status_code=503)
    try:
        data = await asyncio.to_thread(tts.synth, req.tutor, req.text[:3000])
    except Exception as error:
        print("Ошибка озвучки:", error)
        return JSONResponse({"error": "не получилось озвучить"}, status_code=500)
    if not data:
        return JSONResponse({"error": "нечего читать"}, status_code=400)
    return Response(content=data, media_type="audio/wav")
