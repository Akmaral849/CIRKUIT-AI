// Circuit AI — настройки сервера и данные тьюторов.
// Адрес сервера. Если сайт открыт у тебя на компьютере (Live Server) — локальный сервер,
// если открыт из интернета (GitHub Pages) — сервер на Render.
// Адрес Render впишем после создания сервера (одна строка ниже).
const SERVER_ONLINE = 'https://circuit-ai-server.onrender.com';
const IS_LOCAL = ['127.0.0.1', 'localhost', ''].indexOf(location.hostname) !== -1;
window.CIRCUIT_API = IS_LOCAL ? 'http://127.0.0.1:8000' : SERVER_ONLINE;

// Тьюторы. id передаётся на сервер: там у каждого свой характер ответов (AVATAR_STYLES в main.py).
// img: картинки эмоций в assets/tutors/<id>/.
// voice: какой голос браузера искать (gender, prefer — имена по порядку), скорость rate и высота pitch.
// Высоту держим около 1.0: сильный сдвиг делает живой голос «мультяшным».
// lines: короткие реплики тьютора на результат дефектоскопа.
const TUTORS = [
  {
    id: 'dex',
    name: 'Декс',
    role: 'Свой парень',
    tags: ['Дерзкий', 'Сленг', 'Быстрый'],
    about: 'Робот-подросток в худи и кепке задом наперёд. Говорит на ты и со сленгом, ошибку называет прямо, но без наездов, и всегда доводит до ответа.',
    greet: 'Йоу! Я Декс. Кидай схему в дефектоскоп или спрашивай голосом — ща всё разрулим, бро.',
    sample: 'Йоу, бро! Я Декс. Го чекнем твою схемку — найдём косяк за пару минут, изи!',
    voice: { gender: 'male', prefer: ['Dmitry', 'Дмитрий', 'Pavel', 'Павел'], pitch: 1.1, rate: 1.25 },
    color: '#7C5CFF',
    bg: 'linear-gradient(135deg, #E9E2FF, #FFD9EC)',
    lines: {
      ok: 'Йоу, это имба! Схема собрана чётко. Заливай код и кайфуй.',
      error: 'Опа, бро, тут косячок — он в красной рамке. Го пофиксим?',
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
    greet: 'Приветик! Я Люми! Давай вместе соберём схемку — у тебя всё-всё получится!',
    sample: 'Приветик, я Люми! Ой, как здорово, что ты здесь! Не бойся ошибок, мы разберёмся вместе!',
    voice: { gender: 'female', prefer: ['Dariya', 'Дария', 'Svetlana', 'Светлана', 'Google', 'Irina', 'Ирина'], pitch: 1.4, rate: 1.12 },
    color: '#FF8A5C',
    bg: 'linear-gradient(135deg, #FFF0D9, #FFE0EC)',
    lines: {
      ok: 'Ура-ура! Всё собрано правильно! Ты просто звёздочка!',
      error: 'Ой, я нашла маленькую ошибочку. Это совсем не страшно, давай исправим вместе?',
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
    greet: 'Уху! Здравствуй, я Ом. Давай разберёмся, как устроена твоя схема — и почему.',
    sample: 'Уху! Здравствуй, я Ом. Итак, вопрос на размышление: куда течёт ток, когда цепь замкнута?',
    voice: { gender: 'male', prefer: ['Dmitry', 'Дмитрий', 'Pavel', 'Павел'], pitch: 0.85, rate: 0.92 },
    color: '#2F5BEA',
    bg: 'linear-gradient(135deg, #DCEBFF, #E9E2FF)',
    lines: {
      ok: 'Уху! Превосходно. Схема соответствует эталону. Можешь объяснить, почему она работает?',
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

// ===== Озвучка тьюторов =====
// Голос даёт сам браузер (Web Speech API, speechSynthesis). Качество зависит от браузера:
//   Microsoft Edge — нейросетевые голоса «Online (Natural)»: Светлана, Дария (жен.), Дмитрий (муж.). Лучший вариант.
//   Google Chrome — голос «Google русский» (женский).
//   Остальные — голоса Windows (Ирина, Павел), они звучат более механически.
// Код выбирает лучший доступный голос для каждого тьютора.

const FEMALE_NAMES = ['svetlana', 'светлана', 'dariya', 'дария', 'irina', 'ирина', 'google', 'milena', 'милена', 'katya', 'катя'];
const MALE_NAMES = ['dmitry', 'дмитрий', 'pavel', 'павел', 'yuri', 'юрий', 'maxim', 'максим'];
let ruVoices = [];

function loadVoices() {
  if (!('speechSynthesis' in window)) return;
  ruVoices = speechSynthesis.getVoices().filter(function (v) {
    return v.lang && v.lang.toLowerCase().indexOf('ru') === 0;
  });
}

function voiceGender(v) {
  const n = v.name.toLowerCase();
  if (MALE_NAMES.some(function (m) { return n.indexOf(m) >= 0; })) return 'male';
  if (FEMALE_NAMES.some(function (f) { return n.indexOf(f) >= 0; })) return 'female';
  return '';
}

// Оценка голоса: живые нейросетевые голоса выше всего, потом нужный пол, потом порядок из prefer
function voiceScore(v, t) {
  const n = v.name.toLowerCase();
  let score = 0;
  if (n.indexOf('natural') >= 0) score += 100;
  else if (n.indexOf('online') >= 0) score += 60;
  else if (n.indexOf('google') >= 0) score += 40;
  if (voiceGender(v) === t.voice.gender) score += 30;
  const pref = t.voice.prefer || [];
  for (let i = 0; i < pref.length; i++) {
    if (n.indexOf(pref[i].toLowerCase()) >= 0) { score += 20 - i; break; }
  }
  return score;
}

// Свои настройки голоса (выбираются на странице «Тьюторы» и хранятся в этом браузере)
function voiceSettings(t) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('circuitai-voice-' + t.id) || '{}'); } catch (e) {}
  return {
    name: saved.name || '',
    rate: typeof saved.rate === 'number' ? saved.rate : t.voice.rate,
    pitch: typeof saved.pitch === 'number' ? saved.pitch : t.voice.pitch
  };
}

function saveVoiceSettings(t, data) {
  try { localStorage.setItem('circuitai-voice-' + t.id, JSON.stringify(data)); } catch (e) {}
}

function pickVoice(t) {
  if (!ruVoices.length) loadVoices();
  if (!ruVoices.length) return null;
  const wanted = voiceSettings(t).name;
  const exact = wanted && ruVoices.find(function (v) { return v.name === wanted; });
  if (exact) return exact;
  return ruVoices.slice().sort(function (a, b) { return voiceScore(b, t) - voiceScore(a, t); })[0];
}

// Делаем текст удобным для чтения вслух
function speechText(text) {
  return String(text || '')
    .replace(/[*_#`>]/g, ' ')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, ' ')
    .replace(/→|->/g, ', ')
    .replace(/\bGND\b/g, 'земля')
    .replace(/\bLED\b/g, 'светодиод')
    .replace(/(\d+)\s?V\b/g, '$1 вольт')
    .replace(/(\d+)\s?(кОм|kΩ|k)\b/g, '$1 килоом')
    .replace(/(\d+)\s?(Ом|Ω)\b/g, '$1 ом')
    .replace(/\bA([0-5])\b/g, 'А $1')
    .replace(/\s+/g, ' ')
    .trim();
}

// Длинный текст режем на фразы: некоторые браузеры обрывают длинную речь на середине
function splitPhrases(text) {
  const parts = text.match(/[^.!?]+[.!?]*/g) || [text];
  const out = [];
  parts.forEach(function (p) {
    p = p.trim();
    if (!p) return;
    if (out.length && (out[out.length - 1] + ' ' + p).length < 180) out[out.length - 1] += ' ' + p;
    else out.push(p);
  });
  return out;
}

// ===== Голос тьютора с сервера (Silero) =====
// Каждый тьютор всегда говорит своим голосом: сервер (адрес /tts) делает запись, сайт её проигрывает.
// Если на сервере голосов нет (сервер в интернете на Render), говорит голос браузера.
// Если голоса сервера уже звучали, а один раз сервер не ответил — тьютор молчит, а не меняет голос.
let speakAudio = null, speakSeq = 0, serverVoice = null;   // serverVoice: null — ещё не знаем, true/false

function tutorStopSpeech() {
  speakSeq++;
  if (speakAudio) { try { speakAudio.pause(); } catch (e) {} speakAudio = null; }
  if ('speechSynthesis' in window) speechSynthesis.cancel();
}

function browserSpeak(t, text, onStart, onEnd) {
  if (!('speechSynthesis' in window)) { if (onEnd) onEnd(); return; }
  const phrases = splitPhrases(speechText(text));
  if (!phrases.length) { if (onEnd) onEnd(); return; }
  const voice = pickVoice(t);
  const vs = voiceSettings(t);
  let started = false;
  phrases.forEach(function (p, i) {
    const u = new SpeechSynthesisUtterance(p);
    u.lang = 'ru-RU';
    if (voice) u.voice = voice;
    u.pitch = vs.pitch;
    u.rate = vs.rate;
    u.onstart = function () { if (!started) { started = true; if (onStart) onStart(); } };
    if (i === phrases.length - 1) u.onend = function () { if (onEnd) onEnd(); };
    u.onerror = function (e) { if (e.error !== 'interrupted' && e.error !== 'canceled' && onEnd) onEnd(); };
    speechSynthesis.speak(u);
  });
}

function tutorSpeak(t, text, onStart, onEnd) {
  tutorStopSpeech();
  const my = speakSeq;
  const clean = speechText(text);
  if (!clean) { if (onEnd) onEnd(); return; }
  if (serverVoice === false) { browserSpeak(t, text, onStart, onEnd); return; }

  const controller = ('AbortController' in window) ? new AbortController() : null;
  const timer = setTimeout(function () { if (controller) controller.abort(); }, 20000);
  fetch(window.CIRCUIT_API + '/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tutor: t.id, text: clean }),
    signal: controller ? controller.signal : undefined
  }).then(function (r) {
    if (r.status === 503) { serverVoice = false; throw new Error('no-tts'); }
    if (!r.ok) throw new Error('tts ' + r.status);
    return r.blob();
  }).then(function (blob) {
    clearTimeout(timer);
    if (my !== speakSeq) return;          // пока ждали, тьютора уже перебили
    serverVoice = true;
    const audio = new Audio(URL.createObjectURL(blob));
    speakAudio = audio;
    let started = false;
    audio.onplay = function () { if (!started) { started = true; if (onStart) onStart(); } };
    audio.onended = function () { if (speakAudio === audio) speakAudio = null; if (onEnd) onEnd(); };
    audio.onerror = function () { if (onEnd) onEnd(); };
    audio.play().catch(function () { if (onEnd) onEnd(); });
  }).catch(function (e) {
    clearTimeout(timer);
    if (my !== speakSeq) return;
    if (serverVoice === true) { if (onEnd) onEnd(); return; }   // голос не меняем — лучше промолчать
    serverVoice = false;
    browserSpeak(t, text, onStart, onEnd);
  });
}

// Какой голос выбран для каждого тьютора (видно в консоли браузера: F12 → Console)
function tutorVoiceReport() {
  loadVoices();
  return TUTORS.map(function (t) { const v = pickVoice(t); return t.name + ': ' + (v ? v.name : 'голос браузера по умолчанию'); });
}

if ('speechSynthesis' in window) {
  loadVoices();
  speechSynthesis.onvoiceschanged = function () {
    loadVoices();
    console.log('Голоса тьюторов:', tutorVoiceReport().join(' | '));
  };
}

// ===== Панель «Настройка голосов» (страница «Тьюторы») =====
// Для каждого тьютора: выбор голоса из всех русских голосов браузера, скорость и высота, «Прослушать».
function mountVoiceTuner(box) {
  if (!box || !('speechSynthesis' in window)) return;
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function slider(label, min, max, step, value, onInput) {
    const wrap = el('label', 'vt-row');
    const cap = el('span', 'vt-cap', label + ': ' + value.toFixed(2));
    const input = el('input');
    input.type = 'range'; input.min = min; input.max = max; input.step = step; input.value = value;
    input.addEventListener('input', function () { cap.textContent = label + ': ' + Number(input.value).toFixed(2); onInput(Number(input.value)); });
    wrap.appendChild(cap); wrap.appendChild(input);
    return wrap;
  }
  function render() {
    loadVoices();
    box.innerHTML = '';
    box.appendChild(el('h2', '', 'Настройка голосов'));
    box.appendChild(el('p', 'muted', ruVoices.length
      ? 'Русских голосов в этом браузере: ' + ruVoices.length + '. Самые живые — с пометкой Natural (есть в Microsoft Edge). Настройки сохраняются в этом браузере.'
      : 'Браузер пока не дал список голосов. Подожди пару секунд или открой сайт в Microsoft Edge.'));
    TUTORS.forEach(function (t) {
      const vs = voiceSettings(t);
      const current = pickVoice(t);
      const card = el('div', 'card vt-card');
      card.appendChild(el('h3', '', t.name));
      const select = el('select', 'vt-select');
      ruVoices.forEach(function (v) {
        const o = el('option', '', v.name);
        o.value = v.name;
        if (current && v.name === current.name) o.selected = true;
        select.appendChild(o);
      });
      select.addEventListener('change', function () { vs.name = select.value; saveVoiceSettings(t, vs); });
      card.appendChild(select);
      card.appendChild(slider('Скорость', 0.6, 1.8, 0.05, vs.rate, function (x) { vs.rate = x; saveVoiceSettings(t, vs); }));
      card.appendChild(slider('Высота', 0.5, 2, 0.05, vs.pitch, function (x) { vs.pitch = x; saveVoiceSettings(t, vs); }));
      const row = el('div', 'vt-buttons');
      const play = el('button', 'chip', '▶ Прослушать');
      play.type = 'button';
      play.addEventListener('click', function () { vs.name = select.value; saveVoiceSettings(t, vs); tutorSpeak(t, t.sample); });
      const reset = el('button', 'chip', 'Сбросить');
      reset.type = 'button';
      reset.addEventListener('click', function () { try { localStorage.removeItem('circuitai-voice-' + t.id); } catch (e) {} render(); });
      row.appendChild(play); row.appendChild(reset);
      card.appendChild(row);
      box.appendChild(card);
    });
    const copy = el('button', 'btn', 'Скопировать настройки для Claude');
    copy.type = 'button';
    copy.addEventListener('click', function () {
      const text = TUTORS.map(function (t) { const v = voiceSettings(t); const p = pickVoice(t);
        return t.name + ': голос «' + (p ? p.name : '-') + '», скорость ' + v.rate.toFixed(2) + ', высота ' + v.pitch.toFixed(2); }).join('\n');
      if (navigator.clipboard) navigator.clipboard.writeText(text);
      copy.textContent = 'Скопировано — вставь в чат';
    });
    box.appendChild(copy);
  }
  render();
  if ('speechSynthesis' in window) speechSynthesis.addEventListener('voiceschanged', render);
}
