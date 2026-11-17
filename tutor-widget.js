// Circuit AI — тьютор на каждой странице: плавающая кнопка + панель чата с голосом и эмоциями.
// Подключается после tutors.js (и modules-data.js, если он есть на странице).
// Другие скрипты управляют тьютором через window.Tutor:
//   Tutor.open(text?)  — открыть панель (и сразу задать вопрос, если передан текст)
//   Tutor.react(data)  — реакция на результат дефектоскопа (эмоция + реплика голосом)
//   Tutor.setContext({ module, defectResult }) — какой модуль открыт и последний результат проверки
(function () {
  const API = window.CIRCUIT_API;
  let tutor = getTutor();
  const ctx = { module: window.CIRCUIT_MODULE || 0, defectResult: null };
  let history = [];
  let emotionTimer = null;
  let speaking = false;

  function load(key, fallback) {
    try { const v = JSON.parse(localStorage.getItem(key)); return v == null ? fallback : v; } catch (e) { return fallback; }
  }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  const MIC = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
  const SEND = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';

  // ---------- Разметка ----------
  const root = el('div', 'tw');
  root.innerHTML =
    '<div class="tw-bubble" role="status" hidden></div>' +
    '<button class="tw-fab" type="button" aria-expanded="false">' +
      '<img class="tw-fab-img" alt="">' +
      '<span class="tw-fab-text"><b class="tw-fab-name"></b><small>Спроси голосом или текстом</small></span>' +
      '<span class="tw-fab-mic">' + MIC + '</span>' +
    '</button>' +
    '<aside class="tw-panel" role="dialog" aria-label="ИИ-тьютор" hidden>' +
      '<header class="tw-head">' +
        '<img class="tw-avatar" alt="">' +
        '<div class="tw-who"><b class="tw-name"></b><span class="tw-role"></span></div>' +
        '<a class="chip tw-change" href="tutors.html">Сменить</a>' +
        '<button class="tw-close" type="button" aria-label="Закрыть">×</button>' +
      '</header>' +
      '<div class="tw-log" aria-live="polite"></div>' +
      '<div class="tw-chips"></div>' +
      '<div class="tw-input">' +
        '<button class="tw-mic" type="button" aria-label="Спросить голосом">' + MIC + '</button>' +
        '<input type="text" class="tw-text" placeholder="Спроси голосом или напиши…" maxlength="500" aria-label="Вопрос тьютору">' +
        '<button class="tw-send" type="button" aria-label="Отправить">' + SEND + '</button>' +
      '</div>' +
      '<label class="tw-voice"><input type="checkbox" class="tw-speak"> Озвучивать ответы</label>' +
    '</aside>';
  document.body.appendChild(root);

  const fab = root.querySelector('.tw-fab');
  const panel = root.querySelector('.tw-panel');
  const log = root.querySelector('.tw-log');
  const input = root.querySelector('.tw-text');
  const sendBtn = root.querySelector('.tw-send');
  const micBtn = root.querySelector('.tw-mic');
  const speakToggle = root.querySelector('.tw-speak');
  const avatar = root.querySelector('.tw-avatar');
  const fabImg = root.querySelector('.tw-fab-img');
  speakToggle.checked = load('circuitai-speak', true);
  speakToggle.addEventListener('change', function () {
    save('circuitai-speak', speakToggle.checked);
    if (!speakToggle.checked) tutorStopSpeech();
  });

  // ---------- Эмоции ----------
  function setEmotion(e, holdMs) {
    clearTimeout(emotionTimer);
    const src = tutorImg(tutor, e);
    if (avatar.getAttribute('src') !== src) {
      avatar.classList.add('swap');
      setTimeout(function () { avatar.src = src; avatar.classList.remove('swap'); }, 120);
    }
    fabImg.src = src;
    root.dataset.emotion = e;
    if (holdMs) emotionTimer = setTimeout(function () { if (!speaking) setEmotion('main'); }, holdMs);
  }

  function renderTutor() {
    root.querySelector('.tw-fab-name').textContent = tutor.name;
    root.querySelector('.tw-name').textContent = tutor.name;
    root.querySelector('.tw-role').textContent = tutor.role;
    root.querySelector('.tw-head').style.background = tutor.bg;
    avatar.alt = tutor.name;
    root.style.setProperty('--tw-color', tutor.color);
    setEmotion('main');
  }

  function speak(text) {
    if (!speakToggle.checked) return;
    tutorSpeak(tutor, text,
      function () { speaking = true; setEmotion('talk'); },
      function () { speaking = false; setEmotion('main'); });
  }

  // ---------- Чат ----------
  function chatKey() { return 'circuitai-chat-' + (ctx.module || 'general'); }

  function addMsg(role, text, remember) {
    const m = el('div', 'tw-msg ' + (role === 'user' ? 'me' : 'bot'), text);
    log.appendChild(m);
    log.scrollTop = log.scrollHeight;
    if (remember) {
      history.push({ role: role === 'user' ? 'user' : 'model', text: text });
      history = history.slice(-50);
      save(chatKey(), history);
    }
    return m;
  }

  function moduleInfo() {
    return (typeof MODULES !== 'undefined' ? MODULES : []).find(function (m) { return m.id === ctx.module; });
  }

  function renderChips() {
    const box = root.querySelector('.tw-chips');
    box.innerHTML = '';
    const m = moduleInfo();
    const list = (m && m.chips && m.chips.length) ? m.chips
      : ['Чем ты можешь помочь?', 'Как пользоваться дефектоскопом?', 'Что такое Arduino?', 'Зачем нужен резистор?'];
    list.forEach(function (t) {
      const c = el('button', 'chip', t);
      c.type = 'button';
      c.addEventListener('click', function () { ask(t); });
      box.appendChild(c);
    });
  }

  function loadChat() {
    log.innerHTML = '';
    history = load(chatKey(), []);
    if (!Array.isArray(history)) history = [];
    if (!history.length) addMsg('bot', tutor.greet, false);
    else history.forEach(function (h) { addMsg(h.role === 'user' ? 'user' : 'bot', h.text, false); });
    renderChips();
  }

  async function ask(text) {
    text = (text || '').trim();
    if (!text) return;
    open();
    const past = history.slice(-10);
    addMsg('user', text, true);
    input.value = '';
    sendBtn.disabled = true;
    const wait = addMsg('bot', 'Думаю…', false);
    wait.classList.add('typing');
    setEmotion('think');
    try {
      const r = await fetch(API + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: past, defect_result: ctx.defectResult, module: ctx.module || 0, avatar: tutor.id })
      });
      const data = await r.json();
      wait.remove();
      const reply = data.reply || 'Не получилось ответить. Попробуй ещё раз.';
      addMsg('bot', reply, r.ok);
      setEmotion('main');
      speak(reply);
    } catch (e) {
      wait.classList.remove('typing');
      wait.textContent = 'Не удалось связаться с сервером. Проверь, что он запущен, и спроси ещё раз.';
      setEmotion('alert', 4000);
    } finally {
      sendBtn.disabled = false;
    }
  }

  // ---------- Открыть / закрыть ----------
  function open(prefill) {
    root.querySelector('.tw-bubble').hidden = true;
    if (panel.hidden) {
      panel.hidden = false;
      root.classList.add('open');
      fab.setAttribute('aria-expanded', 'true');
      if (!log.childElementCount) loadChat();
      setEmotion('wave', 2500);
    }
    if (prefill) ask(prefill);
  }
  function close() {
    panel.hidden = true;
    root.classList.remove('open');
    fab.setAttribute('aria-expanded', 'false');
    tutorStopSpeech();
  }
  fab.addEventListener('click', function () { panel.hidden ? open() : close(); });
  root.querySelector('.tw-close').addEventListener('click', close);
  sendBtn.addEventListener('click', function () { ask(input.value); });
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter') ask(input.value); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) close(); });

  // ---------- Голосовой вопрос ----------
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const fabMic = root.querySelector('.tw-fab-mic');
  if (!Recognition) {
    micBtn.disabled = true;
    micBtn.title = 'Голосовой ввод работает в браузере Chrome';
  } else {
    const rec = new Recognition();
    rec.lang = 'ru-RU';
    rec.interimResults = true;
    let listening = false, finalText = '';
    rec.onresult = function (e) {
      let t = '';
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      input.value = t;
      if (e.results[e.results.length - 1].isFinal) finalText = t;
    };
    rec.onend = function () {
      listening = false;
      root.classList.remove('listening');
      if (finalText.trim()) ask(finalText);
      else setEmotion('main');
      finalText = '';
    };
    rec.onerror = function (e) {
      if (e.error === 'not-allowed') addMsg('bot', 'Разреши доступ к микрофону в браузере, и я буду слушать.', false);
    };
    function listen() {
      open();
      if (listening) { rec.stop(); return; }
      tutorStopSpeech();
      finalText = '';
      listening = true;
      root.classList.add('listening');
      setEmotion('think');
      input.value = '';
      input.placeholder = 'Слушаю…';
      rec.start();
      setTimeout(function () { input.placeholder = 'Спроси голосом или напиши…'; }, 4000);
    }
    micBtn.addEventListener('click', listen);
    fabMic.addEventListener('click', function (e) { e.stopPropagation(); listen(); });
  }

  // ---------- Внешнее управление ----------
  window.Tutor = {
    open: open,
    close: close,
    ask: ask,
    setEmotion: setEmotion,
    setContext: function (c) {
      const moduleChanged = c.module !== undefined && c.module !== ctx.module;
      Object.assign(ctx, c);
      if (moduleChanged && log.childElementCount) loadChat();
    },
    // Реакция на результат дефектоскопа
    react: function (data) {
      ctx.defectResult = data;
      let key = 'ok', emo = 'happy';
      if (data.status === 'no_circuit') { key = 'nocircuit'; emo = 'alert'; }
      else if (data.errors && data.errors.length) { key = 'error'; emo = 'alert'; }
      else if (data.status === 'unclear') { key = 'unclear'; emo = 'think'; }
      const line = tutor.lines[key];
      root.classList.add('pulse');
      setTimeout(function () { root.classList.remove('pulse'); }, 1200);
      setEmotion(emo, 7000);
      addMsg('bot', line, true);
      speak(line);
      if (panel.hidden) {
        const bubble = root.querySelector('.tw-bubble');
        bubble.textContent = line;
        bubble.hidden = false;
        clearTimeout(bubble._t);
        bubble._t = setTimeout(function () { bubble.hidden = true; }, 8000);
      }
      return line;
    },
    current: function () { return tutor; }
  };

  window.addEventListener('tutor-change', function () {
    tutor = getTutor();
    renderTutor();
    log.innerHTML = '';
  });

  renderTutor();
  // Предзагрузка эмоций, чтобы они менялись без задержки
  TUTOR_EMOTIONS.forEach(function (e) { const i = new Image(); i.src = tutorImg(tutor, e); });
  fetch(API + '/').catch(function () {}); // «будильник» для сервера
})();
