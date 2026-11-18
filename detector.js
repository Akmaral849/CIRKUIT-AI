// Circuit AI — ИИ-дефектоскоп.
// Главная проверка: своя нейросеть (Teachable Machine, папка models/mN) прямо в браузере,
// без интернета и без лимитов. Живая камера несколько раз в секунду пишет вердикт.
// Запасная проверка: сервер /check (Gemini) — кнопка «Подробная проверка Gemini».
(function () {
  const API = window.CIRCUIT_API;
  const $ = function (id) { return document.getElementById(id); };
  function load(k, f) { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? f : v; } catch (e) { return f; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

  // Подсказки «как исправить» по типу ошибки (для ответов Gemini)
  const TIPS = [
    [['пины', 'гнезд'], 'Сравни, в какие гнёзда Arduino воткнуты провода, со схемой модуля. Скорее всего, один провод стоит в соседнем гнезде — переставь его.'],
    [['trig', 'echo'], 'Trig идёт в пин 9, Echo — в пин 10. Если их перепутать, датчик всё время показывает 999.'],
    [['сервопривод', 'серво'], 'Оранжевый (сигнальный) провод сервопривода — в пин 3, коричневый — к минусу, красный — к плюсу.'],
    [['dht'], 'Сигнальная ножка DATA датчика DHT11 идёт в пин 2, VCC — к 5V, GND — к GND.'],
    [['sda', 'scl', 'экран'], 'SDA платы I2C идёт в A4, SCL — в A5. Если их поменять местами, экран не найдётся.'],
    [['звуков', 'ao '], 'Контакт AO звукового датчика идёт в A0, плюс — к 5V, G — к GND.'],
    [['rgb'], 'R — пин 9, G — пин 10, B — пин 11, общий контакт — GND.'],
    [['ик-диод'], 'Одна ножка ИК-диода — в ряду с проводом A1, другая — к GND.'],
    [['луч', 'излучател'], 'Светодиод-излучатель должен смотреть головкой прямо на фоторезистор с расстояния 2–4 см.'],
    [['полярн'], 'Длинная ножка светодиода — к пину Arduino, короткая — через резистор к GND. Переверни светодиод.'],
    [['земля', 'gnd'], 'Проверь, что провод из пина GND на Arduino воткнут до конца, а второй конец стоит в той же половине синей линии или в том же ряду, что и минусы деталей. Без земли цепь разорвана.'],
    [['резистор'], 'У каждого светодиода свой резистор последовательно с ним. Проверь, что все резисторы на месте и обе ножки в плате.'],
    [['висит', 'висящ'], 'Найди провод, у которого конец не воткнут, и вставь его в нужный ряд до упора.'],
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

  // ---------- Своя нейросеть: классы и объяснения ----------
  const MIN_CONF = 0.70;   // меньше — нейросеть честно просит переснять
  const SHORT = {
    ok: 'Правильно',
    net_detali: 'Не хватает детали',
    net_rezistora: 'Нет резистора',
    visyachiy_provod: 'Висящий провод',
    trig_echo: 'Trig и Echo перепутаны',
    sda_scl: 'SDA и SCL перепутаны',
    net_gnd: 'Нет провода GND',
    ne_tot_pin: 'Провод не в том пине'
  };
  // [что не так, как исправить] — по реальной сборке модулей на макете
  const NN_ERRORS = {
    1: {
      net_detali: ['Не хватает детали: проверь красный светодиод и пешеходную кнопку.', 'Верни деталь на место: светодиод длинной ножкой к пину Arduino, кнопку поперёк канавки посередине платы.'],
      net_rezistora: ['Не хватает резистора у одного из светодиодов светофора.', 'У каждого светодиода свой резистор последовательно с ним. Вставь резистор обеими ножками в плату.'],
      visyachiy_provod: ['Висит провод — скорее всего, провод зуммера.', 'Найди провод, у которого конец не воткнут, и вставь до упора: плюс зуммера идёт к пину 8.']
    },
    2: {
      net_detali: ['Не хватает детали: проверь датчик HC-SR04 и разъём сервопривода.', 'HC-SR04: VCC → 5V, Trig → пин 9, Echo → пин 10, GND → GND. Сигнальный провод серво — в пин 3.'],
      trig_echo: ['Провода Trig и Echo перепутаны.', 'Trig должен идти в пин 9, Echo — в пин 10. Поменяй эти два провода местами.'],
      visyachiy_provod: ['Висит провод — проверь провод Echo.', 'Провод Echo идёт в пин 10. Вставь оба его конца до упора.']
    },
    3: {
      net_detali: ['Не хватает детали: проверь фоторезистор и светодиоды-фонари.', 'Фоторезистор: одна ножка к A0, другая к GND. У каждого фонаря длинная ножка к пину, короткая через резистор к GND.'],
      net_rezistora: ['Не хватает резистора у фонаря.', 'Каждый светодиод-фонарь подключается через свой резистор. Вставь резистор обеими ножками.'],
      visyachiy_provod: ['Висит провод — проверь провод A0.', 'Провод от фоторезистора должен быть воткнут в A0 на Arduino до упора.']
    },
    4: {
      net_detali: ['Не хватает детали: проверь датчик DHT11 и 4 провода экрана.', 'DHT11: DATA → пин 2, VCC → 5V, GND → GND. Экран: GND, VCC, SDA → A4, SCL → A5.'],
      sda_scl: ['Провода SDA и SCL экрана перепутаны.', 'SDA должен идти в A4, SCL — в A5. Поменяй их местами, иначе экран не найдётся.'],
      visyachiy_provod: ['Висит провод — проверь провод датчика DHT11.', 'Сигнальный провод DHT11 идёт в пин 2. Вставь его до упора.']
    },
    5: {
      net_detali: ['Не хватает детали: проверь звуковой датчик и RGB-модуль.', 'Датчик: AO → A0, + → 5V, G → GND. RGB: R → 9, G → 10, B → 11, общий → GND.'],
      net_gnd: ['У звукового датчика нет провода G (земля).', 'Подключи контакт G звукового датчика к минусу (GND). Без земли датчик показывает случайные числа.'],
      visyachiy_provod: ['Висит провод — проверь провод AO звукового датчика.', 'Контакт AO датчика идёт в A0 на Arduino. Вставь провод до упора.']
    },
    6: {
      net_detali: ['Не хватает детали: проверь ИК-диод и зуммер.', 'ИК-диод: одна ножка в ряду с проводом A1, другая к GND. Плюс зуммера — к пину 8.'],
      ne_tot_pin: ['Провод датчика огня стоит не в том пине.', 'Провод от ИК-диода должен идти в A1, а не в соседнее гнездо. Переставь его.'],
      visyachiy_provod: ['Висит провод — проверь провод красного светодиода.', 'Красный светодиод тревоги подключается к пину 5. Вставь провод до упора.']
    },
    7: {
      net_detali: ['Не хватает детали: проверь фоторезистор и светодиод-излучатель.', 'Излучатель светит прямо на фоторезистор с 2–4 см. Фоторезистор: одна ножка к A0, другая к GND.'],
      net_rezistora: ['Не хватает резистора у светодиода тревоги.', 'Светодиод тревоги (пин 6) подключается через резистор. Вставь резистор обеими ножками.'],
      visyachiy_provod: ['Висит провод — проверь провод A0.', 'Провод от фоторезистора барьера идёт в A0. Вставь его до упора.']
    }
  };
  function nnError(modId, label) {
    const m = NN_ERRORS[modId] || {};
    return m[label] || [(SHORT[label] || label) + '.', 'Сравни это место со схемой подключения модуля.'];
  }

  const nn = { ready: typeof tf !== 'undefined', models: {}, loading: {}, avg: null, busy: false };
  const canvas224 = document.createElement('canvas');
  canvas224.width = 224; canvas224.height = 224;
  const ctx224 = canvas224.getContext('2d');

  async function getModel(id) {
    if (!nn.ready) throw new Error('no-tf');
    if (nn.models[id]) return nn.models[id];
    if (!nn.loading[id]) {
      nn.loading[id] = (async function () {
        const base = 'models/m' + id + '/';
        const meta = await (await fetch(base + 'metadata.json', { cache: 'no-store' })).json();
        const model = await tf.loadLayersModel(base + 'model.json');
        // прогрев, чтобы первый живой кадр не тормозил
        tf.tidy(function () { model.predict(tf.zeros([1, 224, 224, 3])); });
        nn.models[id] = { model: model, labels: meta.labels };
        return nn.models[id];
      })();
      nn.loading[id].catch(function () { delete nn.loading[id]; });
    }
    return nn.loading[id];
  }

  // Кадр → квадрат 224×224 с серыми полями (как кадры, на которых училась нейросеть) → вероятности
  // Браузер при сильном уменьшении (1280 → 224) пропускает пиксели, и картинка «рябит».
  // Поэтому уменьшаем по шагам, каждый раз в 2 раза — так кадр похож на кадры, на которых училась нейросеть.
  const stepCanvas = [document.createElement('canvas'), document.createElement('canvas')];
  function downscaled(source, w, h, tw) {
    let src = source, cw = w, ch = h, i = 0;
    while (cw / 2 >= tw) {
      const c = stepCanvas[i % 2];
      c.width = Math.round(cw / 2); c.height = Math.round(ch / 2);
      const x = c.getContext('2d');
      x.imageSmoothingEnabled = true; x.imageSmoothingQuality = 'high';
      x.drawImage(src, 0, 0, c.width, c.height);
      src = c; cw = c.width; ch = c.height; i++;
    }
    return { src: src, w: cw, h: ch };
  }
  function predictFrom(m, source, w, h) {
    const k = 224 / Math.max(w, h);
    const dw = Math.round(w * k), dh = Math.round(h * k);
    const small = downscaled(source, w, h, Math.max(dw, dh) === dw ? dw : Math.round(w * k));
    ctx224.fillStyle = 'rgb(128,128,128)';
    ctx224.fillRect(0, 0, 224, 224);
    ctx224.imageSmoothingEnabled = true; ctx224.imageSmoothingQuality = 'high';
    ctx224.drawImage(small.src, 0, 0, small.w, small.h, Math.round((224 - dw) / 2), Math.round((224 - dh) / 2), dw, dh);
    return tf.tidy(function () {
      const x = tf.browser.fromPixels(canvas224).toFloat().div(tf.scalar(127)).sub(tf.scalar(1)).expandDims(0);
      return Array.from(m.model.predict(x).dataSync());
    });
  }

  function topOf(m, probs) {
    let best = 0;
    probs.forEach(function (p, i) { if (p > probs[best]) best = i; });
    return { label: m.labels[best], p: probs[best] };
  }

  function nnResult(m, probs) {
    const top = topOf(m, probs);
    const pct = Math.round(top.p * 100);
    const scores = m.labels.map(function (l, i) { return { label: l, name: SHORT[l] || l, p: probs[i] }; })
      .sort(function (a, b) { return b.p - a.p; });
    const data = { source: 'nn', module: mod.id, label: top.label, confidence: top.p, scores: scores, errors: [], fixes: [], found: [], unclear: [], manual: [] };
    if (top.p < MIN_CONF) {
      data.status = 'unclear';
      data.unclear = ['Нейросеть не уверена (' + pct + ' %). Сними плату сверху и ближе, чтобы в кадре были Arduino и вся макетная плата.'];
      data.speech = 'Я не уверен, что вижу схему чётко. Сними плату сверху и чуть ближе.';
    } else if (top.label === 'ok') {
      data.status = 'ok';
      data.found = ['Своя нейросеть Circuit AI: сборка совпадает с правильной (уверенность ' + pct + ' %).'];
      data.speech = 'Нейросеть уверена на ' + pct + ' процентов: схема собрана правильно.';
    } else {
      const e = nnError(mod.id, top.label);
      data.status = 'error';
      data.errors = [e[0]];
      data.fixes = [e[1]];
      data.speech = e[0] + ' ' + e[1];
    }
    return data;
  }

  // ---------- Сравнение с эталоном (главный режим для живого показа) ----------
  // Телефон стоит неподвижно. Эталон снимается ~2,5 с: для каждой точки запоминаем
  // диапазон яркости (мигание светодиодов и шум камеры попадают в допуск).
  // Потом каждый кадр сравнивается с этим диапазоном, изменённые участки обводятся рамкой.
  const CW = 480, CELL = 10, DIFF_T = 22, CELL_FRAC = 0.08, STABLE = 4, MIN_PX = 15, EDGE = 0.07, SEARCH = 9;
  const cmp = { lo: null, hi: null, mean: 0, w: 0, h: 0, capturing: false, persist: null, boxes: [], moved: false, cells: 0 };
  const cmpCanvas = document.createElement('canvas');
  const cmpCtx = cmpCanvas.getContext('2d', { willReadFrequently: true });

  function blur3(a, w, h) {
    const o = new Float32Array(a.length);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let s = 0, n = 0;
        for (let dy = -1; dy <= 1; dy++) {
          const yy = y + dy; if (yy < 0 || yy >= h) continue;
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx; if (xx < 0 || xx >= w) continue;
            s += a[yy * w + xx]; n++;
          }
        }
        o[y * w + x] = s / n;
      }
    }
    return o;
  }
  function grabGray(src, sw, sh) {
    const w = CW, h = Math.max(1, Math.round(CW * sh / sw));
    if (cmpCanvas.width !== w || cmpCanvas.height !== h) { cmpCanvas.width = w; cmpCanvas.height = h; }
    cmpCtx.drawImage(src, 0, 0, w, h);
    const d = cmpCtx.getImageData(0, 0, w, h).data;
    let g = new Float32Array(w * h), sum = 0;
    for (let i = 0, j = 0; i < g.length; i++, j += 4) g[i] = 0.299 * d[j] + 0.587 * d[j + 1] + 0.114 * d[j + 2];
    g = blur3(g, w, h);
    for (let i = 0; i < g.length; i++) sum += g[i];
    return { g: g, w: w, h: h, mean: sum / g.length };
  }
  // допуск на сдвиг камеры в 1 пиксель: min/max по соседям 3×3
  function spread(a, w, h, useMax) {
    const o = new Float32Array(a.length);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let v = a[y * w + x];
        for (let dy = -1; dy <= 1; dy++) {
          const yy = y + dy; if (yy < 0 || yy >= h) continue;
          for (let dx = -1; dx <= 1; dx++) {
            const xx = x + dx; if (xx < 0 || xx >= w) continue;
            const u = a[yy * w + xx];
            if (useMax ? u > v : u < v) v = u;
          }
        }
        o[y * w + x] = v;
      }
    }
    return o;
  }

  function captureReference() {
    if (!stream || !video.videoWidth) return;
    cmp.capturing = true;
    cmp.lo = null; cmp.boxes = []; cmp.persist = null; cmp.moved = false;
    drawLiveMarks([]);
    const frames = [];
    let n = 0;
    $('timeInfo').textContent = 'Запоминаю правильную сборку… не двигай телефон и плату';
    const t = setInterval(function () {
      frames.push(grabGray(video, video.videoWidth, video.videoHeight));
      n++;
      if (n < 10) return;
      clearInterval(t);
      const f0 = frames[0], w = f0.w, h = f0.h;
      let lo = new Float32Array(w * h).fill(255), hi = new Float32Array(w * h).fill(0);
      frames.forEach(function (f) {
        const k = f0.mean / (f.mean || 1);
        for (let i = 0; i < lo.length; i++) { const v = f.g[i] * k; if (v < lo[i]) lo[i] = v; if (v > hi[i]) hi[i] = v; }
      });
      cmp.lo = spread(lo, w, h, false);
      cmp.hi = spread(hi, w, h, true);
      cmp.mean = f0.mean; cmp.w = w; cmp.h = h;
      cmp.mid = new Float32Array(w * h);
      for (let i = 0; i < cmp.mid.length; i++) cmp.mid[i] = (lo[i] + hi[i]) / 2;
      cmp.persist = new Uint8Array(Math.ceil(w / CELL) * Math.ceil(h / CELL));
      cmp.capturing = false;
      $('refBtn').textContent = 'Запомнить заново';
      $('timeInfo').textContent = 'Эталон сохранён. Теперь можно вынуть деталь — место изменения обведётся рамкой.';
      if (window.Tutor) Tutor.setEmotion('happy', 2500);
    }, 250);
  }

  function compareFrame() {
    const f = grabGray(video, video.videoWidth, video.videoHeight);
    if (f.w !== cmp.w || f.h !== cmp.h) { cmp.lo = null; return; }
    const w = f.w, h = f.h, k = cmp.mean / (f.mean || 1);
    // Телефон мог чуть сдвинуться: ищем сдвиг кадра (до ±6 пикселей), при котором он лучше всего совпадает с эталоном
    let bx = 0, by = 0, best = Infinity;
    for (let sy = -SEARCH; sy <= SEARCH; sy += 2) {
      for (let sx = -SEARCH; sx <= SEARCH; sx += 2) {
        let e = 0, n = 0;
        for (let y = SEARCH; y < h - SEARCH; y += 3) {
          for (let x = SEARCH; x < w - SEARCH; x += 3) { e += Math.abs(f.g[y * w + x] * k - cmp.mid[(y + sy) * w + x + sx]); n++; }
        }
        e /= n;
        if (e < best) { best = e; bx = sx; by = sy; }
      }
    }
    const cx = bx, cy = by;
    for (let sy = cy - 1; sy <= cy + 1; sy++) {
      for (let sx = cx - 1; sx <= cx + 1; sx++) {
        if ((sx === cx && sy === cy) || Math.abs(sx) > SEARCH || Math.abs(sy) > SEARCH) continue;
        let e = 0, n = 0;
        for (let y = SEARCH; y < h - SEARCH; y += 3) {
          for (let x = SEARCH; x < w - SEARCH; x += 3) { e += Math.abs(f.g[y * w + x] * k - cmp.mid[(y + sy) * w + x + sx]); n++; }
        }
        e /= n;
        if (e < best) { best = e; bx = sx; by = sy; }
      }
    }
    const gw = Math.ceil(w / CELL), gh = Math.ceil(h / CELL);
    const cnt = new Uint16Array(gw * gh), tot = new Uint16Array(gw * gh);
    for (let y = 0; y < h; y++) {
      const ry = y + by; if (ry < 0 || ry >= h) continue;
      for (let x = 0; x < w; x++) {
        const rx = x + bx; if (rx < 0 || rx >= w) continue;
        const i = y * w + x, j = ry * w + rx, v = f.g[i] * k;
        const d = v < cmp.lo[j] ? cmp.lo[j] - v : (v > cmp.hi[j] ? v - cmp.hi[j] : 0);
        const c = ((y / CELL) | 0) * gw + ((x / CELL) | 0);
        tot[c]++;
        if (d > DIFF_T) cnt[c]++;
      }
    }
    // края кадра не учитываем: там больше всего ложных отличий от наклона телефона
    const ex = Math.ceil(gw * EDGE), ey = Math.ceil(gh * EDGE);
    let stable = 0;
    for (let c = 0; c < cnt.length; c++) {
      const ccx = c % gw, ccy = (c / gw) | 0;
      const edge = ccx < ex || ccy < ey || ccx >= gw - ex || ccy >= gh - ey;
      if (!edge && tot[c] && cnt[c] / tot[c] > CELL_FRAC) cmp.persist[c] = Math.min(255, cmp.persist[c] + 1);
      else cmp.persist[c] = 0;
      if (cmp.persist[c] >= STABLE) stable++;
    }
    cmp.moved = stable > cnt.length * 0.35;
    // соседние изменённые клетки → одна рамка
    const seen = new Uint8Array(cnt.length), boxes = [];
    for (let c = 0; c < cnt.length; c++) {
      if (seen[c] || cmp.persist[c] < STABLE) continue;
      const q = [c]; seen[c] = 1;
      let x0 = gw, y0 = gh, x1 = 0, y1 = 0, px = 0;
      while (q.length) {
        const u = q.pop(), ux = u % gw, uy = (u / gw) | 0;
        px += cnt[u];
        if (ux < x0) x0 = ux; if (ux > x1) x1 = ux; if (uy < y0) y0 = uy; if (uy > y1) y1 = uy;
        [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(function (dd) {
          const nx = ux + dd[0], ny = uy + dd[1];
          if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) return;
          const v2 = ny * gw + nx;
          if (!seen[v2] && cmp.persist[v2] >= STABLE) { seen[v2] = 1; q.push(v2); }
        });
      }
      if (px < MIN_PX) continue;
      boxes.push({ px: px, box: [
        Math.max(0, (y0 - 0.5) * CELL / h * 1000), Math.max(0, (x0 - 0.5) * CELL / w * 1000),
        Math.min(1000, (y1 + 1.5) * CELL / h * 1000), Math.min(1000, (x1 + 1.5) * CELL / w * 1000)] });
    }
    boxes.sort(function (a, b) { return b.px - a.px; });
    cmp.boxes = cmp.moved ? [] : boxes.slice(0, 4);
  }

  // рамки поверх живого видео (учитываем поля object-fit: contain)
  function drawLiveMarks(boxes) {
    const layer = $('liveMarks');
    if (!layer) return;
    if (!boxes.length || video.hidden || !video.videoWidth) { layer.innerHTML = ''; return; }
    const vw = video.clientWidth, vh = video.clientHeight, a = video.videoWidth / video.videoHeight;
    const cw = Math.min(vw, vh * a), ch = cw / a;
    layer.style.left = (video.offsetLeft + (vw - cw) / 2) + 'px';
    layer.style.top = (video.offsetTop + (vh - ch) / 2) + 'px';
    layer.style.width = cw + 'px'; layer.style.height = ch + 'px';
    drawMarks(boxes.map(function (b) { return { box: b.box, kind: 'error', label: 'Отличие' }; }), layer);
  }

  function cmpHint(modId) {
    const m = NN_ERRORS[modId] || {};
    return Object.keys(m).map(function (k) { return m[k][0]; }).join(' ');
  }
  function cmpResult() {
    const n = cmp.boxes.length;
    const data = { source: 'cmp', module: mod.id, errors: [], fixes: [], found: [], unclear: [], manual: [],
      marks: cmp.boxes.map(function (b) { return { box: b.box, kind: 'error', label: 'Отличие' }; }) };
    if (cmp.moved) {
      data.status = 'unclear';
      data.unclear = ['Изменилась почти вся картинка: сдвинулась камера или в кадре рука. Нажми «Запомнить заново», не двигая телефон.'];
      data.speech = 'Похоже, камера сдвинулась. Запомни правильную сборку заново.';
    } else if (n) {
      data.status = 'error';
      data.errors = ['Плата отличается от правильной сборки: ' + (n === 1 ? 'одно место' : n + ' места') + ' в красной рамке.'];
      data.fixes = ['Посмотри в рамку: там вынута деталь, выдернут или переставлен провод. Частые ошибки этого модуля: ' + cmpHint(mod.id)];
      data.speech = 'Я сравнил плату с правильной сборкой и нашёл отличие. Посмотри в красную рамку: там вынута деталь или выдернут провод. Верни её на место по схеме.';
    } else {
      data.status = 'ok';
      data.found = ['Сравнение с эталоном: отличий от правильной сборки не найдено.'];
      data.speech = 'Плата совпадает с правильной сборкой. Отличий не вижу.';
    }
    return data;
  }

  // ---------- Модуль ----------
  const params = new URLSearchParams(location.search);
  let mod = MODULES.find(function (m) { return m.id === (Number(params.get('module')) || load('circuitai-module', 1)); }) || MODULES[0];
  const pick = $('modPick');
  MODULES.forEach(function (m) {
    const b = el('button', 'chip', m.id + '. ' + m.title);
    b.type = 'button';
    b.setAttribute('aria-pressed', String(m.id === mod.id));
    b.addEventListener('click', function () {
      mod = m;
      save('circuitai-module', m.id);
      pick.querySelectorAll('.chip').forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
      b.setAttribute('aria-pressed', 'true');
      nn.avg = null;
      cmp.lo = null; cmp.boxes = [];
      $('refBtn').textContent = 'Запомнить правильную сборку';
      drawLiveMarks([]);
      if (window.Tutor) Tutor.setContext({ module: m.id, defectResult: null });
      if (window.renderDemo) window.renderDemo();
      prepareModel();
    });
    pick.appendChild(b);
  });
  if (window.Tutor) Tutor.setContext({ module: mod.id });

  const nnStatus = $('nnStatus');
  function setNnStatus(text, cls) { if (nnStatus) { nnStatus.textContent = text; nnStatus.className = 'nn-status ' + (cls || ''); } }
  function prepareModel() {
    if (!nn.ready) {
      setNnStatus('Нейросеть не загрузилась: нет файла lib/tf.min.js и нет интернета. Работает проверка Gemini и готовые фото.', 'bad');
      return;
    }
    const id = mod.id;
    setNnStatus('Загружаю нейросеть модуля ' + id + '…', '');
    getModel(id).then(function () {
      if (mod.id === id) setNnStatus('Нейросеть модуля ' + id + ' готова · работает прямо в браузере, без интернета', 'ok');
    }).catch(function () {
      if (mod.id === id) setNnStatus('Не нашёл нейросеть models/m' + id + '. Работает проверка Gemini.', 'bad');
    });
  }

  // ---------- Режим: сравнение с эталоном / нейросеть ----------
  let mode = 'nn';   // сравнение с эталоном отключено: с телефоном в руке оно давало ложные рамки
  function applyMode() {
    document.querySelectorAll('#modePick .chip').forEach(function (c) { c.setAttribute('aria-pressed', String(c.dataset.mode === mode)); });
    $('refBtn').hidden = !(mode === 'cmp' && stream);
    $('modeHint').textContent = mode === 'cmp'
      ? 'Поставь телефон неподвижно над платой, нажми «Запомнить правильную сборку», потом вынь деталь — место отличия обведётся рамкой.'
      : 'Исследовательский режим: своя нейросеть (7 моделей Teachable Machine) угадывает тип ошибки по кадру.';
    if (nnStatus) nnStatus.hidden = mode !== 'nn';
    drawLiveMarks([]);
    nn.avg = null;
  }
  document.querySelectorAll('#modePick .chip').forEach(function (c) {
    c.addEventListener('click', function () { mode = c.dataset.mode; save('circuitai-mode2', mode); applyMode(); });
  });

  // ---------- Камера ----------
  const viewer = $('viewer'), video = $('video'), still = $('still'), stillImg = $('stillImg');
  const empty = $('viewerEmpty'), camBtn = $('camBtn'), liveBtn = $('liveBtn'), checkBtn = $('checkBtn'), geminiBtn = $('geminiBtn');
  const nnLive = $('nnLive');
  let stream = null, photoBlob = null, liveTimer = null;

  function showLive() {
    video.hidden = false; still.hidden = true; empty.hidden = true; liveBtn.hidden = true;
    viewer.classList.add('live');
    checkBtn.disabled = false; geminiBtn.disabled = false;
    checkBtn.textContent = 'Проверить схему';
    nn.avg = null;
    $('refBtn').hidden = mode !== 'cmp';
    startLive();
  }
  function showStill(src) {
    stillImg.src = src;
    $('marks').innerHTML = '';
    still.hidden = false; video.hidden = true; empty.hidden = true;
    viewer.classList.remove('live');
    liveBtn.hidden = !stream;
    checkBtn.disabled = false; geminiBtn.disabled = false;
    stopLive();
  }

  // Живой вердикт: ~4 раза в секунду, среднее по последним кадрам, чтобы надпись не прыгала
  function startLive() {
    stopLive();
    liveTimer = setInterval(async function () {
      if (nn.busy || !stream || video.hidden || !video.videoWidth) return;
      if (mode === 'cmp') {
        nnLive.hidden = false;
        if (cmp.capturing) { nnLive.textContent = 'Запоминаю эталон…'; nnLive.className = 'nn-live warn'; return; }
        if (!cmp.lo) { nnLive.textContent = 'Нажми «Запомнить правильную сборку»'; nnLive.className = 'nn-live'; drawLiveMarks([]); return; }
        compareFrame();
        drawLiveMarks(cmp.boxes);
        if (cmp.moved) { nnLive.textContent = 'Камера сдвинулась — запомни заново'; nnLive.className = 'nn-live warn'; }
        else if (cmp.boxes.length) { nnLive.textContent = 'Найдено отличие: ' + cmp.boxes.length; nnLive.className = 'nn-live bad'; }
        else { nnLive.textContent = 'Совпадает с эталоном'; nnLive.className = 'nn-live ok'; }
        return;
      }
      if (!nn.ready) return;
      nn.busy = true;
      try {
        const m = await getModel(mod.id);
        const probs = predictFrom(m, video, video.videoWidth, video.videoHeight);
        if (!nn.avg || nn.avg.length !== probs.length) nn.avg = probs;
        else nn.avg = nn.avg.map(function (a, i) { return a * 0.6 + probs[i] * 0.4; });
        const top = topOf(m, nn.avg);
        const pct = Math.round(top.p * 100);
        nnLive.hidden = false;
        if (top.p < MIN_CONF) { nnLive.textContent = 'Наведи ближе · ' + pct + ' %'; nnLive.className = 'nn-live warn'; }
        else if (top.label === 'ok') { nnLive.textContent = 'Правильно · ' + pct + ' %'; nnLive.className = 'nn-live ok'; }
        else { nnLive.textContent = (SHORT[top.label] || top.label) + ' · ' + pct + ' %'; nnLive.className = 'nn-live bad'; }
      } catch (e) {
        nnLive.hidden = true;
      } finally { nn.busy = false; }
    }, 250);
  }
  function stopLive() {
    if (liveTimer) clearInterval(liveTimer);
    liveTimer = null;
    if (nnLive) nnLive.hidden = true;
    drawLiveMarks([]);
  }

  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      $('timeInfo').textContent = 'Камера доступна только на сайте с адресом https:// или через Live Server. Пока загрузи фото.';
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
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
    stopLive();
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    video.srcObject = null;
    camBtn.textContent = 'Включить камеру';
    viewer.classList.remove('live');
    liveBtn.hidden = true;
    $('refBtn').hidden = true;
    cmp.lo = null;
    if (photoBlob) { video.hidden = true; still.hidden = false; }
    else { video.hidden = true; empty.hidden = false; checkBtn.disabled = true; geminiBtn.disabled = true; }
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
    // Небольшое JPEG-фото отправляем без пересжатия: так сервер узнаёт фото из демо-кэша
    if (f.type === 'image/jpeg' && f.size <= 1500000) photoBlob = f;
    else {
      try {
        const img = await fileToImage(f);
        photoBlob = await toJpeg(img, img.naturalWidth, img.naturalHeight, 1280, 0.85);
      } catch (e) { photoBlob = f; }
    }
    showStill(URL.createObjectURL(photoBlob));
    resetStages();
    $('timeInfo').textContent = 'Фото загружено. Нажми «Проверить схему».';
    this.value = '';
  });

  // ---------- Готовые фото для показа (папка demo_photos) ----------
  const DEMO_PHOTOS = {
    1: [["m1_1_01_etalon.jpg", "Правильная сборка"], ["m1_2_06_visyachiy_provod.jpg", "Висящий провод"], ["m1_3_04_net_rezistora.jpg", "Нет резистора"]],
    2: [["m2_1_01_etalon.jpg", "Правильная сборка"], ["m2_2_06_visyachiy_provod.jpg", "Висящий провод"], ["m2_3_07_trig_echo_pereputany.jpg", "Trig и Echo перепутаны"]],
    3: [["m3_1_01_etalon.jpg", "Правильная сборка"], ["m3_2_04_net_rezistora.jpg", "Нет резистора"]],
    4: [["m4_1_01_etalon.jpg", "Правильная сборка"], ["m4_2_06_visyachiy_provod.jpg", "Висящий провод"], ["m4_3_02_net_gnd.jpg", "Нет GND"]],
    5: [["m5_1_01_etalon.jpg", "Правильная сборка"]],
    6: [["m6_1_01_etalon.jpg", "Правильная сборка"], ["m6_2_06_visyachiy_provod.jpg", "Висящий провод"], ["m6_3_07_do_ne_v_tom_pine.jpg", "Датчик огня не в том пине"]],
    7: [["m7_1_01_etalon.jpg", "Правильная сборка"], ["m7_2_04_net_rezistora.jpg", "Нет резистора"]]
  };
  async function useDemo(file) {
    try {
      const r = await fetch('demo_photos/' + file);
      if (!r.ok) throw new Error('нет файла');
      const blob = await r.blob();
      if (stream) stopCamera();
      photoBlob = blob.type ? blob : new Blob([blob], { type: 'image/jpeg' });
      showStill(URL.createObjectURL(photoBlob));
      resetStages();
      $('timeInfo').textContent = 'Готовое фото загружено. Нажми «Проверить схему».';
    } catch (e) {
      $('timeInfo').textContent = 'Не удалось открыть готовое фото (' + file + ').';
    }
  }
  window.renderDemo = function () {
    const list = $('demoList');
    if (!list) return;
    list.innerHTML = '';
    const items = DEMO_PHOTOS[mod.id] || [];
    $('demoRow').hidden = !items.length;
    items.forEach(function (it) {
      const b = el('button', 'demo-item');
      b.type = 'button';
      b.title = it[1];
      const img = el('img');
      img.src = 'demo_photos/' + it[0];
      img.alt = it[1];
      img.loading = 'lazy';
      b.appendChild(img);
      b.appendChild(el('span', '', it[1]));
      b.addEventListener('click', function () { useDemo(it[0]); });
      list.appendChild(b);
    });
  };

  // ---------- Этапы ----------
  const stages = Array.from(document.querySelectorAll('#stages li'));
  function resetStages() { stages.forEach(function (s) { s.className = ''; }); }
  function stage(i, state) { if (stages[i]) stages[i].className = state; }

  // ---------- Итог ----------
  function drawMarks(marks, target) {
    const layer = target || $('marks');
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
    if (data.source === 'cmp') {
      if (data.status === 'ok') return { cls: 'ok', icon: '✓', title: 'Совпадает с правильной сборкой', sub: 'Сравнение с эталоном: отличий не найдено.' };
      if (data.status === 'error') return { cls: 'bad', icon: '!', title: 'Найдено отличие от правильной сборки', sub: 'Мест с изменениями: ' + data.marks.length + '. Смотри красные рамки на снимке.' };
      return { cls: 'warn', icon: '~', title: 'Камера сдвинулась', sub: 'Запомни правильную сборку заново, не двигая телефон.' };
    }
    if (data.source === 'nn') {
      const pct = Math.round((data.confidence || 0) * 100);
      if (data.status === 'ok') return { cls: 'ok', icon: '✓', title: 'Схема собрана верно', sub: 'Своя нейросеть Circuit AI уверена на ' + pct + ' %.' };
      if (data.status === 'error') return { cls: 'bad', icon: '!', title: SHORT[data.label] || 'Найдена ошибка', sub: 'Нейросеть нашла ошибку, уверенность ' + pct + ' %.' };
      return { cls: 'warn', icon: '~', title: 'Пересними ближе', sub: 'Нейросеть не уверена (' + pct + ' %).' };
    }
    if (data.status === 'no_circuit') return { cls: 'warn', icon: '?', title: 'На фото не видно схему', sub: 'Наведи камеру сверху на Arduino и макетную плату.' };
    if (data.errors && data.errors.length) return { cls: 'bad', icon: '!', title: 'Найдена ошибка подключения', sub: 'Ошибок: ' + data.errors.length + '. Разберись с ними ниже или спроси тьютора.' };
    if (data.status === 'unclear') return { cls: 'warn', icon: '~', title: 'Часть схемы не видно', sub: 'Ошибок не найдено, но некоторые места нужно проверить или переснять.' };
    return { cls: 'ok', icon: '✓', title: 'Схема собрана верно', sub: 'Детали, земля и пины на месте. Пройди список «Проверь сам» ниже.' };
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
      data.errors.forEach(function (err, i) {
        const card = el('div', 'issue');
        card.appendChild(el('b', '', err));
        card.appendChild(el('p', '', 'Как исправить: ' + ((data.fixes && data.fixes[i]) || tipFor(err))));
        const btn = el('button', 'btn btn-sm', 'Разобраться с тьютором');
        btn.type = 'button';
        btn.addEventListener('click', function () { Tutor.open('Помоги разобраться с ошибкой: ' + err); });
        card.appendChild(btn);
        wrap.appendChild(card);
      });
      box.appendChild(wrap);
    }
    const found = list(data.source === 'nn' ? 'Что увидела нейросеть' : 'Что ИИ распознал и подтвердил', data.found);
    if (found) box.appendChild(found);
    const unclear = list('Не удалось рассмотреть', data.unclear);
    if (unclear) box.appendChild(unclear);
    if (data.scores && data.scores.length) {
      const g = el('div', 'res-group');
      g.appendChild(el('h4', '', 'Как думает нейросеть (вероятности)'));
      data.scores.forEach(function (s) {
        const row = el('div', 'nn-bar');
        row.appendChild(el('span', 'nn-bar-name', s.name));
        const track = el('span', 'nn-bar-track');
        const fill = el('span', 'nn-bar-fill' + (s.label === 'ok' ? ' ok' : ''));
        fill.style.width = Math.max(1, Math.round(s.p * 100)) + '%';
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(el('span', 'nn-bar-pct', Math.round(s.p * 100) + ' %'));
        g.appendChild(row);
      });
      box.appendChild(g);
    }
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

  function showError(text, retry) {
    const box = $('result');
    $('resultCard').hidden = false;
    box.innerHTML = '';
    const vd = el('div', 'verdict warn');
    vd.appendChild(el('span', 'v-icon', '!'));
    const vt = el('div', '', 'Проверка не завершилась');
    vt.appendChild(el('small', '', text));
    vd.appendChild(vt);
    box.appendChild(vd);
    if (retry) {
      const again = el('button', 'btn btn-sm', 'Повторить');
      again.type = 'button';
      again.style.marginTop = '12px';
      again.addEventListener('click', retry);
      box.appendChild(again);
    }
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

  function finish(data, info) {
    drawMarks(data.marks);
    showResult(data);
    $('timeInfo').textContent = info;
    if (window.Tutor) { Tutor.setContext({ module: mod.id, defectResult: data }); Tutor.react(data); }
    stage(3, 'done');
    remember(data);
  }

  // ---------- Проверка своей нейросетью (главная) ----------
  async function runNnCheck() {
    resetStages();
    const liveProbs = (stream && !video.hidden && nn.avg) ? nn.avg.slice() : null;
    if (stream && !video.hidden) {
      photoBlob = await toJpeg(video, video.videoWidth, video.videoHeight, 1280, 0.85);
      showStill(URL.createObjectURL(photoBlob));
    }
    if (!photoBlob) return;
    stage(0, 'done'); stage(1, 'active');
    const t0 = performance.now();
    try {
      const m = await getModel(mod.id);
      let probs;
      if (liveProbs && liveProbs.length === m.labels.length) probs = liveProbs;   // среднее по живым кадрам — надёжнее одного снимка
      else {
        const img = await fileToImage(photoBlob);
        probs = predictFrom(m, img, img.naturalWidth, img.naturalHeight);
      }
      const data = nnResult(m, probs);
      stage(1, 'done'); stage(2, 'done');
      finish(data, 'Нейросеть ответила за ' + Math.max(1, Math.round(performance.now() - t0)) + ' мс, без интернета');
    } catch (e) {
      stage(1, 'fail');
      showError('Нейросеть этого модуля не загрузилась. Нажми «Подробная проверка Gemini» или выбери готовое фото.', runNnCheck);
    } finally {
      checkBtn.disabled = false;
      if (stream) checkBtn.textContent = 'Снова живая камера';
    }
  }

  // ---------- Подробная проверка через сервер (Gemini) — запасной путь ----------
  async function runGeminiCheck() {
    if (!mod.aiReady) { showError('Для этого модуля проверка Gemini пока не настроена. Используй свою нейросеть — кнопка «Проверить схему».'); return; }
    resetStages();
    if (stream && !video.hidden) {
      photoBlob = await toJpeg(video, video.videoWidth, video.videoHeight, 1280, 0.85);
      showStill(URL.createObjectURL(photoBlob));
    }
    if (!photoBlob) return;
    stage(0, 'done');
    geminiBtn.disabled = true; checkBtn.disabled = true;
    viewer.classList.add('scanning');
    if (window.Tutor) Tutor.setEmotion('think');
    const info = $('timeInfo');
    const started = Date.now();
    const timer = setInterval(function () { info.textContent = 'Gemini проверяет… ' + Math.round((Date.now() - started) / 1000) + ' с'; }, 300);
    const controller = new AbortController();
    const stopper = setTimeout(function () { controller.abort(); }, 90000);
    try {
      const form = new FormData();
      form.append('photo', photoBlob, 'photo.jpg');
      form.append('module', mod.id);
      stage(1, 'active');
      const r = await fetch(API + '/check', { method: 'POST', body: form, signal: controller.signal });
      const data = await r.json();
      if (!r.ok) throw new Error(data.message || 'Сервер не смог проверить фото. Нажми «Повторить».');
      stage(1, 'done'); stage(2, 'done');
      clearInterval(timer);
      finish(data, data.cached ? 'Это фото уже проверяли — результат сохранён' : 'Gemini проверил за ' + data.seconds + ' с');
    } catch (e) {
      stage(1, 'fail');
      info.textContent = '';
      showError(e.name === 'AbortError' ? 'Проверка заняла слишком долго. Нажми «Повторить».'
        : (e.message && e.message !== 'Failed to fetch' ? e.message : 'Сервер не отвечает. Своя нейросеть работает и без него — кнопка «Проверить схему».'), runGeminiCheck);
      if (window.Tutor) Tutor.setEmotion('alert', 4000);
    } finally {
      clearInterval(timer);
      clearTimeout(stopper);
      viewer.classList.remove('scanning');
      geminiBtn.disabled = false; checkBtn.disabled = false;
    }
  }

  async function runCmpCheck() {
    resetStages();
    if (!stream) { showError('Сравнение с эталоном работает с живой камерой. Включи камеру или переключись на режим «Нейросеть».'); return; }
    if (!cmp.lo) { showError('Сначала наведи камеру на правильную плату и нажми «Запомнить правильную сборку».'); return; }
    stage(0, 'done'); stage(1, 'active');
    const data = cmpResult();
    photoBlob = await toJpeg(video, video.videoWidth, video.videoHeight, 1280, 0.85);
    showStill(URL.createObjectURL(photoBlob));
    stage(1, 'done'); stage(2, 'done');
    finish(data, 'Сравнение с эталоном · без интернета');
    checkBtn.disabled = false;
    checkBtn.textContent = 'Снова живая камера';
  }

  checkBtn.addEventListener('click', function () {
    if (stream && !still.hidden) { showLive(); return; }
    checkBtn.disabled = true;
    // Живая камера + режим сравнения → сравнение с эталоном.
    // Готовое или загруженное фото (камеры нет) → своя нейросеть, без лишних вопросов.
    if (mode === 'cmp' && stream && !video.hidden) runCmpCheck(); else runNnCheck();
  });
  $('refBtn').addEventListener('click', function () {
    if (stream && !still.hidden) showLive();
    captureReference();
  });
  geminiBtn.addEventListener('click', function () {
    if (stream && !still.hidden) showLive();
    runGeminiCheck();
  });

  renderHistory();
  window.renderDemo();
  prepareModel();
  applyMode();
  // Список готовых фото делает скрипт server/make_maket_demo.py (demo_photos/list.json)
  fetch('demo_photos/list.json', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (list) {
      if (!list) return;
      Object.keys(DEMO_PHOTOS).forEach(function (k) { delete DEMO_PHOTOS[k]; });
      Object.keys(list).forEach(function (k) { DEMO_PHOTOS[k] = list[k]; });
      window.renderDemo();
    })
    .catch(function () {});
})();
