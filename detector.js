// Circuit AI — ИИ-дефектоскоп: камера/фото → /check → итог, отметки на снимке, история, реакция тьютора.
(function () {
  const API = window.CIRCUIT_API;
  const $ = function (id) { return document.getElementById(id); };
  function load(k, f) { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? f : v; } catch (e) { return f; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

  // Подсказки «как исправить» по типу ошибки
  const TIPS = [
    [['земля', 'gnd'], 'Проверь, что провод из пина GND на Arduino воткнут до конца, а второй конец стоит в той же половине синей линии или в том же ряду, что и минусы деталей. Без земли цепь разорвана.'],
    [['резистор'], 'У каждого светодиода свой резистор последовательно с ним. Проверь, что все резисторы на месте и обе ножки в плате.'],
    [['висит'], 'Найди провод, у которого конец не воткнут, и вставь его в нужный ряд до упора.'],
    [['светодиод'], 'Длинная ножка светодиода — к пину Arduino, короткая — к GND. Проверь, что все светодиоды на месте.'],
    [['кнопк'], 'Кнопка ставится поперёк канавки посередине платы, провода — к ножкам по диагонали.'],
    [['фоторезистор'], 'Одна ножка фоторезистора — к A0, другая — к GND, ножки в разных рядах.'],
    [['датчик', 'hc-sr04'], 'VCC → 5V, Trig → пин 9, Echo → пин 10, GND → GND. Датчик должен стоять прямо.'],
    [['пищалк', 'зуммер'], 'Плюс пищалки (длинная ножка) — к пину 8, вторая ножка — к GND.']
  ];
  function tipFor(text) {
    const low = text.toLowerCase();
    const hit = TIPS.find(function (t) { return t[0].some(function (k) { return low.indexOf(k) >= 0; }); });
    return hit ? hit[1] : 'Сравни это место со схемой подключения модуля и шагами сборки.';
  }

  // ---------- Модуль ----------
  const params = new URLSearchParams(location.search);
  let mod = MODULES.find(function (m) { return m.id === (Number(params.get('module')) || load('circuitai-module', 1)); }) || MODULES[0];
  const pick = $('modPick');
  MODULES.forEach(function (m) {
    const b = el('button', 'chip', m.id + '. ' + m.title + (m.aiReady ? '' : ' · скоро'));
    b.type = 'button';
    b.setAttribute('aria-pressed', String(m.id === mod.id));
    b.addEventListener('click', function () {
      mod = m;
      save('circuitai-module', m.id);
      pick.querySelectorAll('.chip').forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
      b.setAttribute('aria-pressed', 'true');
      if (window.Tutor) Tutor.setContext({ module: m.id, defectResult: null });
    });
    pick.appendChild(b);
  });
  if (window.Tutor) Tutor.setContext({ module: mod.id });

  // ---------- Камера ----------
  const viewer = $('viewer'), video = $('video'), still = $('still'), stillImg = $('stillImg');
  const empty = $('viewerEmpty'), camBtn = $('camBtn'), liveBtn = $('liveBtn'), checkBtn = $('checkBtn');
  let stream = null, photoBlob = null;

  function showLive() {
    video.hidden = false; still.hidden = true; empty.hidden = true; liveBtn.hidden = true;
    viewer.classList.add('live');
    checkBtn.disabled = false;
    checkBtn.textContent = 'Проверить схему';
  }
  function showStill(src) {
    stillImg.src = src;
    $('marks').innerHTML = '';
    still.hidden = false; video.hidden = true; empty.hidden = true;
    viewer.classList.remove('live');
    liveBtn.hidden = !stream;
    checkBtn.disabled = false;
  }
  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $('timeInfo').textContent = 'Камера доступна только на сайте с адресом https://. Пока загрузи фото.';
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      video.srcObject = stream;
      await video.play();
      camBtn.textContent = 'Выключить камеру';
      showLive();
    } catch (e) {
      stream = null;
      $('timeInfo').textContent = 'Нет доступа к камере. Разреши её в браузере или загрузи фото.';
    }
  }
  function stopCamera() {
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    video.srcObject = null;
    camBtn.textContent = 'Включить камеру';
    viewer.classList.remove('live');
    liveBtn.hidden = true;
    if (photoBlob) { video.hidden = true; still.hidden = false; }
    else { video.hidden = true; empty.hidden = false; checkBtn.disabled = true; }
  }
  camBtn.addEventListener('click', function () { stream ? stopCamera() : startCamera(); });
  liveBtn.addEventListener('click', showLive);

  function toJpeg(source, w, h, max, quality) {
    return new Promise(function (resolve) {
      const s = Math.min(1, max / Math.max(w, h));
      const c = document.createElement('canvas');
      c.width = Math.round(w * s); c.height = Math.round(h * s);
      c.getContext('2d').drawImage(source, 0, 0, c.width, c.height);
      c.toBlob(resolve, 'image/jpeg', quality);
    });
  }
  function fileToImage(file) {
    return new Promise(function (resolve, reject) {
      const img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = reject;
      img.src = URL.createObjectURL(file);
    });
  }
  function blobToDataURL(blob) {
    return new Promise(function (resolve) { const r = new FileReader(); r.onload = function () { resolve(r.result); }; r.readAsDataURL(blob); });
  }

  $('uploadBtn').addEventListener('click', function () { $('fileInput').click(); });
  $('fileInput').addEventListener('change', async function () {
    const f = this.files[0];
    if (!f) return;
    if (stream) stopCamera();
    try {
      const img = await fileToImage(f);
      photoBlob = await toJpeg(img, img.naturalWidth, img.naturalHeight, 1280, 0.85);
    } catch (e) { photoBlob = f; }
    showStill(URL.createObjectURL(photoBlob));
    resetStages();
    $('timeInfo').textContent = 'Фото загружено. Нажми «Проверить схему».';
    this.value = '';
  });

  // ---------- Этапы ----------
  const stages = Array.from(document.querySelectorAll('#stages li'));
  function resetStages() { stages.forEach(function (s) { s.className = ''; }); }
  function stage(i, state) { if (stages[i]) stages[i].className = state; }

  // ---------- Итог ----------
  function drawMarks(marks) {
    const layer = $('marks');
    layer.innerHTML = '';
    (marks || []).forEach(function (m) {
      if (!Array.isArray(m.box) || m.box.length !== 4) return;
      const d = el('div', 'mark ' + (m.kind === 'error' ? 'error' : 'ok'));
      d.style.top = m.box[0] / 10 + '%';
      d.style.left = m.box[1] / 10 + '%';
      d.style.height = (m.box[2] - m.box[0]) / 10 + '%';
      d.style.width = (m.box[3] - m.box[1]) / 10 + '%';
      d.appendChild(el('span', '', m.label || ''));
      layer.appendChild(d);
    });
  }

  function verdictOf(data) {
    if (data.status === 'no_circuit') return { cls: 'warn', icon: '?', title: 'На фото не видно схему', sub: 'Наведи камеру сверху на Arduino и макетную плату.' };
    if (data.errors && data.errors.length) return { cls: 'bad', icon: '!', title: 'Найдена ошибка подключения', sub: 'Ошибок: ' + data.errors.length + '. Разберись с ними ниже или спроси тьютора.' };
    if (data.status === 'unclear') return { cls: 'warn', icon: '~', title: 'Часть схемы не видно', sub: 'Ошибок не найдено, но некоторые места нужно проверить или переснять.' };
    return { cls: 'ok', icon: '✓', title: 'Схема собрана верно', sub: 'Детали и земля на месте. Осталось проверить пины по списку.' };
  }

  function list(title, items) {
    if (!items || !items.length) return null;
    const g = el('div', 'res-group');
    g.appendChild(el('h4', '', title));
    const ul = el('ul');
    items.forEach(function (t) { ul.appendChild(el('li', '', t)); });
    g.appendChild(ul);
    return g;
  }

  function showResult(data) {
    const box = $('result');
    box.innerHTML = '';
    $('resultCard').hidden = false;
    const v = verdictOf(data);
    const vd = el('div', 'verdict ' + v.cls);
    vd.appendChild(el('span', 'v-icon', v.icon));
    const vt = el('div', '', v.title);
    vt.appendChild(el('small', '', v.sub));
    vd.appendChild(vt);
    box.appendChild(vd);
    if (data.status === 'no_circuit') return;

    if (data.errors && data.errors.length) {
      const wrap = el('div', 'res-list');
      data.errors.forEach(function (err) {
        const card = el('div', 'issue');
        card.appendChild(el('b', '', err));
        card.appendChild(el('p', '', 'Как исправить: ' + tipFor(err)));
        const btn = el('button', 'btn btn-sm', 'Разобраться с тьютором');
        btn.type = 'button';
        btn.addEventListener('click', function () { Tutor.open('Помоги разобраться с ошибкой: ' + err); });
        card.appendChild(btn);
        wrap.appendChild(card);
      });
      box.appendChild(wrap);
    }
    const found = list('Что ИИ распознал и подтвердил', data.found);
    if (found) box.appendChild(found);
    const unclear = list('Не удалось рассмотреть', data.unclear);
    if (unclear) box.appendChild(unclear);
    if (data.manual && data.manual.length) {
      const g = el('div', 'res-group');
      g.appendChild(el('h4', '', 'Проверь сам (по фото этого не видно)'));
      data.manual.forEach(function (t) {
        const l = el('label');
        const cb = el('input'); cb.type = 'checkbox';
        l.appendChild(cb); l.appendChild(document.createTextNode(t));
        g.appendChild(l);
      });
      box.appendChild(g);
    }
    const ask = el('button', 'btn btn-ghost btn-sm', 'Спросить тьютора про результат');
    ask.type = 'button';
    ask.style.marginTop = '14px';
    ask.addEventListener('click', function () { Tutor.open('Что значит мой результат?'); });
    box.appendChild(ask);
  }

  function showError(text) {
    const box = $('result');
    $('resultCard').hidden = false;
    box.innerHTML = '';
    const vd = el('div', 'verdict warn');
    vd.appendChild(el('span', 'v-icon', '!'));
    const vt = el('div', '', 'Проверка не завершилась');
    vt.appendChild(el('small', '', text));
    vd.appendChild(vt);
    box.appendChild(vd);
    const again = el('button', 'btn btn-sm', 'Повторить');
    again.type = 'button';
    again.style.marginTop = '12px';
    again.addEventListener('click', function () { runCheck(false); });
    box.appendChild(again);
  }

  // ---------- История ----------
  function renderHistory() {
    const h = load('circuitai-checks', []);
    const box = $('history');
    box.innerHTML = '';
    if (!h.length) { box.appendChild(el('p', 'hint', 'Здесь появятся твои проверки.')); return; }
    h.forEach(function (item) {
      const b = el('button', 'h-item');
      b.type = 'button';
      if (item.thumb) { const im = el('img'); im.src = item.thumb; im.alt = ''; b.appendChild(im); }
      const t = el('span', '', 'Модуль ' + item.module + ' · ' + verdictOf(item.result).title);
      t.appendChild(el('small', '', new Date(item.time).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })));
      b.appendChild(t);
      const dot = el('span', 'h-dot');
      const c = verdictOf(item.result).cls;
      dot.style.background = c === 'ok' ? 'var(--ok)' : c === 'bad' ? 'var(--bad)' : 'var(--warn)';
      b.appendChild(dot);
      b.addEventListener('click', function () {
        if (stream) stopCamera();
        if (item.thumb) showStill(item.thumb);
        drawMarks(item.result.marks);
        showResult(item.result);
        Tutor.setContext({ module: item.module, defectResult: item.result });
      });
      box.appendChild(b);
    });
  }
  async function remember(data) {
    let thumb = '';
    try {
      const img = await fileToImage(photoBlob);
      thumb = await blobToDataURL(await toJpeg(img, img.naturalWidth, img.naturalHeight, 240, 0.6));
    } catch (e) {}
    const h = load('circuitai-checks', []);
    h.unshift({ time: Date.now(), module: mod.id, result: data, thumb: thumb });
    save('circuitai-checks', h.slice(0, 8));
    renderHistory();
  }

  // ---------- Проверка ----------
  async function runCheck(newFrame) {
    if (!mod.aiReady) { showError('Для этого модуля проверка по фото скоро появится. Тьютор уже знает его схему — спроси его.'); return; }
    resetStages();
    if (newFrame && stream && !video.hidden) {
      photoBlob = await toJpeg(video, video.videoWidth, video.videoHeight, 1280, 0.85);
      showStill(URL.createObjectURL(photoBlob));
    }
    if (!photoBlob) return;
    stage(0, 'done');
    checkBtn.disabled = true;
    viewer.classList.add('scanning');
    if (window.Tutor) Tutor.setEmotion('think');
    const info = $('timeInfo');
    const started = Date.now();
    const timer = setInterval(function () { info.textContent = 'Проверяю… ' + Math.round((Date.now() - started) / 1000) + ' с'; }, 300);
    const controller = new AbortController();
    const stopper = setTimeout(function () { controller.abort(); }, 45000);
    let current = 1;
    try {
      const form = new FormData();
      form.append('photo', photoBlob, 'photo.jpg');
      form.append('module', mod.id);
      stage(1, 'active');
      const req = fetch(API + '/check', { method: 'POST', body: form, signal: controller.signal });
      stage(1, 'done'); stage(2, 'active'); current = 2;
      const r = await req;
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || 'Сервер не смог проверить фото. Нажми «Повторить».');
      stage(2, 'done'); stage(3, 'done'); stage(4, 'done');
      info.textContent = data.cached ? 'Это фото уже проверяли — результат сохранён' : 'Проверено за ' + data.seconds + ' с';
      drawMarks(data.marks);
      showResult(data);
      Tutor.setContext({ module: mod.id, defectResult: data });
      Tutor.react(data);
      remember(data);
    } catch (e) {
      stage(current, 'fail');
      info.textContent = '';
      showError(e.name === 'AbortError' ? 'Проверка заняла слишком долго. Нажми «Повторить».'
        : (e.message && e.message !== 'Failed to fetch' ? e.message : 'Не удалось связаться с сервером. Проверь, что он запущен.'));
      if (window.Tutor) Tutor.setEmotion('alert', 4000);
    } finally {
      clearInterval(timer);
      clearTimeout(stopper);
      viewer.classList.remove('scanning');
      checkBtn.disabled = false;
      if (stream) checkBtn.textContent = 'Проверить новый кадр';
    }
  }
  checkBtn.addEventListener('click', function () {
    if (stream && !still.hidden) showLive();
    runCheck(true);
  });

  renderHistory();
})();
