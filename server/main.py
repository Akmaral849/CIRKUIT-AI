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
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()
BASE_DIR = Path(__file__).parent

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30000),  # 30 сек, в миллисекундах
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
# 11.11: модули сменились на 7 новых (Smart City Lab по зонам), старые 4 разобраны.
# Эталоны ниже (ETALONS) — от СТАРЫХ модулей, поэтому проверка выключена,
# пока не будут собраны новые модули и сняты эталонные фото. Тогда номера добавим сюда.
CHECK_READY = set()

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

# Эталоны всех модулей. Чат знает эталон того модуля, который открыт у ученика.
# Эталоны написаны по реально собранным модулям.
ETALONS = {
    1: """Эталон: модуль «Светофор» на Arduino Uno.
Правильная сборка:
- Arduino Uno и макетная плата.
- 3 светодиода: красный, жёлтый, зелёный. Расположение на плате любое.
- У каждого светодиода свой резистор (от 220 Ом до 1 кОм), включённый последовательно с ним (с любой стороны светодиода).
- Длинная ножка светодиода (плюс, анод) идёт к пину Arduino, короткая (минус, катод) к GND.
- Пин GND на Arduino соединён проводом с минусовой шиной или с рядом макетной платы, куда идут минусы светодиодов.
- Красный светодиод подключён к пину 10, жёлтый к пину 9, зелёный к пину 8.
- Цвет проводов не важен.
Программа: зелёный горит 3 секунды, жёлтый 1 секунду, красный 3 секунды, потом всё по кругу (digitalWrite и delay).""",

    2: """Эталон: модуль «Кнопка и светодиод» на Arduino Uno.
Правильная сборка:
- Arduino Uno и макетная плата.
- 1 светодиод и 1 резистор (от 220 Ом до 1 кОм) последовательно. Пин 13 идёт к длинной ножке светодиода, короткая ножка через резистор к GND.
- Кнопка с четырьмя ножками стоит поперёк центральной канавки платы. Одна ножка кнопки соединена с пином 2, ножка по диагонали от неё соединена с GND.
- Внешний резистор для кнопки не нужен: включена встроенная подтяжка INPUT_PULLUP.
- GND можно подключать в боковую шину или прямо в ряды платы. У некоторых плат боковая шина разорвана посередине, тогда половины шины не соединены.
Программа: пин 2 в режиме INPUT_PULLUP (не нажата = HIGH, нажата = LOW). Пока кнопка нажата, светодиод горит, отпустил — гаснет. Маленький светодиод L на Arduino тоже загорается, потому что он подключён к пину 13.""",

    3: """Эталон: модуль «Ночник на фоторезисторе» на Arduino Uno.
Правильная сборка (основной вариант):
- Arduino Uno и макетная плата.
- Фоторезистор одной ножкой соединён с пином A0, другой с GND. Отдельный резистор для фоторезистора не нужен: включена встроенная подтяжка INPUT_PULLUP.
- 1 светодиод с резистором (от 220 Ом до 1 кОм): пин 9 к длинной ножке, короткая ножка через резистор к GND.
Также правильный вариант: делитель напряжения из фоторезистора (к 5V) и резистора 10 кОм (к GND), провод A0 в их общем ряду. С резистором 1 кОм вместо 10 кОм числа получаются слишком маленькими, и ночник работает плохо.
Программа: при включении светодиод горит 1 секунду (самопроверка), затем Arduino 2 секунды запоминает свет в комнате и сам считает пороги. Со встроенной подтяжкой: чем темнее, тем больше число analogRead(A0). Два порога, чтобы не мигал: включается, когда стало заметно темнее, выключается, только когда снова стало светлее. Числа видно в Мониторе порта (9600).""",

    4: """Эталон: модуль «Парктроник» на Arduino Uno.
Правильная сборка:
- Arduino Uno, макетная плата, датчик расстояния HC-SR04 и пищалка (зуммер).
- Датчик стоит прямо, «глазами» вперёд: VCC к 5V, Trig к пину 9, Echo к пину 10, GND к GND.
- Пищалка: ножка со знаком + (длинная) к пину 8, вторая ножка к GND. Программа использует tone(), поэтому подходит и активная, и пассивная пищалка.
Программа: импульс на Trig запускает измерение, pulseIn измеряет время эха на Echo, расстояние в сантиметрах = время в микросекундах / 58. Замер каждые 60 мс без остановки (millis). Дальше 40 см тишина, от 40 до 10 см пищит тем чаще, чем ближе, ближе 10 см пищит непрерывно. Если эха нет 3 раза подряд, расстояние 999 (впереди пусто). Датчик меряет расстояние до ближайшего предмета, мягкие и наклонные поверхности он видит хуже.""",
}

