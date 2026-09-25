// Автотесты анализа звука: синтетические удары по шнуру.
// Запуск: node tests/dsp.test.js [путь к index.html или dsp.js]
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const src = fs.readFileSync(process.argv[2] || path.join(__dirname, '..', 'index.html'), 'utf8');
const m = src.match(/\/\* DSP-BEGIN \*\/([\s\S]*?)\/\* DSP-END \*\//);
if (!m) throw new Error('DSP block not found');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(m[1] + '\nthis.api={pitchAnalyze,analyzeSamples,judgeTap,TapEngine,toneLevel,computeRMS,DECAY_DB,thrOf,suggestThresholds,DECAY_REL_MIN,PURITY_REL_MIN,PURITY_ABS_MIN};', ctx);
const D = ctx.api;

// ---------- синтез ----------
let seed = 12345;
function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
function gauss() { let u = 0; for (let i = 0; i < 6; i++) u += rnd(); return (u - 3) / Math.sqrt(0.5); }

const SR = 48000;
// опции: f0, tau (с), amp, harm (массив амплитуд гармоник), evenWeak, key (кольцо ключа), noise (σ), pre (с), len (с),
// inharm: [множители частот] для «дребезга», click: амплитуда щелчка
function tap(o) {
  const sr = o.sr || SR;
  const len = Math.round((o.len || 2.8) * sr), pre = Math.round((o.pre == null ? 0.4 : o.pre) * sr);
  const x = new Float32Array(len);
  const amp = o.amp == null ? 0.3 : o.amp;
  const harm = o.harm || [1, 0.08, 0.35, 0.05, 0.15, 0.03, 0.07];
  const partials = [];
  if (o.inharm) {
    o.inharm.forEach((k, i) => partials.push({ f: o.f0 * k, a: amp * (o.inharmAmp ? o.inharmAmp[i] : 1 / (i + 1)), tau: o.tau / Math.sqrt(i + 1) }));
  } else {
    harm.forEach((a, i) => {
      const k = i + 1, B = 1e-4;
      partials.push({ f: o.f0 * k * Math.sqrt(1 + B * k * k), a: amp * a, tau: o.tau / Math.sqrt(k) });
    });
  }
  if (o.key !== false) {
    partials.push({ f: 3730, a: amp * (o.key || 0.5), tau: 0.06 });
    partials.push({ f: 4610, a: amp * (o.key || 0.5) * 0.6, tau: 0.04 });
  }
  const ph = partials.map(() => rnd() * 2 * Math.PI);
  for (let n = pre; n < len; n++) {
    const t = (n - pre) / sr;
    let v = 0;
    for (let j = 0; j < partials.length; j++) {
      const p = partials[j];
      if (p.f >= sr / 2) continue;
      v += p.a * Math.exp(-t / p.tau) * Math.sin(2 * Math.PI * p.f * t + ph[j]);
    }
    const click = o.click == null ? 0.6 : o.click;
    if (t < 0.003) v += click * amp * gauss() * (1 - t / 0.003);
    x[n] = v;
  }
  if (o.buzz) {
    // дребезг: нерегулярные короткие касания шнура (частота касаний o.rate в секунду)
    let t = 0.005;
    while (t < o.tau * 3) {
      const n0 = pre + Math.round(t * sr), A = o.buzz * amp * Math.exp(-t / o.tau), w = Math.round(0.0015 * sr);
      for (let j = 0; j < w && n0 + j < len; j++) x[n0 + j] += A * gauss() * (1 - j / w);
      t += (1 / (o.rate || 400)) * (0.5 + rnd());
    }
  }
  const sigma = o.noise == null ? 0.002 : o.noise;
  for (let n = 0; n < len; n++) x[n] += sigma * gauss();
  return x;
}

// ---------- мини-фреймворк ----------
let pass = 0, fail = 0;
function check(name, cond, info) {
  if (cond) { pass++; console.log('  ok   ' + name + (info ? '  ' + info : '')); }
  else { fail++; console.log('  FAIL ' + name + (info ? '  ' + info : '')); }
}
const pct = (a, b) => ((a / b - 1) * 100);

// ---------- 1. частота: широкий диапазон записи эталона (45–1500 Гц) ----------
console.log('1. Частота по записи эталона, поиск 45–1500 Гц');
for (const f0 of [55, 70, 82.4, 98, 123, 147, 196, 262, 330, 440, 587]) {
  const x = tap({ f0, tau: 0.45 });
  const r = D.analyzeSamples(x, SR, null);
  const e = r.freq ? pct(r.freq, f0) : NaN;
  check(`f0=${f0} Гц`, r.freq && Math.abs(e) < 1, `→ ${r.freq ? r.freq.toFixed(2) : 'null'} Гц (${e.toFixed(2)}%), чистота ${(r.purity * 100).toFixed(0)}%`);
}

// ---------- 2. защита от ошибки на октаву: все гармоники равной силы ----------
console.log('2. Ошибка на октаву: сильные гармоники');
for (const f0 of [65, 110, 180, 300]) {
  const x = tap({ f0, tau: 0.5, harm: [1, 1, 1, 1, 1, 1], key: 0.2 });
  const r = D.analyzeSamples(x, SR, null);
  const e = r.freq ? pct(r.freq, f0) : NaN;
  check(`f0=${f0} Гц, гармоники 1:1:1:1:1:1`, r.freq && Math.abs(e) < 1, `→ ${r.freq ? r.freq.toFixed(2) : 'null'} Гц`);
}

// ---------- 3. затухание ----------
console.log('3. Время затухания (спад на 20 дБ), ожидание ≈ τ·ln10');
for (const tau of [0.08, 0.15, 0.3, 0.6]) {
  const f0 = 160;
  const x = tap({ f0, tau, len: 3 });
  const r = D.analyzeSamples(x, SR, [f0 * 0.55, f0 * 1.6]);
  const expect = tau * Math.log(10) * 1000;
  const e = r.decayMs != null ? pct(r.decayMs, expect) : NaN;
  check(`τ=${tau} с`, r.decayState === 'ok' && Math.abs(e) < 20, `→ ${r.decayMs && r.decayMs.toFixed(0)} мс при ожидаемых ${expect.toFixed(0)} мс (${e.toFixed(1)}%), состояние ${r.decayState}`);
}
{
  const x = tap({ f0: 160, tau: 2.0, len: 3 });
  const r = D.analyzeSamples(x, SR, [88, 256]);
  check('очень долгий тон → long', r.decayState === 'long', `→ ${r.decayState}, ${r.decayMs && r.decayMs.toFixed(0)} мс`);
}

// ---------- 4. чистота тона ----------
console.log('4. Чистота тона');
const clean = D.analyzeSamples(tap({ f0: 150, tau: 0.4 }), SR, null);
check('чистый удар: чистота ≥ 80%', clean.purity >= 0.8, `→ ${(clean.purity * 100).toFixed(0)}%`);
const noisyClean = D.analyzeSamples(tap({ f0: 150, tau: 0.4, noise: 0.01 }), SR, null);
check('чистый удар в шуме: чистота ≥ 60%', noisyClean.purity >= 0.6, `→ ${(noisyClean.purity * 100).toFixed(0)}%`);
for (const [buzz, rate] of [[1, 400], [2, 150], [2, 400], [4, 400]]) {
  const rt = D.analyzeSamples(tap({ f0: 150, tau: 0.35, buzz, rate }), SR, [82, 240]);
  check(`дребезг ×${buzz}, ${rate} касаний/с: чистота ниже 75% от чистого удара`, !rt.freq || rt.purity < 0.75 * clean.purity, `→ ${rt.freq ? rt.freq.toFixed(1) + ' Гц' : 'тон не найден'}, чистота ${(rt.purity * 100).toFixed(0)}%`);
}
const thud = D.analyzeSamples(tap({ f0: 150, tau: 0.012, click: 3, noise: 0.004 }), SR, null);
check('глухой удар (τ=12 мс): тон не найден или низкая чистота/быстрое затухание', !thud.freq || thud.purity < 0.4 || (thud.decayMs != null && thud.decayMs < 60), `→ ${thud.freq ? thud.freq.toFixed(1) + ' Гц' : 'тон не найден'}, чистота ${(thud.purity * 100).toFixed(0)}%, затухание ${thud.decayMs && thud.decayMs.toFixed(0)} мс`);

{
  // запись началась на «хвосте» прошлого удара, затем полный удар — берётся полный удар
  const tail = tap({ f0: 150, tau: 0.4, pre: 0, len: 0.6 }).subarray(Math.round(0.25 * SR));
  const full = tap({ f0: 150, tau: 0.4, pre: 0.5, len: 2.6 });
  const x = new Float32Array(tail.length + full.length); x.set(tail); x.set(full, tail.length);
  const r = D.analyzeSamples(x, SR, null), expect = 0.4 * Math.log(10) * 1000;
  check('запись с хвостом прошлого удара: берётся полный удар', r.freq && Math.abs(pct(r.freq, 150)) < 1 && Math.abs(pct(r.decayMs, expect)) < 10, `→ ${r.freq && r.freq.toFixed(1)} Гц, затухание ${r.decayMs && r.decayMs.toFixed(0)} мс (ожидалось ≈${expect.toFixed(0)})`);
}
{
  // частота дискретизации 44,1 кГц
  const r = D.analyzeSamples(tap({ f0: 110, tau: 0.3, sr: 44100 }), 44100, null);
  check('44,1 кГц: частота и затухание', r.freq && Math.abs(pct(r.freq, 110)) < 1 && Math.abs(pct(r.decayMs, 0.3 * Math.log(10) * 1000)) < 10, `→ ${r.freq && r.freq.toFixed(2)} Гц, ${r.decayMs && r.decayMs.toFixed(0)} мс`);
}

// ---------- 5. вердикты ----------
console.log('5. Вердикты');
const ref = { target: 150, tol: 3, refPurity: 0.92, refDecay: 800, refDecayState: 'ok' };
const V = (m) => D.judgeTap(Object.assign({ purity: 0.9, decayMs: 780, decayState: 'ok' }, m), ref);
check('норма', V({ freq: 151 }) === 'tuned');
check('слабо', V({ freq: 144 }) === 'loose');
check('туго', V({ freq: 156 }) === 'tight');
check('быстро затухает', V({ freq: 150, decayMs: 400 }) === 'fast');
check('дребезг', V({ freq: 150, purity: 0.5 }) === 'rattle');
check('глухой звук', V({ freq: 150, purity: 0.3, decayMs: 200 }) === 'dull');
check('долгий тон — не брак', V({ freq: 150, decayMs: 2500, decayState: 'long' }) === 'tuned');
check('затухание в шуме не судим', V({ freq: 150, decayMs: 100, decayState: 'noisy' }) === 'tuned');
check('старый эталон без затухания', D.judgeTap({ freq: 150, purity: 0.9, decayMs: 100, decayState: 'ok' }, { target: 150, tol: 3 }) === 'tuned');
check('старая запись журнала без чистоты', D.judgeTap({ freq: 150 }, ref) === 'tuned');

// ---------- 6. живой режим: поток с микрофона кадрами по ~16,7 мс ----------
console.log('6. Живой режим (TapEngine) против записи эталона');
function stream(x, cfg, range, target) {
  const eng = new D.TapEngine(SR), hop = 800, BUF = 4096, events = [];
  const buf = new Float32Array(BUF);
  for (let n = 0; n + hop <= x.length; n += hop) {
    buf.copyWithin(0, hop);
    buf.set(x.subarray(n, n + hop), BUF - hop);
    const ev = eng.process(buf, (n + hop) / SR * 1000, cfg, range, target);
    if (ev && ev.type !== 'decay-start') events.push(ev);
  }
  return events;
}
const CFG = { spike: 0.035, quiet: 0.014 };
for (const [f0, tau] of [[82.4, 0.5], [150, 0.35], [150, 0.12], [260, 0.25]]) {
  const refRec = D.analyzeSamples(tap({ f0, tau, len: 3 }), SR, null);
  const live = stream(tap({ f0, tau, len: 3 }), CFG, [f0 * 0.55, f0 * 1.6], f0);
  const ev = live.find(e => e.type === 'tap');
  const ok = ev && Math.abs(pct(ev.freq, f0)) < 1 && ev.decayState === 'ok' && Math.abs(pct(ev.decayMs, refRec.decayMs)) < 15;
  check(`f0=${f0}, τ=${tau}: живой замер совпадает с эталоном`, ok,
    ev ? `живой ${ev.freq.toFixed(1)} Гц / ${ev.decayMs && ev.decayMs.toFixed(0)} мс / ${(ev.purity * 100).toFixed(0)}%; запись ${refRec.freq.toFixed(1)} Гц / ${refRec.decayMs.toFixed(0)} мс / ${(refRec.purity * 100).toFixed(0)}%` : 'нет события');
}
{
  // эталон τ=0.4, проверка: тот же тон, но τ=0.15 → «быстро затухает»
  const r = D.analyzeSamples(tap({ f0: 150, tau: 0.4, len: 3 }), SR, null);
  const refX = { target: r.freq, tol: 3, refPurity: r.purity, refDecay: r.decayMs, refDecayState: r.decayState };
  const same = stream(tap({ f0: 150, tau: 0.4, len: 3 }), CFG, [82, 240], 150).find(e => e.type === 'tap');
  const fast = stream(tap({ f0: 150, tau: 0.15, len: 3 }), CFG, [82, 240], 150).find(e => e.type === 'tap');
  const loose = stream(tap({ f0: 141, tau: 0.4, len: 3 }), CFG, [82, 240], 150).find(e => e.type === 'tap');
  check('тот же удар → норма', same && D.judgeTap(same, refX) === 'tuned', same && D.judgeTap(same, refX));
  check('затухание в 2,7 раза короче → брак «быстро затухает»', fast && D.judgeTap(fast, refX) === 'fast', fast && D.judgeTap(fast, refX));
  check('частота на 6% ниже → «слабо»', loose && D.judgeTap(loose, refX) === 'loose', loose && D.judgeTap(loose, refX));
  const rat = stream(tap({ f0: 150, tau: 0.3, len: 3, inharm: [1, 1.41, 1.83, 2.37, 2.92, 3.61], inharmAmp: [1, 0.9, 0.8, 0.7, 0.6, 0.5] }), CFG, [82, 240], 150);
  const re = rat.find(e => e.type === 'tap');
  const bz = stream(tap({ f0: 150, tau: 0.4, len: 3, buzz: 2, rate: 400 }), CFG, [82, 240], 150).find(e => e.type === 'tap');
  check('дребезг (касания шнура) в живом режиме → брак «дребезг»', bz && ['rattle', 'dull'].includes(D.judgeTap(bz, refX)), bz && (D.judgeTap(bz, refX) + ', чистота ' + (bz.purity * 100).toFixed(0) + '%'));
  check('негармонические призвуки в живом режиме → брак или «тон не определился»', (re && ['rattle', 'dull'].includes(D.judgeTap(re, refX))) || rat.some(e => e.type === 'notone'), re ? D.judgeTap(re, refX) + ', чистота ' + (re.purity * 100).toFixed(0) + '%' : 'notone');
  // два удара подряд
  const a = tap({ f0: 150, tau: 0.4, len: 1.2 }), b = tap({ f0: 150, tau: 0.4, len: 2.5, pre: 0.05 });
  const two = new Float32Array(a.length + b.length); two.set(a); two.set(b, a.length);
  const evs = stream(two, CFG, [82, 240], 150).filter(e => e.type === 'tap');
  check('два удара подряд → два замера', evs.length === 2, evs.map(e => e.decayState).join(', '));
  // тишина и шум без удара
  const quiet = new Float32Array(SR * 2); for (let i = 0; i < quiet.length; i++) quiet[i] = 0.004 * gauss();
  check('тишина → нет событий', stream(quiet, CFG, [82, 240], 150).length === 0);
}

// ---------- 7. режим «Про»: глухой удар, свои пороги, подбор порогов ----------
console.log('7. Режим «Про»: «нет отклика», пороги брака, подбор порогов');
{
  // глухой удар без тона: шумовой щелчок 15 мс
  const x = new Float32Array(SR * 3), pre = Math.round(0.4 * SR);
  for (let n = pre; n < x.length; n++) x[n] = 0.25 * gauss() * Math.exp(-(n - pre) / SR / 0.015);
  for (let n = 0; n < x.length; n++) x[n] += 0.002 * gauss();
  const evs = stream(x, CFG, [82, 240], 150);
  check('глухой удар без тона → «нет отклика», замера нет', evs.some(e => e.type === 'notone') && !evs.some(e => e.type === 'tap'), evs.map(e => e.type).join(', '));

  const ref = { target: 150, tol: 3, refPurity: 0.95, refDecay: 800, refDecayState: 'ok' };
  const m = { freq: 150, purity: 0.9, decayMs: 440, decayState: 'ok' };          // затухание 55% эталона
  check('исходные пороги: затухание 55% эталона → «быстро затухает»', D.judgeTap(m, ref) === 'fast');
  check('свой порог затухания 50% → норма', D.judgeTap(m, Object.assign({ thr: { decayRel: 0.5 } }, ref)) === 'tuned');
  check('свой порог чистоты 99% эталона → «дребезг»', D.judgeTap({ freq: 150, purity: 0.9, decayMs: 800, decayState: 'ok' }, Object.assign({ thr: { purityRel: 0.99 } }, ref)) === 'rattle');
  const t = D.thrOf({ thr: { purityRel: 0.6 } });
  check('недостающие пороги берутся исходными', t.purityRel === 0.6 && t.decayRel === D.DECAY_REL_MIN && t.purityAbs === D.PURITY_ABS_MIN, JSON.stringify(t));
  check('без эталона и порогов — исходные пороги', JSON.stringify(D.thrOf(null)) === JSON.stringify({ decayRel: D.DECAY_REL_MIN, purityRel: D.PURITY_REL_MIN, purityAbs: D.PURITY_ABS_MIN }));

  // подбор: 12 годных (±1,5% по частоте, затухание 70–110% эталона) и 6 недотянутых (−6%, затухание 35–45%)
  const good = [], bad = [];
  for (let i = 0; i < 12; i++) good.push({ label: 'good', freq: 150 * (1 + (i % 7 - 3) * 0.005), purity: 0.86 + 0.01 * (i % 8), decayMs: 800 * (0.7 + 0.04 * (i % 11)), decayState: 'ok' });
  for (let i = 0; i < 6; i++) bad.push({ label: 'bad', freq: 141 + i * 0.3, purity: 0.9, decayMs: 800 * (0.35 + 0.02 * i), decayState: 'ok' });
  const s = D.suggestThresholds(good.concat(bad), ref);
  check('подбор: все годные проходят', s && s.goodPass === s.goodN && s.goodN === 12, s && `${s.goodPass}/${s.goodN}`);
  check('подбор: все недотянутые выявлены', s && s.badCaught === s.badN && s.badN === 6, s && `${s.badCaught}/${s.badN}`);
  check('подбор: допуск и пороги в разумных пределах', s && s.tol >= 2 && s.tol <= 15 && s.decayRel >= 0.3 && s.decayRel <= 0.95 && s.purityRel >= 0.3 && s.purityRel <= 0.98 && s.purityAbs >= 0.2 && s.purityAbs <= 0.4,
    s && `допуск ±${s.tol}%, затухание ≥${s.decayRel}, чистота ≥${s.purityRel} и ≥${s.purityAbs}`);
  check('подбор: порог затухания ниже самого короткого годного', s && s.decayRel < 0.7, s && s.decayRel);
  check('подбор: меньше трёх годных — рекомендации нет', D.suggestThresholds(good.slice(0, 2).concat(bad), ref) === null);
  check('подбор: без эталона — рекомендации нет', D.suggestThresholds(good, { target: null }) === null);
  // эталон без затухания (записан в 2.1): порог затухания остаётся исходным
  const s2 = D.suggestThresholds(good, { target: 150, tol: 3, refPurity: 0.95 });
  check('эталон без затухания — порог затухания исходный', s2 && s2.decayRel === D.DECAY_REL_MIN, s2 && s2.decayRel);
}

console.log(`\nИтого: ${pass} пройдено, ${fail} не пройдено`);
process.exit(fail ? 1 : 0);
