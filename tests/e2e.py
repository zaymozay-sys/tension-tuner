"""E2E-проверка в Chromium с поддельным микрофоном (WAV с синтетическим ударом)."""
import os, re, sys, json, time, subprocess, threading
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
if not os.path.exists(os.path.join(OUT, 'index.html')):
    OUT = os.path.join(HERE, '..')  # корень репозитория
PORT = 8765
WAV = os.path.join(HERE, 'wav')
BASE = f'http://localhost:{PORT}/'

import atexit
srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '-d', OUT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(srv.terminate)
time.sleep(0.8)
results = []
def check(name, cond, info=''):
    results.append(bool(cond))
    print(('  ok   ' if cond else '  FAIL ') + name + ('  ' + str(info) if info else ''))

def launch(p, wav):
    return p.chromium.launch(args=[
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
        f'--use-file-for-fake-audio-capture={os.path.join(WAV, wav)}',
        '--autoplay-policy=no-user-gesture-required'])

def new_page(browser, storage=None, locale='ru-RU'):
    ctx = browser.new_context(locale=locale, viewport={'width': 390, 'height': 844}, storage_state=storage,
                              permissions=['microphone'], accept_downloads=True)
    page = ctx.new_page()
    errs = []
    page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errs.append(str(e)))
    return ctx, page, errs

def listen_until(page, n_entries, timeout=15):
    page.click('#btnListen')
    t0 = time.time()
    while time.time() - t0 < timeout:
        n = page.evaluate('(() => { const s = window.__tt.state; const z = s.sizes.find(x => x.id === s.selectedSizeId); return z && z.log ? z.log.length : 0; })()')
        if n >= n_entries: break
        time.sleep(0.25)
    time.sleep(0.3)
    txt = page.inner_text('#verdictBox')
    log = page.evaluate('(() => { const s = window.__tt.state; const z = s.sizes.find(x => x.id === s.selectedSizeId); return z.log; })()')
    page.click('#btnStop')
    return txt, log