# Что по фото проверить нельзя надёжно, остаётся ученику
MANUAL = [
    "Красный светодиод подключён к пину 10, жёлтый к пину 9, зелёный к пину 8",
    "Каждый светодиод стоит правильной стороной: длинная ножка к пину Arduino, короткая к GND (по фото это не видно)",
    "Минусы светодиодов (через резисторы) доходят до GND, а провод GND воткнут до конца",
    "Выводы резисторов не касаются друг друга",
]

# Правило про рамки: по ним сайт рисует на фото, где деталь или ошибка
BOX_RULE = ("- В каждом пункте добавь box: рамку вокруг этой детали или провода на фото в виде "
            "[ymin, xmin, ymax, xmax], числа от 0 до 1000 (доля высоты и ширины фото). "
            "Если пункт про несколько деталей, обведи их все одной рамкой. Если не видно или не уверен, ставь null.")

SYSTEM = """Ты проверяющий на учебной платформе Circuit AI. Ты смотришь на фото схемы «Светофор» на Arduino Uno и макетной плате и отвечаешь на конкретные вопросы.

Строгие правила:
- Описывай только то, что реально видишь. Если не видно, ставь "cannot_see". Не достраивай «как обычно бывает».
- В каждом evidence коротко объясни, что именно видишь и где (по цвету провода, по положению).
- Провод считается висящим, если один его конец явно не воткнут и торчит в воздухе или лежит на столе. Если конец провода просто уходит за край кадра, это не «висит», а "cannot_see".
- Номера пинов не называй.
""" + BOX_RULE + """

Вопросы:
1. leds: есть ли на макетной плате три светодиода: красный, жёлтый, зелёный? status: yes / no / cannot_see.
2. resistor_count: сколько резисторов (маленькие цилиндры с цветными полосками) на макетной плате? value: число или null, если не можешь сосчитать.
3. gnd_pin: воткнут ли какой-нибудь провод в пин с подписью GND на плате Arduino? status: yes / no / cannot_see. wire_color: цвет провода или "".
4. gnd_other_end: куда воткнут второй конец этого провода? status: rail (в отверстие макетной платы: в боковую шину или в ряд) / hanging (висит в воздухе, никуда не воткнут) / cannot_see.
5. hanging_wires: список проводов, у которых явно висит конец в воздухе, как массив объектов {"color": "...", "evidence": "...", "box": [...]}. Пустой массив, если таких нет или не видно.

Если на фото нет электронной схемы, верни {"no_circuit": true}.

Верни ТОЛЬКО JSON:
{"no_circuit": false,
 "leds": {"status": "...", "evidence": "...", "box": [ymin, xmin, ymax, xmax]},
 "resistor_count": {"value": 3, "evidence": "...", "box": [ymin, xmin, ymax, xmax]},
 "gnd_pin": {"status": "...", "wire_color": "...", "evidence": "...", "box": [ymin, xmin, ymax, xmax]},
 "gnd_other_end": {"status": "...", "evidence": "...", "box": [ymin, xmin, ymax, xmax]},
 "hanging_wires": [{"color": "...", "evidence": "...", "box": [ymin, xmin, ymax, xmax]}]}"""

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
- Ответ могут озвучивать голосом, поэтому пиши короткими предложениями, без списков со звёздочками и без длинных формул."""


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
    "dex": ("Тебя зовут Декс, ты робот-подросток, «свой парень». Говори на ты, коротко, уверенно, с лёгким современным сленгом "
            "(«изи», «го чекнем», «косяк»), но без мата, грубости и оскорблений. Ошибку называй прямо, но всегда доводи до решения."),
    "lumi": ("Тебя зовут Люми, ты добрая девочка-лампочка. Говори мягко и тепло, подбадривай, никогда не ругай за ошибки, "
             "хвали за каждый шаг и объясняй спокойно и понятно. Без смайликов."),
    "om": ("Тебя зовут Ом, ты мудрый совёнок-профессор. Сначала задай один наводящий вопрос, чтобы ученик догадался сам. "
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


def text_of(item, key="evidence"):
    return ((item or {}).get(key) or "").strip()


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


class Collector:
    """Собирает итог проверки и рамки для подсветки на фото."""

    def __init__(self):
        self.found, self.errors, self.unclear, self.marks = [], [], [], []

    def add(self, kind, label, text, item=None):
        {"ok": self.found, "error": self.errors, "unclear": self.unclear}[kind].append(text)
        box = valid_box((item or {}).get("box"))
        if box and kind != "unclear":
            self.marks.append({"kind": kind, "label": label, "box": box})


NO_CIRCUIT = {"status": "no_circuit", "found": [], "missing": [], "errors": [],
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
    return {"status": status, "found": c.found, "missing": [], "errors": c.errors,
            "unclear": c.unclear, "manual": manual, "marks": c.marks, "message": message}


def check_ground(c, raw, ok_ends):
    gp = raw.get("gnd_pin") or {}
    ge = raw.get("gnd_other_end") or {}
    if gp.get("status") == "no" and text_of(gp):
        c.add("error", "GND", "Провод в пин GND на Arduino не воткнут: " + text_of(gp), gp)
    elif gp.get("status") == "yes" and ge.get("status") == "hanging" and text_of(ge):
        color = gp.get("wire_color") or "провод"
        c.add("error", "Земля висит", f"Земля никуда не доходит ({color}): " + text_of(ge),
              ge if valid_box(ge.get("box")) else gp)
    elif gp.get("status") == "yes" and ge.get("status") in ok_ends and text_of(gp) and text_of(ge):
        c.add("ok", "GND", "Земля: " + text_of(gp) + " " + text_of(ge), gp)
    else:
        c.add("unclear", "GND", "Земля (GND): по фото подтвердить не получилось, проверь сам")

    # Висящие провода (кроме уже описанного провода земли)
    gnd_color = (gp.get("wire_color") or "").lower()
    for w in raw.get("hanging_wires") or []:
        color = (w.get("color") or "").strip()
        ev = (w.get("evidence") or "").strip()
        if not ev:
            continue
        if gnd_color and color.lower() == gnd_color and any("Земля никуда не доходит" in e for e in c.errors):
            continue
        c.add("error", "Висит провод", f"Провод ({color or 'без цвета'}) возможно висит в воздухе: {ev}", w)


def build_result(raw):
    """Модуль 1. Итог считает код: подтверждаем только то, что модель описала."""
    if raw.get("no_circuit"):
        return dict(NO_CIRCUIT)
    c = Collector()

    leds = raw.get("leds") or {}
    if leds.get("status") == "yes" and text_of(leds):
        c.add("ok", "Светодиоды", "Три светодиода: " + text_of(leds), leds)
    elif leds.get("status") == "no" and text_of(leds):
        c.add("error", "Светодиоды", "Светодиоды: " + text_of(leds), leds)
    else:
        c.add("unclear", "Светодиоды", "Светодиоды: по фото подтвердить не получилось")

    res = raw.get("resistor_count") or {}
    value = res.get("value")
    if isinstance(value, int) and not isinstance(value, bool) and text_of(res):
        if value == 3:
            c.add("ok", "Резисторы", "Три резистора: " + text_of(res), res)
        elif 0 <= value < 3:
            c.add("error", "Резисторы", f"Резисторов видно {value} вместо трёх: " + text_of(res), res)
        else:
            c.add("unclear", "Резисторы", f"Резисторы: насчитано {value}, проверь сам")
    else:
        c.add("unclear", "Резисторы", "Резисторы: сосчитать по фото не получилось")

    check_ground(c, raw, {"rail"})
    return finish(c, MANUAL,
                  "Детали и земля выглядят правильно. Проверь пины по списку ниже и загрузи программу: светофор должен переключаться.")


# ================== Дефектоскоп для модулей 2-4 ==================
# Для модулей 2-4 у каждого свой список узких вопросов. Итог считает код ниже.
# Номера пинов модель не проверяет, они в списке «Проверь сам».

COMMON_RULES = """Строгие правила:
- Описывай только то, что реально видишь. Если не видно, ставь "cannot_see". Не достраивай «как обычно бывает».
- В каждом evidence коротко объясни, что именно видишь и где (по цвету провода, по положению).
- Провод считается висящим, если один его конец явно не воткнут и торчит в воздухе или лежит на столе. Если конец провода просто уходит за край кадра, это не «висит», а "cannot_see".
- Номера пинов не называй.
""" + BOX_RULE

GENERIC = {
    2: {
        "title": "Кнопка и светодиод",
        "items": [
            {"key": "led_count", "kind": "count", "expected": 1, "label": "Светодиод",
             "q": "сколько светодиодов на макетной плате? value: число или null."},
            {"key": "resistor_count", "kind": "count", "expected": 1, "label": "Резистор",
             "q": "сколько резисторов (маленькие цилиндры с цветными полосками) на макетной плате? value: число или null."},
            {"key": "button", "kind": "yesno", "label": "Кнопка",
             "q": "есть ли на макетной плате кнопка (маленькая квадратная кнопка с четырьмя ножками)? status: yes / no / cannot_see."},
            {"key": "button_across", "kind": "yesno", "label": "Кнопка через канавку",
             "q": "стоит ли кнопка поперёк центральной канавки макетной платы (две ножки по одну сторону канавки, две по другую)? status: yes / no / cannot_see."},
        ],
        "gnd_end": "rail",
        "manual": [
            "Провод от кнопки идёт в пин 2, провод к светодиоду в пин 13",
            "Вторая ножка кнопки (по диагонали) соединена с GND",
            "Светодиод стоит правильной стороной: длинная ножка к пину 13, короткая через резистор к GND",
            "Если GND идёт через боковую шину: шина не разорвана посередине между проводом GND и деталями",
        ],
        "ok": "Детали и земля выглядят правильно. Проверь пины по списку ниже, загрузи программу и нажми кнопку: светодиод должен включаться и выключаться.",
    },
    3: {
        "title": "Ночник на фоторезисторе",
        "items": [
            {"key": "photoresistor", "kind": "yesno", "label": "Фоторезистор",
             "q": "есть ли на макетной плате фоторезистор (маленькая круглая деталь с плоской головкой и рисунком-змейкой сверху, две ножки)? status: yes / no / cannot_see."},
            {"key": "led_count", "kind": "count", "expected": 1, "label": "Светодиод",
             "q": "сколько светодиодов на макетной плате? value: число или null."},
            # Два правильных варианта: с резистором 10 кОм (2 резистора) или без него,
            # со встроенной подтяжкой INPUT_PULLUP (1 резистор, только у светодиода)
            {"key": "resistor_count", "kind": "count", "expected": 1, "allowed": [1, 2], "label": "Резисторы",
             "q": "сколько обычных резисторов (маленькие цилиндры с цветными полосками) на макетной плате? Фоторезистор не считай. value: число или null."},
        ],
        "gnd_end": "rail",
        "manual": [
            "Фоторезистор подключён к пину A0 (одна ножка) и к GND (другая ножка)",
            "Если в схеме есть резистор 10 кОм, он стоит в ряду с A0 и вторым концом идёт к GND",
            "Если резистора 10 кОм нет, в программе должен быть pinMode(A0, INPUT_PULLUP)",
            "Светодиод подключён к пину 9 длинной ножкой, короткая через резистор к GND",
        ],
        "ok": "Детали и земля выглядят правильно. Проверь соединения по списку ниже, загрузи программу и закрой фоторезистор ладонью: светодиод должен включиться.",
    },
    4: {
        "title": "Парктроник",
        "items": [
            {"key": "sensor", "kind": "yesno", "label": "Датчик расстояния HC-SR04",
             "q": "есть ли на фото датчик расстояния HC-SR04 (плата с двумя круглыми серебристыми «глазами»)? status: yes / no / cannot_see."},
            {"key": "buzzer", "kind": "yesno", "label": "Пищалка",
             "q": "есть ли на фото пищалка (маленький чёрный цилиндр)? status: yes / no / cannot_see."},
            {"key": "sensor_wires", "kind": "count", "expected": 4, "label": "Провода датчика",
             "q": "к скольким из четырёх ножек датчика HC-SR04 подходят провода или к скольким ножкам есть соединение через ряды макетной платы? value: число или null."},
        ],
        "gnd_end": "rail_or_part",
        "manual": [
            "Ножка VCC датчика соединена с 5V, ножка GND с GND",
            "Trig идёт в пин 9, Echo в пин 10, и они не перепутаны (если расстояние всегда 999, поменяй их местами)",
            "Плюс пищалки идёт в пин 8, вторая ножка к GND",
            "Датчик стоит прямо, и перед «глазами» нет проводов",
        ],
        "ok": "Детали и земля выглядят правильно. Проверь соединения по списку ниже, загрузи программу и поднеси ладонь к датчику: пищалка должна пищать чаще.",
    },
}


def generic_system(cfg):
    lines = []
    for i, it in enumerate(cfg["items"], 1):
        lines.append(f"{i}. {it['key']}: {it['q']}")
    n = len(lines)
    if cfg["gnd_end"] == "rail_or_part":
        end_q = ("status: rail (в отверстие макетной платы) / part (прямо в ножку детали, например датчика) / "
                 "hanging (висит в воздухе, никуда не воткнут) / cannot_see.")
    else:
        end_q = "status: rail (в отверстие макетной платы: в боковую шину или в ряд) / hanging (висит в воздухе, никуда не воткнут) / cannot_see."
    lines.append(f"{n+1}. gnd_pin: воткнут ли какой-нибудь провод в пин с подписью GND на плате Arduino? status: yes / no / cannot_see. wire_color: цвет провода или \"\".")
    lines.append(f"{n+2}. gnd_other_end: куда воткнут второй конец этого провода? {end_q}")
    lines.append(f"{n+3}. hanging_wires: список проводов, у которых явно висит конец в воздухе, как массив объектов {{\"color\": \"...\", \"evidence\": \"...\", \"box\": [...]}}. Пустой массив, если таких нет или не видно.")

    box = '"box": [ymin, xmin, ymax, xmax]'
    example = ['"no_circuit": false']
    for it in cfg["items"]:
        if it["kind"] == "count":
            example.append(f'"{it["key"]}": {{"value": {it["expected"]}, "evidence": "...", {box}}}')
        else:
            example.append(f'"{it["key"]}": {{"status": "...", "evidence": "...", {box}}}')
    example.append('"gnd_pin": {"status": "...", "wire_color": "...", "evidence": "...", ' + box + '}')
    example.append('"gnd_other_end": {"status": "...", "evidence": "...", ' + box + '}')
    example.append('"hanging_wires": [{"color": "...", "evidence": "...", ' + box + '}]')

    return (f"Ты проверяющий на учебной платформе Circuit AI. Ты смотришь на фото схемы «{cfg['title']}» "
            "на Arduino Uno и макетной плате и отвечаешь на конкретные вопросы.\n\n"
            + COMMON_RULES + "\n\nВопросы:\n" + "\n".join(lines)
            + "\n\nЕсли на фото нет электронной схемы, верни {\"no_circuit\": true}.\n\n"
            "Верни ТОЛЬКО JSON:\n{" + ",\n ".join(example) + "}")


def build_result_generic(raw, cfg):
    """Модули 2-4. Итог считает код: подтверждаем только то, что модель описала с evidence."""
    if raw.get("no_circuit"):
        return dict(NO_CIRCUIT)
    c = Collector()

    for it in cfg["items"]:
        item = raw.get(it["key"]) or {}
        label = it["label"]
        if it["kind"] == "count":
            value = item.get("value")
            exp = it["expected"]
            allowed = it.get("allowed", [exp])
            if isinstance(value, int) and not isinstance(value, bool) and text_of(item):
                if value in allowed:
                    c.add("ok", label, f"{label} ({value}): " + text_of(item), item)
                elif 0 <= value < min(allowed):
                    c.add("error", label, f"{label}: видно {value}, а нужно {exp}. " + text_of(item), item)
                else:
                    c.add("unclear", label, f"{label}: насчитано {value}, проверь сам")
            else:
                c.add("unclear", label, f"{label}: сосчитать по фото не получилось")
        else:
            status = item.get("status")
            if status == "yes" and text_of(item):
                c.add("ok", label, f"{label}: " + text_of(item), item)
            elif status == "no" and text_of(item):
                c.add("error", label, f"{label}: " + text_of(item), item)
            else:
                c.add("unclear", label, f"{label}: по фото подтвердить не получилось")

    ok_ends = {"rail", "part"} if cfg["gnd_end"] == "rail_or_part" else {"rail"}
    check_ground(c, raw, ok_ends)
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


async def run_check(data, media_type, module, use_cache=True):
    """Проверяет одно фото. Возвращает (результат, код ответа).
    Эту же функцию использует run_tests.py для прогона тестовых фото."""
    key = hashlib.sha256(data).hexdigest() + f":{module}"
    if use_cache and key in CHECK_CACHE:
        print("Это фото уже проверяли, отдаю сохранённый результат")
        CHECK_CACHE.move_to_end(key)
        result = dict(CHECK_CACHE[key])
        result.update({"seconds": 0, "cached": True})
        return result, 200

    begin = time.time()
    system_prompt = SYSTEM if module == 1 else generic_system(GENERIC[module])
    response, model = await ask_gemini(
        [types.Part.from_bytes(data=data, mime_type=media_type), "Ответь на вопросы по этому фото."],
        make_config(system_prompt, as_json=True),
    )
    seconds = round(time.time() - begin, 1)

    if response is None:
        log_check({"time": datetime.now().isoformat(timespec="seconds"), "module": module,
                   "status": "api_error", "seconds": seconds})
        return {"status": "api_error", "seconds": seconds,
                "message": "ИИ сейчас не ответил. Нажми «Повторить» — обычно со второго раза всё работает."}, 502

    try:
        raw = parse_json(response.text)
        print("Ответ модели:", json.dumps(raw, ensure_ascii=False))
        result = build_result(raw) if module == 1 else build_result_generic(raw, GENERIC[module])
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
               "seconds": seconds, "model": model})

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
            "key_loaded": bool(os.getenv("GEMINI_API_KEY"))}


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
    (("земля", "gnd"), "Земля (GND): проверь, что провод из пина GND на Arduino воткнут до конца и второй конец стоит в той же половине синей линии или в том же ряду, что и минусы деталей. Без земли ток не возвращается в Arduino, и ничего не работает."),
    (("резистор",), "Резистор: у каждого светодиода должен быть свой резистор, стоящий последовательно с ним. Посмотри, все ли резисторы на месте и не выскочили ли ножки из платы."),
    (("висит",), "Висящий провод: найди провод, у которого конец не воткнут в плату, и вставь его в нужный ряд. Иногда провод кажется воткнутым, но держится только краем."),
    (("светодиод",), "Светодиоды: проверь, что все на месте и стоят правильной стороной. Длинная ножка (плюс) идёт к пину Arduino, короткая к GND."),
    (("кнопк",), "Кнопка: она должна стоять поперёк канавки посередине платы, а провода идут к ножкам по диагонали."),
    (("фоторезистор",), "Фоторезистор: одна ножка идёт к A0, другая к GND. Проверь, что обе ножки стоят в разных рядах."),
    (("датчик", "hc-sr04"), "Датчик HC-SR04: VCC к 5V, Trig к пину 9, Echo к пину 10, GND к GND. Датчик должен стоять прямо, «глазами» вперёд."),
    (("пищалк", "зуммер"), "Пищалка: плюс (длинная ножка) к пину 8, вторая ножка к GND."),
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
    if quick:
        return {"reply": quick, "quick": True}

    if req.module in QA:
        context = "\n\nМодуль, который сейчас проходит ученик:\n" + qa_context(req.module)
    else:
        names = ", ".join(f"{m['id']} {m['name']}" for m in QA.values())
        context = ("\n\nУченик сейчас не в конкретном модуле. Модули макета Smart City Lab "
                   "(4 зоны города: Транспорт, Энергия, Экология, Безопасность): " + names + ".")

    if req.module in CHECK_READY:
        context += "\n\nДля этого модуля проверка схемы по фото доступна."
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

    contents = []
    for m in req.history[-10:]:
        role = "user" if m.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=m.text[:2000])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=req.message[:1000])]))

    style = AVATAR_STYLES.get(req.avatar, AVATAR_STYLES["dex"])
    response, model = await ask_gemini(contents, make_config(CHAT_SYSTEM + "\n\nТвой характер: " + style + context),
                                       models=CHAT_MODELS, attempt_timeout=CHAT_ATTEMPT_TIMEOUT, budget=CHAT_BUDGET)

    if response is None or not response.text:
        return {"reply": fallback_reply(req), "offline": True}
    return {"reply": response.text.strip()}
