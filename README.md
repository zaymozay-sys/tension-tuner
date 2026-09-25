# Натяжка · TapTension

**Проверка натяжения шнура подвеса холста по звуку удара.** Цифровой инструмент для способа контроля качества по патенту РФ № 2867038.

[English version below](#english)

## Что делает приложение

Для каждого размера подрамника записывается эталон — удар шестигранным ключом 4–5 мм по центру правильно натянутого шнура, перпендикулярно шнуру. При проверке приложение слушает удар и сравнивает его с эталоном по трём признакам:

| Признак | Как измеряется |
|---|---|
| Частота основного тона | автокорреляция; допуск по умолчанию ±3% по частоте ≈ ±6% по натяжению |
| Время затухания | спад основного тона на 20 дБ от пика |
| Чистота тона | периодичность звука на найденной частоте, 0–100%; снижается при дребезге |

Вердикт: **норма**, **слабо**, **туго** или **брак**. Брак, как в описании патента, — быстрое затухание (короче 60% эталона), дребезг (чистота ниже 75% эталона) или глухой звук (оба признака).

Два режима, переключатель вверху экрана:
- **Лайт** — проверить натяжение: размер холста, эталон, удар, вердикт.
- **Про** — проверка по регламенту. Эталоны по длине стороны подрамника со шнуром (перечень 20–120 см с шагом 10 см и свои длины). В каждой записи — номер заказа, исполнитель, паспорт контрольного ключа (идентификатор и масса), результат по звуку и отметка о провисании полотна. Один удар на проверку; повторная проверка после корректировки ссылается на первичную запись; статусы «нет отклика» и «проверка прервана». Реестр не удаляется и не редактируется. Выгрузки: CSV реестра и перечня эталонов, аудиофайлы эталонов, печатные формы реестра РП-01 и отчёта ОТЧ-ПАТ-01 за период. Подбор порогов брака на своих изделиях.

Кроме того:
- журнал проверок по каждому удару с выгрузкой в CSV для Excel;
- передача эталона в другую мастерскую одним файлом;
- работа без интернета; данные хранятся только на телефоне;
- русский и английский интерфейс.

## Как открыть

- Веб-версия: https://zaymozay-sys.github.io/tension-tuner/ — английский интерфейс: https://zaymozay-sys.github.io/tension-tuner/?lang=en
- Android: RuStore, «Натяжка — тюнер подвеса картин»
- [Инструкция](guide.html) · [User guide](guide-en.html) · [Политика конфиденциальности](privacy.html)

## Патент

RU 2867038 C1 «Способ контроля качества натяжения гибкого подвеса художественного полотна на подрамнике». Автор и патентообладатель — Воробьев Александр Сергеевич. Заявка № 2026103663 от 09.02.2026, дата государственной регистрации 28.07.2026. [Запись в реестре ФИПС](https://new.fips.ru/registers-doc-view/fips_servlet?DB=RUPAT&DocNumber=2867038&TypeFile=html).

## Условия использования

Приложение бесплатное. Автор и патентообладатель разрешает безвозмездно применять способ с помощью этого приложения для контроля качества собственной продукции. Подробно — в [LICENSE](LICENSE).

## Автор

Александр Сергеевич Воробьев, типография «ФотоКот» (Липецк) · zaymozay@gmail.com

## Для разработчиков

- Приложение — один файл `index.html`, без сборки и внешних зависимостей. Анализ звука — блок `DSP-BEGIN … DSP-END`.
- `sw.js` кеширует файлы для работы без интернета; при выпуске новой версии меняется `VERSION`.
- Тесты анализа звука на синтетических ударах: `node tests/dsp.test.js` (частота 55–587 Гц, защита от ошибки на октаву, затухание, чистота тона, вердикты, живой режим, «нет отклика», пороги и подбор порогов).
- Проверка в браузере с поддельным микрофоном: `node tests/make_wav.js && python3 tests/e2e.py && python3 tests/e2e_pro.py` (нужен Playwright; второй тест проходит весь сценарий режима «Про»: реестр, повторная проверка, выгрузки, отчёт, резервная копия, английский интерфейс).
- Реестр режима «Про» хранится в IndexedDB (`natyazhka-registry`), отдельно от размеров и настроек (`localStorage`).
- История изменений — [CHANGELOG.md](CHANGELOG.md).

---

<a id="english"></a>
# TapTension (Натяжка)

**Checks the tension of the hanging cord on stretched canvas prints by the sound of a tap.** A digital tool for the quality-control method of Russian Patent No. 2867038.

## What it does

For each stretcher-frame size, the user records a reference: a tap with a 4–5 mm hex key on the center of a correctly tensioned cord, perpendicular to the cord. During a check, the app listens to the tap and compares it with the reference on three features:

| Feature | How it is measured |
|---|---|
| Fundamental frequency | autocorrelation; default tolerance ±3% in frequency ≈ ±6% in tension |
| Decay time | time for the fundamental to fall by 20 dB from its peak |
| Tone purity | periodicity of the sound at the detected frequency, 0–100%; drops with rattle |

Verdict: **OK**, **low**, **high** or **reject**. As described in the patent, a reject is fast decay (shorter than 60% of the reference), rattle (purity below 75% of the reference) or a dull sound (both).

Two modes, switched at the top of the screen:
- **Lite** — check the tension: canvas size, reference, tap, verdict.
- **Pro** — checks by a written procedure. References by the length of the stretcher side that carries the cord (a 20–120 cm list in 10 cm steps plus custom lengths). Every record holds the order number, operator, control tool passport (ID and mass), the acoustic result and a visual sag check. One tap per check; a re-check after correction links to the primary record; “no response” and “check interrupted” statuses. The registry is never deleted or edited. Exports: registry and reference-list CSV, reference audio files, printable RP-01 registry and OTCH-PAT-01 period report. Reject thresholds can be tuned on your own pieces.

Also:
- an inspection log of every tap, exportable to CSV;
- one-file transfer of a reference to another workshop;
- works offline; all data stays on the phone;
- Russian and English interface.

## Open the app

- Web: https://zaymozay-sys.github.io/tension-tuner/?lang=en
- Android: RuStore (Russian store listing)
- [User guide](guide-en.html) · [Privacy policy](privacy.html#en)

## Patent

RU 2867038 C1, “Method for Quality Control of the Tension of a Flexible Hanger of an Art Canvas on a Stretcher Frame.” Inventor and patent holder: Aleksandr Vorobev. Application No. 2026103663 filed 9 February 2026; registered 28 July 2026. [Rospatent (FIPS) register entry](https://new.fips.ru/registers-doc-view/fips_servlet?DB=RUPAT&DocNumber=2867038&TypeFile=html).

## Terms of use

The app is free. The author and patent holder permits free use of the method through this app for quality control of one’s own products. See [LICENSE](LICENSE).

## Author

Aleksandr Vorobev, FotoKot print studio (Lipetsk, Russia) · zaymozay@gmail.com