with sync_playwright() as p:
    # ---------- 1. эталон + норма ----------
    print('1. Запись эталона и проверка «норма» (ok.wav, 150 Гц, τ=0,4 с)')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b)
    page.goto(BASE + 'index.html')
    page.wait_for_selector('#main')
    check('заголовок по-русски', page.title() == 'Натяжка — тюнер подвеса картин', page.title())
    page.click('.nav-btn[data-view="sizes"]')
    page.click('.slot[data-slot="40×60 см"]')
    page.click('#btnStartRec')
    page.wait_for_selector('#btnSaveRec', timeout=15000)
    rec_txt = page.inner_text('.rec-card')
    check('эталон: частота определена', 'Определено: 15' in rec_txt or 'Определено: 14' in rec_txt, rec_txt.split('\n')[0])
    check('эталон: затухание и чистота показаны', 'Затухание:' in rec_txt and 'чистота тона' in rec_txt, [l for l in rec_txt.split('\n') if 'Затухание' in l])
    page.click('#btnSaveRec')
    size = page.evaluate('window.__tt.state.sizes[0]')
    check('эталон сохранён с затуханием', size.get('refDecayState') in ('ok', 'long') and size.get('refDecay'), f"target={size.get('target'):.1f} refDecay={size.get('refDecay')} state={size.get('refDecayState')} purity={size.get('refPurity')}")
    txt, log = listen_until(page, 2)
    check('вердикт «Натяжение в норме»', 'Натяжение в норме' in txt, txt)
    check('в журнале есть затухание и чистота', log and log[0].get('decayMs') and log[0].get('purity') is not None,
          [(round(e['freq'], 1), round(e.get('decayMs') or 0), round((e.get('purity') or 0) * 100), e.get('verdict')) for e in log[:3]])
    body = page.inner_text('#main')
    check('плитки «затухание» и «чистота тона»', 'затухание' in body and 'чистота тона' in body)
    # CSV
    with page.expect_download() as dl:
        page.click('#exportCsvTuner')
    path = dl.value.path()
    csv = open(path, encoding='utf-8-sig').read()
    check('CSV: имя файла', dl.value.suggested_filename.startswith('natyazhka-zhurnal-'), dl.value.suggested_filename)
    check('CSV: заголовок и строки', csv.startswith('Дата;Время;Размер;Частота, Гц;Эталон, Гц') and ';150,0;' in csv and csv.count('\n') >= 2 and ';норма' in csv, csv.splitlines()[:2])
    storage = ctx.storage_state()
    check('нет ошибок в консоли', not errs, errs[:3])
    page.screenshot(path=os.path.join(HERE, 'e2e_ok.png'), full_page=True)
    b.close()

    # ---------- 2–4. брак и отклонения ----------
    for wav, expect, label in [('fast.wav', 'Брак: звук быстро затухает', 'быстро затухает'),
                               ('buzz.wav', 'Брак: дребезг', 'дребезг'),
                               ('tight.wav', 'Слишком туго', 'туго (160 Гц)'),
                               ('loose.wav', 'Подтяните сильнее', 'слабо (142 Гц)')]:
        print(f'— {label}: {wav}')
        b = launch(p, wav)
        ctx, page, errs = new_page(b, storage)
        page.goto(BASE + 'index.html')
        page.wait_for_selector('#btnListen')
        n0 = len(page.evaluate('window.__tt.state.sizes[0].log || []'))
        txt, log = listen_until(page, n0 + 2)
        e = log[0]
        check(f'вердикт «{expect}»', expect in txt, f"{txt} | {e['freq']:.1f} Гц, затухание {e.get('decayMs') and round(e['decayMs'])} мс, чистота {round((e.get('purity') or 0)*100)}%")
        check('нет ошибок в консоли', not errs, errs[:3])
        page.screenshot(path=os.path.join(HERE, f'e2e_{wav[:-4]}.png'), full_page=True)
        b.close()

    # ---------- 5. английский интерфейс ----------
    print('5. Английский интерфейс (?lang=en)')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b, storage, locale='en-US')
    page.set_viewport_size({'width': 1200, 'height': 900})
    page.goto(BASE + 'index.html?lang=en')
    page.wait_for_selector('#main')
    check('title EN', page.title().startswith('TapTension'), page.title())
    vis = page.evaluate('document.body.innerText')
    cyr = sorted(set(re.findall(r'[^\s]*[А-Яа-яЁё][^\s]*', vis)))
    check('нет русского текста, кроме «Русский»', cyr == ['Русский'], cyr[:10])
    page.click('.nav-btn[data-view="sizes"]')
    vis = page.evaluate('document.body.innerText')
    check('слоты «40×60 cm»', '40×60 cm' in vis)
    with page.expect_download() as dl:
        page.click('#btnExportCsv')
    csv = open(dl.value.path(), encoding='utf-8-sig').read()
    check('CSV EN', csv.startswith('Date,Time,Size,"Frequency, Hz"') and ',150.0,' in csv, csv.splitlines()[:2])
    page.click('#aboutBtnDesktop')
    about = page.inner_text('#drawerBody')
    check('About EN: patent + version', '2867038' in about and 'Version 2.4' in about, about[:80])
    page.keyboard.press('Escape')
    # переключение обратно на русский
    page.click('#drawerClose')
    page.click('.rail .lang-btn[data-lang="ru"]')
    page.wait_for_load_state('load')
    time.sleep(0.5)
    check('переключатель языка → русский', page.title() == 'Натяжка — тюнер подвеса картин', page.title())
    check('нет ошибок в консоли', not errs, errs[:3])
    b.close()

    # ---------- 6. миграция эталона 2.2 ----------
    print('6. Эталон из версии 2.2 (без затухания) досчитывается из записи')
    b = launch(p, 'ok.wav')
    st = json.loads(json.dumps(storage))
    for o in st['origins']:
        for item in o['localStorage']:
            if item['name'] == 'canvas_tension_v2':
                data = json.loads(item['value'])
                s0 = data['sizes'][0]
                for k in ('refDecay', 'refDecayState', 'refPurity'): s0.pop(k, None)
                s0['log'] = [{'freq': 150.2, 'ts': 1758000000000, 'confidence': 0.9}]
                item['value'] = json.dumps(data)
    ctx, page, errs = new_page(b, st)
    page.goto(BASE + 'index.html')
    page.wait_for_selector('#btnListen')
    time.sleep(1.5)
    s0 = page.evaluate('window.__tt.state.sizes[0]')
    check('refDecay досчитан', s0.get('refDecayState') in ('ok', 'long') and s0.get('refDecay'), (s0.get('refDecay'), s0.get('refDecayState'), s0.get('refPurity')))
    txt = page.inner_text('#verdictBox')
    check('старая запись журнала: вердикт по частоте', 'Натяжение в норме' in txt, txt)
    check('нет ошибок в консоли', not errs, errs[:3])
    b.close()

srv.terminate()
print(f'\nИтого: {sum(results)} из {len(results)}')
sys.exit(0 if all(results) else 1)
