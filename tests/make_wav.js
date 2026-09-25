// Синтетические удары для E2E-проверки в Chromium (поддельный микрофон)
const fs = require('fs');
let seed = 99;
function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
function gauss() { let u = 0; for (let i = 0; i < 6; i++) u += rnd(); return (u - 3) / Math.sqrt(0.5); }
const SR = 48000;
function tap(o) {
  const len = Math.round(o.len * SR), pre = Math.round(o.pre * SR), x = new Float32Array(len), amp = 0.3;
  const harm = [1, 0.08, 0.35, 0.05, 0.15, 0.03, 0.07];
  const parts = harm.map((a, i) => ({ f: o.f0 * (i + 1) * Math.sqrt(1 + 1e-4 * (i + 1) ** 2), a: amp * a, tau: o.tau / Math.sqrt(i + 1) }));
  parts.push({ f: 3730, a: amp * 0.5, tau: 0.06 }, { f: 4610, a: amp * 0.3, tau: 0.04 });
  for (let n = pre; n < len; n++) {
    const t = (n - pre) / SR; let v = 0;
    for (const p of parts) v += p.a * Math.exp(-t / p.tau) * Math.sin(2 * Math.PI * p.f * t);
    if (t < 0.003) v += 0.18 * gauss() * (1 - t / 0.003);
    x[n] = v;
  }
  if (o.buzz) {
    let t = 0.005;
    while (t < o.tau * 3) {
      const n0 = pre + Math.round(t * SR), A = o.buzz * amp * Math.exp(-t / o.tau), w = Math.round(0.0015 * SR);
      for (let j = 0; j < w && n0 + j < len; j++) x[n0 + j] += A * gauss() * (1 - j / w);
      t += (1 / 400) * (0.5 + rnd());
    }
  }
  for (let n = 0; n < len; n++) x[n] += 0.002 * gauss();
  return x;
}
function wav(x, file) {
  const b = Buffer.alloc(44 + x.length * 2);
  b.write('RIFF', 0); b.writeUInt32LE(36 + x.length * 2, 4); b.write('WAVE', 8); b.write('fmt ', 12);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(SR, 24); b.writeUInt32LE(SR * 2, 28);
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(x.length * 2, 40);
  for (let i = 0; i < x.length; i++) b.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(x[i] * 32767))), 44 + i * 2);
  fs.writeFileSync(file, b);
}
// глухой удар без тона: короткий шумовой щелчок — приложение должно сообщить «нет отклика»
function thud(o) {
  const len = Math.round(o.len * SR), pre = Math.round(o.pre * SR), x = new Float32Array(len);
  for (let n = pre; n < len; n++) { const t = (n - pre) / SR; x[n] = 0.25 * gauss() * Math.exp(-t / 0.015); }
  for (let n = 0; n < len; n++) x[n] += 0.002 * gauss();
  return x;
}
// два удара подряд: второй приходится на затухание первого — «проверка прервана»
function double(o) {
  const a = tap(o), b = tap(Object.assign({}, o, { pre: o.pre + o.gap }));
  for (let n = 0; n < a.length; n++) a[n] += b[n];
  return a;
}
const D = __dirname + '/wav/';
fs.mkdirSync(D, { recursive: true });
wav(tap({ f0: 150, tau: 0.40, pre: 0.5, len: 3.0 }), D + 'ok.wav');
wav(tap({ f0: 150, tau: 0.12, pre: 0.5, len: 3.0 }), D + 'fast.wav');
wav(tap({ f0: 160, tau: 0.40, pre: 0.5, len: 3.0 }), D + 'tight.wav');
wav(tap({ f0: 142, tau: 0.40, pre: 0.5, len: 3.0 }), D + 'loose.wav');
wav(tap({ f0: 150, tau: 0.40, pre: 0.5, len: 3.0, buzz: 2 }), D + 'buzz.wav');
wav(thud({ pre: 0.5, len: 3.0 }), D + 'thud.wav');
wav(double({ f0: 150, tau: 0.40, pre: 0.5, len: 3.0, gap: 0.6 }), D + 'double.wav');
console.log('ok');
