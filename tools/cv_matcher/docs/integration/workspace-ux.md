# Фокус рабочего места: Today, вакансии, рейтинг и отклики

> Сверка 22.10.2026. Раздел learning теперь [Карьерная траектория](../architecture/career-trajectory.md): цель/этапы перед выбором CV. Исторический UX трёх основ анализа остаётся внутри инструментов навыков. [Текущий вход](../applicant_quickstart.md).

20.10.2026. Эволюционный UI/UX-рефакторинг существующего archive-web без новых UI dependencies.

## Today

[journey.js](../../archive-web/journey.js) показывает одно следующее действие для текущего CV: проверка отклика, актуализация CV, сбор, рейтинг или выбор следующего отклика. Текущие данные и `resume_id/state/status/stage_key` поступают из [journey.overview](../../src/journey.py). Отклик с другого CV не выбирается случайно как основной. На экран выведены три компактных показателя, до трёх следующих карточек и до двух ближайших встреч.

Пять сворачиваемых панелей: задачи агента, автоматизация HH, источники/расписание, подключение/диагностика и цель/CV. Их содержимое загружается по раскрытию; начальный показ не вызывает agent/discovery API. При обновлении настроек открытые панели сохраняются в пределах страницы. Очередь, pause/cancel, opt-in подъём, подтверждения и источники доступны из прежних бизнес-компонентов.

`Frame with ID 0 is showing error page` означает, что при попытке чтения Chrome показывал страницу ошибки. В UI это **последняя неудачная попытка**, с датой из `last_error_at` [hh_auto_sync](../../src/hh_auto_sync.py); текущий queued/running статус отделён. Понятное пояснение и действие — на первом уровне, исходная строка — в техническом раскрытии. [workflow_messages.browser_note](../../src/workflow_messages.py) также переводит этот случай для Telegram. Представление ошибки не является исправлением сетевой доступности HH.

## Вакансии и рейтинг

[archive-web/index.html](../../archive-web/index.html), [archive.js](../../archive-web/archive.js), [vacancy-selection.js](../../archive-web/vacancy-selection.js):

- Общая компактная строка: поиск, компании, CV, дополнительные фильтры.
- Крупные сводные счётчики скрыты на этих двух экранах; число результатов остаётся над списком.
- Источник и модель фильтруются прежними контролами/ID; модель и редкие фильтры находятся в раскрытии.
- Настройки нового ранжирования и платные/offline действия находятся в **Настроить и обновить рейтинг**. Открытие страницы читает сохранённые результаты; расчёт по-прежнему требует явной кнопки.
- Prompt/export вынесен в закрытый **Отбор с помощью LLM · без API**. Ничего из существующей пакетной функциональности не удалено.
- Ручное добавление вакансии свёрнуто; на рейтинге скрыто.
- В списке остаются ключевые статусы, близость и ручная отметка отклика. Полное описание, наличие готовых vectors и число версий не засоряют карточки; они доступны в tooltip и полной карточке.
- Навигация между разделами возвращает к началу страницы.

## Чтение полного описания вакансии

[VacancyDocument](../../archive-web/vacancy-document.js) подключён перед `archive.js` и разрешён в статических assets [archive_routes](../../src/archive_routes.py). В блоке «Полный сохранённый текст» по умолчанию показывается читаемый вид: заголовки, абзацы, Markdown-списки, выделения, код и HTTP(S)-ссылки. Переключатель «Исходный текст» возвращает точный `data.text`, включая название и компанию. Для фрагментов сохраняется предупреждение о неполноте.

У старых описаний, в которых сборщик свёл переносы к пробелам, распознаётся ограниченный словарь явных заголовков (обязанности, требования, стек, условия и т. д.). UI сообщает об этом восстановлении. Произвольные предложения не превращаются в обязательные требования, списки не выдумываются, повторы не удаляются. Текст в архиве, версии, входы анализа и рейтинга от переключения представления не изменяются. HTML выводится как текст; изображения, скрипты и произвольные HTML-атрибуты не исполняются.

[HH content script](../../hh-research-extension/content.js) при последующих чтениях сохраняет границы абзацев, заголовков и пунктов списка вместо сведения всего описания в одну строку. Скрытые элементы, формы и поля ответов исключаются. Старые снимки автоматически не пересобираются.

Проверено на сохранённой вакансии Senior ML Engineer (Kandinsky), включая оба режима. Screenshot: `AI Vacancies Replies/vacancy-structured-view.png`. После изменения: **373 Python / 330 JS** тестов проходят, журнал JS-ошибок в живой проверке пуст. Тесты: [vacancy-document.test.mjs](../../hh-research-extension/vacancy-document.test.mjs), [core.test.mjs](../../hh-research-extension/core.test.mjs).

## Отклики

[workflow.js](../../archive-web/workflow.js): поиск по компании/названию, переключатели **В работе / На проверку / Все**, свернутые фильтры этапов и источники/уведомления. Фильтр внимания использует `workflow_state` из [workflow_routes](../../src/workflow_routes.py), не только общий статус записи.

Карточка начинается с **Следующий шаг**. Кнопка прокручивает к нужному блоку (письмо, форма, проверка, переписка, сверка неизвестного результата), сама не генерирует и не отправляет данные. История, точные версии, обновление контекста, параметры письма и уже пройденный редактор раскрываются по запросу. Три режима работы с письмом сохранены; дублирующие кнопки убраны. Согласия, одноразовые подтверждения, revision/TTL, recovery и правила Chrome остаются в прежнем application layer.

## Проверка

- Изолированный Python suite: **373 теста**, включая новые режимы навыков; JS suite: **323 теста**. Новые Today regression cases проверяют текущий CV/attention, отсутствие eager API при показе и перевод старой ошибки Chrome.
- HTML: корректная вложенность, нет дублирующихся ID.
- Live: проверены четыре раздела, открытие карточки сайта компании без отправки, скрытые настройки ранжирования, историческая диагностика HH. JS error log пуст.
- Существующие реальные ошибки доступности HH, неподтверждённое поднятие и ограничение автозаполнения сайтов не маскируются как успех. Платные модели, рассылки и отклики при QA не запускались.

Снимок Today: `AI Vacancies Replies/today-ux-refactor.png`. Срез навыков с тремя основами плана: [Skills Intelligence](../architecture/skills-intelligence.md).

### Resume pages with text flows and vacancy reading (2026-10-20)

See [Resume comparison and reading workspace](resume-comparison.md) for the implemented document + alluvial ribbon mode, matching limits, historical snapshots, imports, vacancy reader tabs and shared per-vacancy skill priorities. Native macOS packaging remains a possible adapter; the shared application layer and browser execution stay independent of the presentation.

### Opportunity Map PNG export

The analytics map and compact vacancy map provide **Скачать PNG · с осями**. The export clones the full SVG viewBox, including both axis titles, ticks, threshold lines and all plotted points. Computed SVG styles are embedded before rasterization. The PNG includes a caption, sample counts, current analytics filters and category legend; the bounded export geometry limits raster memory. A downloadable PNG is accompanied by an in-page preview. Live verification produced a 2000 × 1488 PNG with both axes intact.
