"""E2E-проверка режима «Про» в Chromium с поддельным микрофоном.
Реестр хранится в IndexedDB, поэтому между запусками браузера состояние переносится с indexed_db=True."""
import os, re, sys, json, time, subprocess
from datetime import date
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
if not os.path.exists(os.path.join(OUT, 'index.html')):
    OUT = os.path.join(HERE, '..')  # корень репозитория
PORT = 8766
WAV = os.path.join(HERE, 'wav')
BASE = f'http://localhost:{PORT}/'
SHOTS = os.path.join(HERE, 'pro_shots')
os.makedirs(SHOTS, exist_ok=True)

import atexit
srv = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT), '-d', OUT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
atexit.register(srv.terminate)
time.sleep(0.8)
results = []
def check(name, cond, info=''):
    results.append(bool(cond))
    print(('  ok   ' if cond else '  FAIL ') + name + ('  ' + str(info) if info not in ('', None) else ''))

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
    page.on('dialog', lambda d: d.accept())
    return ctx, page, errs

def reg(page): return page.evaluate('window.__tt.reg()')
def st(page): return page.evaluate('window.__tt.state')
def main(page): return page.evaluate('document.getElementById("main").textContent')
def lines(page): return page.inner_text('#main').split('\n')
def open_app(page, query=''):
    page.goto(BASE + 'index.html' + query)
    page.wait_for_selector('#main')
    page.wait_for_function('window.__tt && window.__tt.reg')
    time.sleep(0.4)

def side_id(page, cm): return page.evaluate(f'window.__tt.state.sizes.find(s => s.kind === "side" && s.sideCm === {cm}).id')

def strike(page, order=None, measurable=True):
    """один удар на экране «Проверка»: ждём, пока приложение само остановит прослушивание.
    Поддельный микрофон иногда начинает с хвоста предыдущего удара — тогда приложение честно пишет «шумно»;
    такой удар отменяем и повторяем (не больше трёх раз)."""
    if order is not None:
        page.fill('#proOrder', order)
    for attempt in range(3):
        page.click('#btnProListen')
        page.wait_for_selector('#btnStop', timeout=8000)
        page.wait_for_selector('#btnStop', state='detached', timeout=20000)
        time.sleep(0.2)
        v = page.inner_text('#verdictBox')
        if not measurable or page.query_selector('#proDiscard') is None:
            return v
        print('     (удар не оценён: ' + v + ' — повтор)')
        page.click('#proDiscard')
    return v

def record(page, sag):
    n = len(reg(page))
    page.click(f'[data-sag="{sag}"]')
    page.click('#proRecord')
    page.wait_for_function(f'window.__tt.reg().length === {n + 1}', timeout=8000)
    page.wait_for_selector('.result-card', timeout=5000)
    return reg(page)[-1]

def cal_strike(page, which):
    """один удар подбора порогов; если приложение удар не учло (шум, нет тона) — повторяем, но не больше трёх раз"""
    sid = page.evaluate('window.__tt.state.proSelectedSizeId')
    n = page.evaluate(f'(window.__tt.state.calib["{sid}"] || []).length')
    for attempt in range(3):
        page.click('#calGood' if which == 'good' else '#calBad')
        page.wait_for_selector('#btnStop', timeout=8000)
        page.wait_for_selector('#btnStop', state='detached', timeout=20000)
        time.sleep(0.2)
        if page.evaluate(f'(window.__tt.state.calib["{sid}"] || []).length') == n + 1:
            return attempt
        print('     (удар подбора не учтён: ' + page.evaluate('document.getElementById("notice").textContent') + ')')
    raise AssertionError('удар подбора не учтён три раза подряд')

def download(page, selector):
    with page.expect_download() as dl:
        page.click(selector)
    return dl.value.suggested_filename, open(dl.value.path(), encoding='utf-8-sig').read()

TODAY = date.today()
RU_DAY = TODAY.strftime('%d.%m.%Y')

