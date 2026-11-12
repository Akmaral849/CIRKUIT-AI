// Circuit AI — настройки сервера и данные тьюторов.
// Адрес сервера. Если сайт открыт у тебя на компьютере (Live Server) — локальный сервер,
// если открыт из интернета (GitHub Pages) — сервер на Render.
// Адрес Render впишем после создания сервера (одна строка ниже).
const SERVER_ONLINE = 'https://circuit-ai-server.onrender.com';
const IS_LOCAL = ['127.0.0.1', 'localhost', ''].indexOf(location.hostname) !== -1;
window.CIRCUIT_API = IS_LOCAL ? 'http://127.0.0.1:8000' : SERVER_ONLINE;

// Тьюторы. id передаётся на сервер: там у каждого свой характер ответов (AVATAR_STYLES в main.py).
// img: картинки эмоций в assets/tutors/<id>/.
// voice: pitch (высота, 0.5–2) и rate (скорость, 0.5–2) для озвучки браузером.
// lines: короткие реплики тьютора на результат дефектоскопа.
const TUTORS = [
  {
    id: 'dex',
    name: 'Декс',
    role: 'Свой парень',
    tags: ['Дерзкий', 'Сленг', 'Быстрый'],
    about: 'Робот-подросток в худи и кепке задом наперёд. Говорит на ты и со сленгом, ошибку называет прямо, но без наездов, и всегда доводит до ответа.',
    greet: 'Йо! Я Декс. Кидай схему в дефектоскоп или спрашивай голосом — разрулим.',
    sample: 'Йо, я Декс. Го чекнем твою схему — найдём косяк за пару минут.',
    voice: { pitch: 0.75, rate: 1.1 },
    color: '#7C5CFF',
    bg: 'linear-gradient(135deg, #E9E2FF, #FFD9EC)',
    lines: {
      ok: 'Изи! Схема собрана чётко. Загружай код и смотри, как работает.',
      error: 'Опа, есть косяк — он в красной рамке. Го разберём?',
      unclear: 'Часть схемы не видно. Сними поближе и сверху — и я всё чекну.',
      nocircuit: 'Бро, тут схемы не видно. Наведи камеру прямо на плату.'
    }
  },
  {
    id: 'lumi',
    name: 'Люми',
    role: 'Добрая подруга',
    tags: ['Нежная', 'Поддерживает', 'Терпеливая'],
    about: 'Девочка-лампочка: её сердечко светится ярче, когда у тебя получается. Никогда не ругает, объясняет мягко и подбадривает на каждом шаге.',
    greet: 'Привет! Я Люми. Давай вместе соберём схему — у тебя всё получится!',
    sample: 'Привет, я Люми! Не бойся ошибок — мы разберёмся с ними вместе.',
    voice: { pitch: 1.45, rate: 1.0 },
    color: '#FF8A5C',
    bg: 'linear-gradient(135deg, #FFF0D9, #FFE0EC)',
    lines: {
      ok: 'Ура, всё собрано правильно! Я так тобой горжусь!',
      error: 'Я нашла одну ошибку, но это совсем не страшно. Давай исправим вместе?',
      unclear: 'Мне плохо видно часть схемы. Сфотографируй, пожалуйста, чуть ближе.',
      nocircuit: 'Ой, я не вижу здесь схему. Наведи камеру на плату, хорошо?'
    }
  },
  {
    id: 'om',
    name: 'Ом',
    role: 'Мудрый профессор',
    tags: ['Умный', 'Спокойный', 'Наводящие вопросы'],
    about: 'Совёнок-профессор. Не спешит с готовым ответом: задаёт наводящий вопрос, чтобы ты догадался сам, и объясняет, почему всё работает именно так.',
    greet: 'Здравствуй, я Ом. Давай разберёмся, как устроена твоя схема — и почему.',
    sample: 'Здравствуй, я Ом. Подумай: куда течёт ток, когда цепь замкнута?',
    voice: { pitch: 1.0, rate: 0.88 },
    color: '#2F5BEA',
    bg: 'linear-gradient(135deg, #DCEBFF, #E9E2FF)',
    lines: {
      ok: 'Превосходно. Схема соответствует эталону. Можешь объяснить, почему она работает?',
      error: 'Я заметил ошибку. Подумай: что изменится в цепи из-за этого места?',
      unclear: 'Часть соединений не видна. Сделай снимок сверху и при хорошем свете.',
      nocircuit: 'На снимке я не вижу схемы. Попробуем ещё раз?'
    }
  }
];

const TUTOR_EMOTIONS = ['main', 'wave', 'think', 'talk', 'happy', 'alert'];

function tutorImg(t, emotion) {
  const e = TUTOR_EMOTIONS.indexOf(emotion) >= 0 ? emotion : 'main';
  return 'assets/tutors/' + t.id + '/' + t.id + '_' + e + '.webp';
}

function getTutor() {
  let id = 'dex';
  try { id = localStorage.getItem('circuitai-tutor') || 'dex'; } catch (e) {}
  return TUTORS.find(function (t) { return t.id === id; }) || TUTORS[0];
}

function setTutor(id) {
  try { localStorage.setItem('circuitai-tutor', id); } catch (e) {}
  window.dispatchEvent(new CustomEvent('tutor-change', { detail: id }));
}

// Озвучка голосом браузера с настройками тьютора
function tutorSpeak(t, text, onStart, onEnd) {
  if (!('speechSynthesis' in window)) { if (onEnd) onEnd(); return; }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'ru-RU';
  const voices = speechSynthesis.getVoices().filter(function (v) { return v.lang && v.lang.toLowerCase().startsWith('ru'); });
  if (voices.length) u.voice = voices[TUTORS.indexOf(t) % voices.length];
  u.pitch = t.voice.pitch;
  u.rate = t.voice.rate;
  u.onstart = function () { if (onStart) onStart(); };
  u.onend = u.onerror = function () { if (onEnd) onEnd(); };
  speechSynthesis.speak(u);
}
if ('speechSynthesis' in window) speechSynthesis.getVoices();
