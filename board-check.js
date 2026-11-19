// Circuit AI — проверка схемы через саму плату (USB, Web Serial).
// Arduino раз в 0,5 с присылает строку «CAI|b=3|lcd=1|dht=0|...» с измерениями.
// Два вида проверок:
//  • «измерение» — плата сама видит ошибку (датчик не отвечает, вход висит в воздухе);
//  • «тест» — нажимаешь «Тест», делаешь действие (кнопка, пульт, луч, хлопок),
//    сайт ждёт несколько секунд: реакция пришла — ✓, не пришла — ✗ и подсказка.
// Работает в Chrome/Edge на компьютере, без интернета.
(function () {
  const $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  const box = $('bcBoards');
  if (!box) return;

  const BOARD_NAMES = { 1: 'Плата 1 · Транспорт (модули 1 и 2)', 2: 'Плата 2 · Освещение (модуль 3)', 3: 'Плата 3 · Экология (модули 4 и 5)', 4: 'Плата 4 · Безопасность (модули 6 и 7)' };

  // Измерение: check(s) → { state: 'ok'|'bad'|'warn'|'info', text, fix? }
  // Тест: start(s, st) запоминает начальные значения; pass(s, st) → true, когда реакция пришла.
  const RULES = {
    1: [
      { mod: 1, name: 'Пешеходная кнопка', test: 'Нажми пешеходную кнопку', time: 8,
        pass: function (s) { return s.btn === 1; },
        okText: 'Кнопка работает: нажатие дошло до пина 2.',
        fail: 'Нажатие кнопки не дошло до Arduino.',
        fix: 'Кнопка стоит поперёк канавки посередине платы, провода — к ножкам по диагонали: один в пин 2, другой в GND.' },
      { mod: 1, name: 'Светофор и зуммер',
        check: function () { return { state: 'info', text: 'Светодиоды и зуммер плата не измеряет — проверь глазами: зелёный 3 с, жёлтый 1 с, красный 3 с.' }; } },
      { mod: 2, name: 'Датчик расстояния HC-SR04',
        check: function (s) {
          if (s.miss >= 3) return { state: 'bad', text: 'Датчик HC-SR04 не отвечает.', fix: 'Trig — пин 9, Echo — пин 10 (не перепутаны?), VCC — 5V, GND — GND. Провода вставлены до упора.' };
          return { state: 'ok', text: 'Датчик отвечает: ' + (s.cm >= 0 ? s.cm + ' см' : '…') + '.' };
        } },
      { mod: 2, name: 'Шлагбаум', test: 'Поднеси ладонь ближе 10 см к датчику', time: 8,
        pass: function (s) { return s.open === 1 || (s.cm >= 0 && s.cm < 10); },
        okText: 'Ладонь замечена, плата поднимает шлагбаум. Если серво не двигается — сигнальный провод серво в пин 3.',
        fail: 'Ладонь у датчика не замечена.',
        fix: 'Проверь HC-SR04: Trig — пин 9, Echo — пин 10, питание 5V и GND.' }
    ],
    2: [
      { mod: 3, name: 'Фоторезистор', pauseOnTest: true,
        check: function (s) {
          if (s.a0 >= 1000) return { state: 'bad', text: 'Фоторезистор не подключён: на A0 только встроенная подтяжка (' + s.a0 + ').', fix: 'Одна ножка фоторезистора — в ряд с проводом A0, другая — к GND. Провод A0 вставлен до упора.' };
          return { state: 'ok', text: 'Фоторезистор подключён: A0 = ' + s.a0 + '.' };
        } },
      { mod: 3, name: 'Фонари', test: 'Накрой фоторезистор ладонью', time: 8,
        start: function (s, st) { st.a0 = s.a0; },
        pass: function (s, st) { return s.lamps === 1 || s.a0 > st.a0 + 120; },
        okText: 'Темноту заметил, плата включает фонари. Если какой-то не горит — у него нет резистора или он перевёрнут.',
        fail: 'Темнота не замечена.',
        fix: 'Фоторезистор: одна ножка к A0, другая к GND. Накрой его ладонью полностью.' }
    ],
    3: [
      { mod: 4, name: 'Экран (I2C)',
        check: function (s) {
          if (s.lcd !== 1) return { state: 'bad', text: 'Экран не отвечает по шине I2C.', fix: 'SDA — A4, SCL — A5 (не перепутаны?), VCC — 5V, GND — GND. Все 4 провода экрана вставлены.' };
          return { state: 'ok', text: 'Экран на связи.' };
        } },
      { mod: 4, name: 'Датчик DHT11',
        check: function (s) {
          if (s.dht !== 1) return { state: 'bad', text: 'DHT11 не отвечает.', fix: 'Сигнальный провод DHT11 — в пин 2, VCC — 5V, GND — GND.' };
          return { state: 'ok', text: 'DHT11 работает: ' + s.t + ' °C, ' + s.h + ' %.' };
        } },
      { mod: 4, name: 'Влажность', test: 'Подыши на датчик DHT11', time: 20,
        start: function (s, st) { st.h = s.h; },
        pass: function (s, st) { return s.dht === 1 && s.h >= st.h + 3; },
        okText: 'Влажность выросла — датчик реагирует.',
        fail: 'Влажность не выросла.',
        fix: 'Подыши прямо на решётку датчика. Если не помогает — проверь провод DHT11 в пине 2.' },
      { mod: 5, name: 'Звуковой датчик',
        check: function (s) {
          if (s.snd > 300 || s.snd < 3) return { state: 'bad', text: 'Звуковой датчик подключён неправильно: на A0 странное значение (' + s.snd + ').', fix: 'AO — в A0, G — к GND, + — к 5V. Без провода G датчик выдаёт случайные числа.' };
          return { state: 'ok', text: 'Датчик подключён: тишина ' + s.snd + ', размах ' + s.lvl + '.' };
        } },
      { mod: 5, name: 'Реакция на шум', test: 'Хлопни в ладоши рядом с датчиком', time: 8,
        pass: function (s) { return s.peak > s.base + 60; },
        okText: 'Хлопок услышан. RGB должен стать красным на 2 с — если не стал, проверь R → 9, G → 10, B → 11.',
        fail: 'Хлопок не услышан.',
        fix: 'AO датчика — в A0, G — GND, + — 5V. Хлопни ближе к микрофону.' }
    ],
    4: [
      { mod: 6, name: 'Датчик огня (ИК-диод)', test: 'Нажми кнопку пульта над ИК-диодом', time: 8,
        pass: function (s) { return s.fire === 1; },
        okText: 'ИК-сигнал дошёл до A1, плата включила тревогу. Нет звука — зуммер (пин 8), нет света — красный светодиод (пин 5).',
        fail: 'ИК-сигнал не дошёл до Arduino.',
        fix: 'Провод ИК-диода должен быть в A1, а не в соседнем гнезде; вторая ножка — в GND. Направь пульт прямо на диод.' },
      { mod: 7, name: 'Фоторезистор барьера', pauseOnTest: true,
        check: function (s) {
          if (s.a0 > 900) return { state: 'bad', text: 'Фоторезистор не получает луч (' + s.a0 + ').', fix: 'Проверь провод A0 и GND фоторезистора; излучатель должен гореть и светить прямо в фоторезистор (его резистор на месте?).' };
          return { state: 'ok', text: 'Луч на месте: A0 = ' + s.a0 + '.' };
        } },
      { mod: 7, name: 'Охрана', test: 'Перекрой луч рукой', time: 8,
        start: function (s, st) { st.p = s.passes; },
        pass: function (s, st) { return s.passes > st.p; },
        okText: 'Проход засчитан. Не мигнул светодиод тревоги — проверь его (пин 6) и резистор.',
        fail: 'Проход не засчитан.',
        fix: 'Излучатель должен светить прямо в фоторезистор с 2–4 см; фоторезистор — A0 и GND.' }
    ]
  };

  function parse(line) {
    if (line.indexOf('CAI|') !== 0) return null;
    const s = {};
    line.split('|').slice(1).forEach(function (kv) {
      const p = kv.split('=');
      if (p.length === 2) { const n = Number(p[1]); s[p[0]] = isNaN(n) ? p[1] : n; }
    });
    return s.b ? s : null;
  }

  function say(mod, status, text, speech, fix) {
    if (!window.Tutor) return;
    Tutor.setContext({ module: mod });
    // errors + fixes уходят в чат: тьютор отвечает по реальному результату платы
    Tutor.react({ status: status, errors: status === 'error' ? [text] : [], fixes: fix ? [fix] : [], source: 'board', module: mod, speech: speech });
  }

  // ---------- Подключённые платы ----------
  const boards = [];

  const ICON = { ok: '✓', bad: '✗', warn: '!', wait: '…', info: 'i', run: '⏱' };
  function paint(ui, state, text, fix) {
    ui.row.className = 'bc-row ' + state;
    ui.icon.textContent = ICON[state] || '•';
    ui.text.textContent = text;
    ui.fix.textContent = fix ? 'Как исправить: ' + fix : '';
  }

  function buildCard(bd) {
    const card = el('div', 'bc-board');
    const head = el('div', 'bc-head');
    head.appendChild(el('b', '', BOARD_NAMES[bd.b] || ('Плата ' + bd.b)));
    bd.live = el('span', 'bc-live', 'на связи');
    head.appendChild(bd.live);
    card.appendChild(head);
    bd.rows = (RULES[bd.b] || []).map(function (r, i) {
      const row = el('div', 'bc-row');
      const icon = el('span', 'bc-icon', '…');
      const body = el('div', 'bc-body');
      body.appendChild(el('b', '', 'Модуль ' + r.mod + ' · ' + r.name));
      const text = el('span', 'bc-text', r.test ? 'Нажми «Тест» и сделай: ' + r.test.toLowerCase() + '.' : 'Жду данные от платы…');
      const fix = el('span', 'bc-fix');
      body.appendChild(text); body.appendChild(fix);
      row.appendChild(icon); row.appendChild(body);
      let btn = null;
      if (r.test) {
        btn = el('button', 'btn btn-sm bc-test', 'Тест');
        btn.type = 'button';
        btn.addEventListener('click', function () { startTest(bd, i); });
        row.appendChild(btn);
      }
      card.appendChild(row);
      return { row: row, icon: icon, text: text, fix: fix, btn: btn };
    });
    bd.raw = el('code', 'bc-raw');
    card.appendChild(bd.raw);
    box.appendChild(card);
    bd.card = card;
  }

  function startTest(bd, i) {
    const r = RULES[bd.b][i];
    const st = bd.state[i] = { run: true, until: Date.now() + r.time * 1000 };
    if (r.start && bd.last) r.start(bd.last, st);
    bd.rows[i].btn.textContent = 'Ещё раз';
    paint(bd.rows[i], 'run', '👉 ' + r.test + ' (' + r.time + ' с)…');
  }

  function testRunning(bd) {
    return Object.keys(bd.state).some(function (k) { return bd.state[k] && bd.state[k].run; });
  }

  function update(bd, s, line) {
    if (!bd.card) buildCard(bd);
    bd.last = s;
    bd.lastAt = Date.now();
    bd.live.textContent = 'на связи'; bd.live.className = 'bc-live';
    bd.raw.textContent = line;
    const busy = testRunning(bd);
    (RULES[bd.b] || []).forEach(function (r, i) {
      const ui = bd.rows[i];
      const st = bd.state[i] || (bd.state[i] = {});
      if (r.test) {
        if (!st.run) return;
        if (r.pass(s, st)) {
          st.run = false;
          paint(ui, 'ok', r.okText);
          say(r.mod, 'ok', r.okText, 'Отлично! ' + r.okText);
        }
        return;
      }
      if (r.pauseOnTest && busy) return;   // во время теста (например, перекрыли луч) не ругаемся
      const res = r.check(s);
      paint(ui, res.state, res.text, res.fix);
      // тьютор говорит, когда проблема держится 2 отчёта подряд, и когда её исправили
      if (res.state === 'bad') {
        st.badN = (st.badN || 0) + 1;
        if (st.badN === 2 && !st.said) { st.said = true; say(r.mod, 'error', res.text, res.text + ' ' + (res.fix || ''), res.fix); }
      } else {
        st.badN = 0;
        if (st.said && res.state === 'ok') { st.said = false; say(r.mod, 'ok', res.text, 'Исправлено! ' + r.name + ' снова работает.'); }
      }
    });
  }

  // таймеры тестов и потеря связи
  setInterval(function () {
    boards.forEach(function (bd) {
      if (!bd.card) return;
      if (Date.now() - bd.lastAt > 3000) {
        bd.live.textContent = 'нет данных — залит новый скетч? закрыт Монитор порта?';
        bd.live.className = 'bc-live off';
      }
      (RULES[bd.b] || []).forEach(function (r, i) {
        const st = bd.state[i];
        if (!r.test || !st || !st.run) return;
        const left = Math.ceil((st.until - Date.now()) / 1000);
        if (left > 0) { bd.rows[i].text.textContent = '👉 ' + r.test + ' (' + left + ' с)…'; return; }
        st.run = false;
        paint(bd.rows[i], 'bad', r.fail, r.fix);
        say(r.mod, 'error', r.fail, r.fail + ' ' + r.fix, r.fix);
      });
    });
  }, 250);

  async function readLoop(bd) {
    const decoder = new TextDecoderStream();
    bd.port.readable.pipeTo(decoder.writable).catch(function () {});
    const reader = decoder.readable.getReader();
    let buf = '';
    try {
      while (true) {
        const r = await reader.read();
        if (r.done) break;
        buf += r.value;
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i).trim();
          buf = buf.slice(i + 1);
          const s = parse(line);
          if (!s) continue;
          if (bd.b !== s.b) {             // плату узнали по первой строке
            if (bd.card) { bd.card.remove(); bd.card = null; }
            bd.b = s.b; bd.state = {};
          }
          update(bd, s, line);
        }
      }
    } catch (e) {
      if (bd.live) { bd.live.textContent = 'плата отключена'; bd.live.className = 'bc-live off'; }
    }
  }

  async function connect() {
    const status = $('bcStatus');
    if (!('serial' in navigator)) {
      status.textContent = 'Этот браузер не умеет работать с USB. Открой сайт в Chrome или Edge на компьютере.';
      return;
    }
    try {
      const port = await navigator.serial.requestPort();
      await port.open({ baudRate: 9600 });
      const bd = { port: port, b: null, state: {}, lastAt: Date.now() };
      boards.push(bd);
      status.textContent = 'Плата подключена. Через 2–3 секунды (калибровка) появятся проверки.';
      readLoop(bd);
    } catch (e) {
      if (e && e.name === 'NotFoundError') status.textContent = 'Порт не выбран.';
      else if (e && e.name === 'InvalidStateError') status.textContent = 'Этот порт уже открыт.';
      else status.textContent = 'Не удалось открыть порт. Закрой Монитор порта в Arduino IDE и попробуй снова.';
    }
  }
  $('bcConnect').addEventListener('click', connect);
  if (!('serial' in navigator)) $('bcStatus').textContent = 'Проверка по USB работает в Chrome или Edge на компьютере.';
})();