with sync_playwright() as p:
    # ---------- 1. включение «Про», паспорт ключа, перечень длин, эталон, первые проверки ----------
    print('1. Режим «Про»: параметры, перечень 20–120 см, эталон 60 см, проверки (ok.wav)')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b)
    open_app(page)
    navs = lambda: page.eval_on_selector_all('#nav .nav-btn', 'els => els.map(e => e.dataset.view)')
    check('по умолчанию простой режим', st(page)['mode'] == 'simple' and navs() == ['tuner', 'sizes'], navs())
    page.click('#main .mode-btn[data-mode="pro"]')
    check('переключение на «Про»: вкладки Проверка / Реестр / Эталоны', st(page)['mode'] == 'pro' and navs() == ['check', 'registry', 'refs'], navs())
    t = main(page)
    check('без паспорта ключа проверка не начинается', 'Исполнитель и ключ не указаны' in t and page.query_selector('#btnProListen') is None)
    page.click('#main button.btn[data-pro-settings]')
    page.fill('#ps_org', 'ФотоКот')
    page.fill('#ps_op', 'Иванов И. И.')
    page.fill('#ps_tool', 'К-01')
    page.fill('#ps_mass', '')
    page.click('#ps_save')
    check('без массы ключа параметры не сохраняются', not st(page)['pro'].get('toolMass'))
    page.fill('#ps_mass', '42')
    page.click('#ps_save')
    pro = st(page)['pro']
    check('паспорт ключа сохранён', pro.get('operator') == 'Иванов И. И.' and pro.get('toolId') == 'К-01' and pro.get('toolMass') == 42 and pro.get('org') == 'ФотоКот', pro)
    check('нет эталонов → подсказка', 'Нет эталонов' in main(page))
    page.click('#goRefs')
    page.click('#addPresetSides')
    sides = page.evaluate('window.__tt.state.sizes.filter(s => s.kind === "side").map(s => s.sideCm)')
    check('перечень 20–120 см с шагом 10', sides == list(range(20, 121, 10)), sides)
    check('простые слоты не смешиваются с длинами', page.evaluate('window.__tt.state.sizes.filter(s => s.kind !== "side").length') == 0)
    page.click('#addSide')
    page.fill('#sd_cm', '45')
    page.click('#sd_save')
    check('своя длина 45 см', 45 in page.evaluate('window.__tt.state.sizes.filter(s => s.kind === "side").map(s => s.sideCm)'))
    id60 = side_id(page, 60)
    page.click(f'[data-pick-side="{id60}"]')
    page.click('#btnStartRec')
    page.wait_for_selector('#btnSaveRec', timeout=15000)
    page.click('#btnSaveRec')
    s60 = page.evaluate(f'window.__tt.state.sizes.find(s => s.id === "{id60}")')
    check('эталон 60 см: частота, затухание, ключ и исполнитель', abs(s60['target'] - 150) < 1.5 and s60.get('refDecayState') == 'ok' and s60.get('refToolId') == 'К-01' and s60.get('refToolMass') == 42 and s60.get('refOperator') == 'Иванов И. И.' and s60.get('refRecordedAt'),
          f"{s60['target']:.1f} Гц, {s60.get('refDecay'):.0f} мс, {s60.get('refToolId')}")
    page.screenshot(path=os.path.join(SHOTS, 'refs.png'), full_page=True)

    page.click('.nav-btn[data-view="check"]')
    id45 = side_id(page, 45)
    page.select_option('#sizeSelect', id45)
    check('длина без эталона: проверка запрещена', 'Для длины 45 см нет эталона' in main(page) and page.query_selector('#btnProListen') is None)
    page.select_option('#sizeSelect', id60)
    page.fill('#proOrder', '')
    page.click('#btnProListen')
    check('без номера заказа удар не слушаем', page.query_selector('#btnStop') is None)
    v = strike(page, '1001')
    check('удар → «Натяжение в норме», один удар и стоп', 'Натяжение в норме' in v and page.query_selector('#btnStop') is None, v)
    check('без отметки о провисании запись не вносится', page.is_disabled('#proRecord'))
    page.screenshot(path=os.path.join(SHOTS, 'check_shot.png'), full_page=True)
    r = record(page, 'none')
    check('запись № 1: соответствует → на упаковку', r['no'] == 1 and r['result'] == 'pass' and r['action'] == 'pack' and r['order'] == '1001' and r['side'] == 60 and r['attempt'] == 1 and r['sag'] == 'none', {k: r[k] for k in ('no', 'result', 'order', 'side')})
    check('в записи: исполнитель, ключ, эталон, пороги, версия', r['operator'] == 'Иванов И. И.' and r['toolId'] == 'К-01' and r['toolMass'] == 42 and abs(r['ref']['target'] - s60['target']) < 0.01 and r['thr']['decayRel'] == 0.6 and r['v'] == '2.4' and r['freq'] and r['decayMs'] and r['purity'])
    check('карточка результата и пустое поле заказа', '✓ Запись № 1: соответствует' in main(page) and page.input_value('#proOrder') == '')
    page.screenshot(path=os.path.join(SHOTS, 'check_pass.png'), full_page=True)

    strike(page, '1002')
    r = record(page, 'present')
    check('звук в норме, но провисание → не соответствует', r['result'] == 'fail' and r['reasons'] == ['sag'] and r['action'] == 'correct', r['reasons'])
    t = main(page)
    check('ждёт повторной проверки: заказ 1002', 'Ждут повторной проверки · 1' in t and 'Заказ 1002' in t)
    page.fill('#proOrder', '1001')
    page.press('#proOrder', 'Tab')
    check('повторный номер годного изделия → подсказка про дробь', 'уже прошло проверку (запись № 1)' in main(page))
    page.fill('#proOrder', '')
    page.press('#proOrder', 'Tab')

    page.click('.nav-btn[data-view="refs"]')
    page.click('#goCalib')
    for i in range(3): cal_strike(page, 'good')
    t = main(page)
    check('подбор порогов: 3 удара по годным → рекомендация', 'Рекомендация' in t and 'Годные проходят: 3 из 3' in t, [l for l in lines(page) if 'Годные' in l])
    check('localStorage без реестра', 'registry' not in page.evaluate('localStorage.getItem("canvas_tension_v2")'))
    check('нет ошибок в консоли', not errs, errs[:3])
    storage = ctx.storage_state(indexed_db=True)
    b.close()

    # ---------- 2. брак «слабо», подбор порогов по недотянутым ----------
    print('2. Брак «слабое натяжение» и подбор порогов (loose.wav)')
    b = launch(p, 'loose.wav')
    ctx, page, errs = new_page(b, storage)
    open_app(page)
    check('после перезапуска: режим «Про» и реестр из IndexedDB', st(page)['mode'] == 'pro' and len(reg(page)) == 2 and page.evaluate('window.__tt.backend()') == 'idb', (st(page)['mode'], len(reg(page))))
    v = strike(page, '1003')
    check('вердикт «Подтяните сильнее»', 'Подтяните сильнее' in v, v)
    r = record(page, 'none')
    check('запись № 3: не соответствует, причина — слабое натяжение', r['no'] == 3 and r['result'] == 'fail' and r['reasons'] == ['loose'], r['reasons'])
    t = main(page)
    check('карточка: вернуть на корректировку + причина', 'не соответствует — вернуть на корректировку' in t and 'слабое натяжение' in t)
    page.screenshot(path=os.path.join(SHOTS, 'check_fail.png'), full_page=True)
    page.click('.nav-btn[data-view="refs"]')
    page.click('#goCalib')
    for i in range(2): cal_strike(page, 'bad')
    t = main(page)
    check('рекомендация: недотянутые выявлены 2 из 2', 'Недотянутые выявлены: 2 из 2' in t, [l for l in lines(page) if 'Недотянутые' in l])
    page.screenshot(path=os.path.join(SHOTS, 'calib.png'), full_page=True)
    page.click('#calApply')
    s = st(page)
    s60 = next(x for x in s['sizes'] if x['id'] == id60)
    check('пороги применены и сохранены', s['thresholds'] and 0.3 <= s['thresholds']['decayRel'] <= 0.95 and 2 <= s60['tolerance'] <= 15, (s['thresholds'], s60['tolerance']))
    check('нет ошибок в консоли', not errs, errs[:3])
    storage = ctx.storage_state(indexed_db=True)
    b.close()

    # ---------- 3. нет отклика: отмена, «прервана», запись «не соответствует» ----------
    print('3. Глухой удар без тона (thud.wav)')
    b = launch(p, 'thud.wav')
    ctx, page, errs = new_page(b, storage)
    open_app(page)
    v = strike(page, '1004', measurable=False)
    check('вердикт «Нет отклика»', 'Нет отклика' in v, v)
    page.click('#proDiscard')
    check('«Удара не было» — запись не вносится', len(reg(page)) == 3 and page.query_selector('#btnProListen') is not None)
    strike(page, measurable=False)
    page.click('#proAbort')
    page.wait_for_function('window.__tt.reg().length === 4')
    r = reg(page)[-1]
    check('проверка прервана: запись № 4, действие — повторить', r['result'] == 'aborted' and r['reasons'] == ['abort'] and r['action'] == 'repeat', r['reasons'])
    check('после прерванной проверки номер заказа остаётся', page.input_value('#proOrder') == '1004')
    strike(page, measurable=False)
    check('кнопка «Записать: нет отклика»', 'нет отклика' in page.inner_text('#proRecord'))
    r = record(page, 'none')
    check('нет отклика → не соответствует', r['result'] == 'fail' and r['reasons'] == ['notone'] and r['freq'] is None and r['attempt'] == 1, r['reasons'])
    check('нет ошибок в консоли', not errs, errs[:3])
    storage = ctx.storage_state(indexed_db=True)
    b.close()

    # ---------- 4. второй удар во время затухания ----------
    print('4. Второй удар во время затухания (double.wav)')
    b = launch(p, 'double.wav')
    ctx, page, errs = new_page(b, storage)
    open_app(page)
    v = strike(page, '1005', measurable=False)
    check('вердикт «Затухание прервано повторным ударом»', 'прервано повторным ударом' in v, v)
    check('записать как годное или брак нельзя', page.query_selector('#proRecord') is None and page.query_selector('#proAbort') is not None)
    page.click('#proAbort')
    page.wait_for_function('window.__tt.reg().length === 6')
    r = reg(page)[-1]
    check('запись № 6: прервана, причина — повторный удар', r['result'] == 'aborted' and r['reasons'] == ['interrupted'], r['reasons'])
    check('нет ошибок в консоли', not errs, errs[:3])
    storage = ctx.storage_state(indexed_db=True)
    b.close()

    # ---------- 5. повторная проверка, смена ключа, реестр, выгрузки, печатные формы ----------
    print('5. Повторная проверка, смена ключа, выгрузки и отчёт (ok.wav)')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b, storage)
    open_app(page)
    t = main(page)
    check('ждут повторной проверки: 1004, 1003, 1002', 'Ждут повторной проверки · 3' in t and all(f'Заказ {o}' in t for o in ('1002', '1003', '1004')))
    rid3 = next(x['id'] for x in reg(page) if x['no'] == 3)
    page.click(f'[data-recheck="{rid3}"]')
    t = main(page)
    check('повторная проверка: попытка 2, первичная запись № 3', 'попытка 2 · первичная запись № 3' in t and page.input_value('#proOrder') == '1003' and page.input_value('#proCorrection') == 'Дотяжка шнура')
    page.fill('#proCorrection', 'Дотяжка шнура на 2 оборота')
    v = strike(page)
    check('после корректировки — норма', 'Натяжение в норме' in v, v)
    r = record(page, 'none')
    check('запись № 7: повторная, соответствует, связь с № 3', r['no'] == 7 and r['attempt'] == 2 and r['prevNo'] == 3 and r['prev'] == rid3 and r['result'] == 'pass' and r['correction'] == 'Дотяжка шнура на 2 оборота', {k: r[k] for k in ('no', 'attempt', 'prevNo', 'correction')})
    check('в записи — подобранные пороги', r['thr'] == st(page)['thresholds'], r['thr'])
    t = main(page)
    check('ждут повтора: 1004 и 1002', 'Ждут повторной проверки · 2' in t and 'Заказ 1003' not in t.split('Ждут повторной проверки')[1])

    page.click('#main .pro-line [data-pro-settings]')
    page.fill('#ps_mass', '45')
    page.click('#ps_save')
    t = main(page)
    check('смена ключа → просьба сверить отклик', 'Ключ заменён: К-01, 45 г' in t and st(page)['pro'].get('toolAck') is False)
    page.fill('#proOrder', '1006')
    page.click('#btnProListen')
    time.sleep(0.5)
    check('до сверки проверка не начинается', page.query_selector('#btnStop') is None)
    page.click('#proToolAck')
    check('после сверки баннер убран', 'Ключ заменён' not in main(page) and st(page)['pro'].get('toolAck') is True)

    page.click('.nav-btn[data-view="registry"]')
    t = main(page)
    check('реестр: 7 записей, 4 изделия', 'Записей: 7 · изделий: 4' in t, lines(page)[2:5])
    stats = page.eval_on_selector_all('.journal-stats.five b', 'els => els.map(e => e.textContent)')
    check('счётчики: 5 проверок, 1 годно сразу, 3 на корректировку, 2 ждут, 2 прервано', stats == ['5', '1', '3', '2', '2'], stats)
    check('напоминание о выгрузке', 'Реестр ещё не выгружался' in t)
    page.screenshot(path=os.path.join(SHOTS, 'registry.png'), full_page=True)
    name, csv = download(page, '#expRegCsv')
    lines = csv.splitlines()
    check('CSV реестра: имя и заголовок', name.startswith('natyazhka-reestr-') and lines[0].startswith('№;Дата;Время;Заказ;Длина стороны, см;Проверка;Первичная запись №;Корректировка;Частота, Гц') and lines[0].count(';') == 27, (name, lines[0][:60]))
    check('CSV реестра: 7 строк', len(lines) == 8, len(lines))
    row = {l.split(';')[0]: l for l in lines[1:]}
    check('CSV: № 1 годно, передано на упаковку', ';1001;60;первичная;' in row['1'] and ';соответствует;' in row['1'] and 'передано на упаковку;годно;Иванов И. И.;К-01;42,0;' in row['1'], row['1'][-120:])
    check('CSV: № 3 → итог изделия «годно» после повторной', ';1003;60;первичная;' in row['3'] and 'слабое натяжение' in row['3'] and 'возвращено на корректировку;годно;' in row['3'])
    check('CSV: № 2 ждёт повторной', 'провисание полотна;возвращено на корректировку;ожидает повторной проверки;' in row['2'])
    check('CSV: № 4 и № 6 прерваны', ';проверка прервана;помеха;провести проверку заново;' in row['4'] and 'повторный удар во время затухания' in row['6'])
    check('CSV: № 5 нет отклика', ';нет отклика;нет;не соответствует;нет отклика;' in row['5'], row['5'][-110:])
    check('CSV: № 7 повторная, попытка 2, к записи № 3', ';повторная, попытка 2;3;Дотяжка шнура на 2 оборота;' in row['7'])
    check('после выгрузки напоминание исчезло', st(page)['pro'].get('lastExportTs') and 'Реестр ещё не выгружался' not in main(page))
    name, csv = download(page, '#expRefsCsv')
    lines = csv.splitlines()
    check('CSV эталонов: действующий эталон 60 см с аудиофайлом', name.startswith('natyazhka-etalony-') and any(l.startswith('60;15') and 'действующий' in l and 'К-01' in l and '.webm' in l for l in lines[1:]), lines[:2])

    page.click('#printRp')
    page.wait_for_selector('#printView .pv-doc h1')
    pv = page.inner_text('#printView')
    rows = page.evaluate('[...document.querySelectorAll("#printView .pv-scroll")].pop().querySelectorAll("tr").length')
    check('РП-01: форма, паспорт ключа, эталоны, 7 проверок', 'Форма РП-01' in pv and 'ФотоКот' in pv and '2867038' in pv and 'К-01' in pv and 'текущий, проверок пока нет' in pv and rows == 8, rows)
    check('РП-01: печатный режим', page.evaluate('document.documentElement.classList.contains("printing")'))
    page.screenshot(path=os.path.join(SHOTS, 'print_rp01.png'), full_page=True)
    page.click('#pvClose')
    check('печатная форма закрыта', not page.evaluate('document.documentElement.classList.contains("printing")') and page.query_selector('#expRegCsv') is not None)
    page.click('#printRep')
    page.wait_for_selector('#printView .pv-doc h1')
    pv = page.inner_text('#printView')
    kv = page.evaluate('Object.fromEntries([...document.querySelectorAll("#printView table")[0].rows].map(r => [r.cells[0].textContent, r.cells[1].textContent]))')
    check('ОТЧ-ПАТ-01: итоги', kv.get('Проверок (без прерванных)') == '5' and kv.get('в том числе первичных / повторных') == '4 / 1' and kv.get('Прервано проверок') == '2' and kv.get('Изделий проверено') == '4'
          and kv.get('Соответствовали с первой проверки') == '1 (25%)' and kv.get('Возвращено на корректировку') == '3 (75%)' and kv.get('Из них прошли повторную проверку') == '1' and kv.get('Ожидают повторной проверки') == '2', kv)
    check('ОТЧ-ПАТ-01: причины и вывод', 'провисание полотна' in pv and 'слабое натяжение' in pv and 'нет отклика' in pv and 'способ применён к 4 изделиям (5 проверок)' in pv, pv[pv.find('5. '):][:200])
    page.screenshot(path=os.path.join(SHOTS, 'print_report.png'), full_page=True)
    page.click('#pvClose')
    page.fill('#repFrom', '2020-01-01')
    page.fill('#repTo', '2020-01-31')
    page.click('#printRep')
    time.sleep(0.3)
    check('период без записей — отчёт не формируется', page.query_selector('#printView .pv-doc') is None)

    name, js = download(page, '#btnExport')
    data = json.loads(js)
    check('резервная копия: реестр и параметры', len(data.get('registry', [])) == 7 and data['state']['pro']['toolId'] == 'К-01' and data['state']['thresholds'], name)
    backup = os.path.join(SHOTS, 'backup.json')
    open(backup, 'w', encoding='utf-8').write(js)
    check('нет ошибок в консоли', not errs, errs[:3])
    storage = ctx.storage_state(indexed_db=True)
    b.close()

    # ---------- 6. восстановление на новом телефоне, удаление длины ----------
    print('6. Восстановление из копии и слияние реестра')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b)
    open_app(page)
    page.click('.nav-btn[data-view="sizes"]')
    page.set_input_files('#importFile', backup)
    page.wait_for_function('window.__tt.reg().length === 7', timeout=8000)
    s = st(page)
    check('импорт: режим «Про», 7 записей, следующий № 8', s['mode'] == 'pro' and len(reg(page)) == 7 and s['pro']['nextNo'] == 8, (s['mode'], s['pro'].get('nextNo')))
    page.click('.nav-btn[data-view="registry"]')
    page.set_input_files('#importFile', backup)
    time.sleep(1.0)
    check('повторный импорт не дублирует записи', len(reg(page)) == 7)
    page.click('.nav-btn[data-view="refs"]')
    page.click(f'[data-pick-side="{id60}"]')
    page.click('#delSide')
    check('длина 60 см удалена, реестр цел', not any(x.get('sideCm') == 60 for x in st(page)['sizes']) and len(reg(page)) == 7)
    page.click('.nav-btn[data-view="registry"]')
    name, csv = download(page, '#expRegCsv')
    check('CSV после удаления длины: эталон в записях сохранён', ';150,' in csv.splitlines()[1], csv.splitlines()[1][:90])
    page.click('.nav-btn[data-view="check"]')
    rid = next(x['id'] for x in reg(page) if x['no'] == 2)
    page.click(f'[data-recheck="{rid}"]')
    check('повторная проверка без длины в перечне → подсказка, без падения', not errs)
    bad = json.loads(open(backup, encoding='utf-8').read())
    r0 = dict(bad['registry'][0]); r0['id'] = '"><img src=x onerror=alert(1)>'
    r1 = dict(bad['registry'][1]); r1['id'] = 'extra1'; r1['reasons'] = ['<b>x</b>', 'sag']; r1['no'] = '<i>9</i>'
    bad['registry'] = [r0, r1, dict(r1)]
    bpath = os.path.join(SHOTS, 'backup_bad.json')
    json.dump(bad, open(bpath, 'w', encoding='utf-8'), ensure_ascii=False)
    page.click('.nav-btn[data-view="registry"]')
    page.set_input_files('#importFile', bpath)
    page.wait_for_function('window.__tt.reg().length === 8', timeout=8000)
    time.sleep(0.5)
    x = next(r for r in reg(page) if r['id'] == 'extra1')
    check('импорт чужого файла: неверный id отброшен, повтор не задвоен, причины очищены', len(reg(page)) == 8 and x['reasons'] == ['sag'] and x['no'] == 0 and page.query_selector('img[src="x"]') is None, (len(reg(page)), x['reasons'], x['no']))
    check('нет ошибок в консоли', not errs, errs[:3])
    b.close()

    # ---------- 7. английский интерфейс «Про» ----------
    print('7. Английский интерфейс «Про» (?lang=en)')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b, storage, locale='en-US')
    open_app(page, '?lang=en')
    DATA = {'Русский', 'Иванов', 'И.', 'ФотоКот', 'К-01', 'К-01,', 'Дотяжка', 'шнура', '(К-01)', 'на', 'оборота', 'оборота;'}  # данные, введённые пользователем
    def cyr(): return sorted(set(re.findall(r'[^\s]*[А-Яа-яЁё][^\s]*', page.evaluate('document.body.innerText'))) - DATA)
    for v in ('check', 'registry', 'refs'):
        page.click(f'.nav-btn[data-view="{v}"]')
        c = cyr()
        check(f'EN «{v}»: нет русского текста', c == [], c[:8])
    page.click('#goCalib')
    c = cyr(); check('EN «calib»: нет русского текста', c == [], c[:8])
    page.click('.nav-btn[data-view="registry"]')
    for btn in ('#printRp', '#printRep'):
        page.click(btn)
        page.wait_for_selector('#printView .pv-doc h1')
        c = cyr()
        pv = page.inner_text('#printView')
        check(f'EN печатная форма {btn}: нет русского текста', c == [] and ('RP-01' in pv or 'OTCH-PAT-01' in pv), c[:8])
        page.click('#pvClose')
    name, csv = download(page, '#expRegCsv')
    head = csv.splitlines()[0]
    check('EN CSV реестра', name.startswith('taptension-registry-') and head.startswith('No.,Date,Time,Order,') and not re.search('[А-Яа-я]', head), head[:70])
    page.click('#main [data-pro-settings]')
    c = cyr(); check('EN «Параметры Про»: нет русского текста', c == [], c[:8])
    page.keyboard.press('Escape')
    check('нет ошибок в консоли', not errs, errs[:3])
    b.close()

    # ---------- 8. возврат в простой режим ----------
    print('8. Возврат в простой режим')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b, storage)
    open_app(page)
    page.click('#main .mode-btn[data-mode="simple"]')
    t = main(page)
    check('простой режим: вкладки Тюнер / Холсты', navs() == ['tuner', 'sizes'] and st(page)['mode'] == 'simple')
    page.click('.nav-btn[data-view="sizes"]')
    t = main(page)
    names = page.evaluate('[...document.querySelectorAll("#main *")].filter(e => !e.children.length && /^\\d+ см$/.test(e.textContent.trim())).map(e => e.textContent.trim())')
    check('длины «Про» не видны в простом режиме', names == [] and '40×60 см' in t, names)
    check('реестр не тронут', len(reg(page)) == 7)
    check('нет ошибок в консоли', not errs, errs[:3])
    b.close()

    # ---------- 9. несохранённый удар не теряется, «не засчитывать», двойное нажатие ----------
    print('9. Несохранённый удар, «проверка прервана» для годного удара, двойное нажатие (ok.wav)')
    b = launch(p, 'ok.wav')
    ctx, page, errs = new_page(b, storage)
    open_app(page)
    n0 = len(reg(page))
    strike(page, '1007')
    check('после удара длину сменить нельзя', page.is_disabled('#sizeSelect'))
    page.click('.nav-btn[data-view="registry"]')
    page.click(f'[data-recheck="{next(x["id"] for x in reg(page) if x["no"] == 2)}"]')
    check('«Проверить повторно» не сбрасывает удар', page.evaluate('document.getElementById("notice").textContent').startswith('Сначала запишите результат удара'))
    page.click('.nav-btn[data-view="check"]')
    check('после перехода по вкладкам удар на месте', page.query_selector('#proRecord') is not None and page.input_value('#proOrder') == '1007')
    page.click('#proAbort')
    page.wait_for_function(f'window.__tt.reg().length === {n0 + 1}')
    r = reg(page)[-1]
    check('«не засчитывать»: запись «проверка прервана» с замером', r['result'] == 'aborted' and r['reasons'] == ['abort'] and r['acoustic'] == 'tuned' and r['freq'], {k: r[k] for k in ('result', 'reasons', 'acoustic')})
    check('после прерванной проверки длину снова можно выбрать', not page.is_disabled('#sizeSelect'))
    strike(page, '1008')
    page.click('[data-sag="none"]')
    page.evaluate('(() => { const b = document.getElementById("proRecord"); b.click(); b.click(); })()')
    time.sleep(1.0)
    check('двойное нажатие — одна запись', len(reg(page)) == n0 + 2, len(reg(page)) - n0)
    check('нет ошибок в консоли', not errs, errs[:3])
    b.close()

srv.terminate()
print(f'\nИтого: {sum(results)} из {len(results)}')
sys.exit(0 if all(results) else 1)
