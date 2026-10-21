# Telegram → Personalized Search → Luna → Draft → Chrome → Human Review

Состояние 19.10.2026. Backend API 13, расширение 0.11.16. Общая бизнес-логика остаётся в существующем Python-приложении и SQLite. Дополнительные сервисы, очереди, базы, MCP tools и зависимости не добавлены.

## Execution path и сохранённое состояние

| Переход | Реализация | Долговременное состояние |
|---|---|---|
| Telegram → owner/intent | [`WorkflowBot.update`](../../src/workflow_bot.py), [`career_orchestrator.converse`](../../src/career_orchestrator.py) | owner/private-chat guard; `settings:agent-request:*` |
| Условия поиска | [`career_search_scope`](../../src/career_search_scope.py) | компании, период публикации, темы и размер подборки в `discovery_runs.payload.scope`; отдельная `ranking_goal`, без смены глобальной цели |
| Search → Chrome | [`discovery.start/queue_source/advance`](../../src/discovery.py), [`wfCollect`](../../hh-research-extension/discovery-worker.js) | `discovery_runs`, `browser_commands`, checkpoint курсора и attempted IDs |
| DOM → архив | [`runHHCrawl`](../../hh-research-extension/hh-crawl.js), [`runBoardCrawl`](../../hh-research-extension/board-crawl.js), [`ArchiveStore`](../../src/archive_store.py) | entities/versions/scans, исходные ID и URLs; факт чтения выдачи отдельно от возраста полного текста |
| Архив → embeddings/ranking | [`rank_vacancies`](../../src/extension_ranking.py), [`AnalysisStore`](../../src/analysis_store.py) | SQLite embeddings/cache bindings/ranking_runs; пакеты до 200, checkpoint каждого пакета |
| Luna → подборка | [`discovery.rank_run`](../../src/discovery.py), [`skill_analysis.analyze/cached`](../../src/skill_analysis.py) | `skill_analyses` с цитатами и версиями; opt-in `luna_top:0..10` + allow_api; started checkpoint перед запросом |
| Подборка → объяснение/feedback | [`CareerApplication.finish_digest/candidates`](../../src/career_application.py), [`career_recommendations`](../../src/career_recommendations.py) | recommendation refs, последние упорядоченные refs, feedback с CV hash в settings; durable outbox |
| Выбор → подготовка | [`application_preparation.enqueue/advance`](../../src/application_preparation.py) | новая таблица `application_preparations` в той же SQLite: queued → analyzing → drafting → waiting_chrome/awaiting_user/needs_input |
| Письмо | [`application_conversation.discuss`](../../src/application_conversation.py) | application_chat_requests/discussion/draft revisions; вопрос модели не заменяет проверенный черновик |
| Chrome → заполненная форма HH | [`CareerApplication.prepare_form`](../../src/career_application.py), [`wfPrepare`](../../hh-research-extension/hh-workflow.js) | существующая prepare-команда, fingerprint формы, CV ID, анкета и значения в application_workflow |
| Human review → CRM | [`WorkflowBot.preview`](../../src/workflow_bot.py), [`WorkflowMixin.intent/approve/claim_approval`](../../src/application_workflow.py) | одноразовое разрешение на 15 минут для точных CV/письма/формы/ответов; до отправки CRM остаётся preparing |
| Доставка/прогресс | [`agent_progress`](../../src/agent_progress.py), [`delivery_store`](../../src/delivery_store.py), [`telegram_presentation`](../../src/telegram_presentation.py) | worker counters, sequence, outbox receipt/message_id; редактирование исходного прогресс-сообщения, HTML escaping |

MCP, Web и Telegram пользуются существующим application layer. Часть HTTP routes и старых UI по-прежнему обращается к доменным модулям напрямую; это не означает, что все handlers уже полностью перенесены в один facade. Рабочий путь использует SQLite, а не старую ChromaDB. Миграция старой ChromaDB не требуется для этого сценария и не выполнена.

## Исправления критических разрывов

1. HH crawler возвращал только ID текущей выдачи, хотя читал ещё старую очередь неполных карточек. Теперь передаются все прочитанные/reused IDs; membership scan содержит только реально увиденные в выдаче ID.
2. Старые pending IDs ошибочно прибавлялись к «найдено в выдаче». Счётчик теперь отражает текущие listing IDs.
3. HH сбор продолжается порциями автоматически: attempted IDs предотвращают бесконечное повторение ошибок; переход допускается только при том же origin/path/фильтрах. Общий лимит API-off по умолчанию 20 страниц/1000 описаний на источник. Для сохранённого API-on без новых общих лимитов прежний бюджет pages/details не расширяется. Общие лимиты редактируются в вебе.
4. Свежесть выдачи не продлевает возраст описания. Для подборки допускается описание моложе суток + подтверждение присутствия моложе 30 минут, если текст не dirty. Изменённое/суточное/закрытое не считается свежим.
5. Счётчики продолжаемых порций суммируются; повторы одинакового checkpoint не увеличивают итог. Для кэша передаются ID, чтобы не суммировать повторно одни и те же карточки.
6. Сложный запрос с четырьмя компаниями, четырьмя темами, семью днями и десятью результатами сохраняет ограничения. Неизвестная дата публикации исключает вакансию из строгого временного фильтра; дата сбора её не заменяет.
7. В Telegram появились следующие шаги, API/offline ветки, импорт JSON разбора и письма, safe bold/эмодзи, рекомендации с объяснением и feedback. «Подготовь отклики на первые две» использует сохранённые refs последней подборки, а не угадывает IDs/CV.
8. Подготовка выполняется общим backend scheduler, независимо от открытого Telegram. Перед платными фазами сохраняется started marker; неоднозначный запрос после сбоя не повторяется автоматически. Повтор старой кнопки не создаёт новую оплату. Письмо с needs_user не применяется и не отправляется в prepare.
9. Конфликт Giga start-token изолируется в `integration_conflicts`: корректные HH статусы/сообщения сохраняются, токен не перепривязывается, владелец получает одно уведомление. Прочие ошибки БД по-прежнему откатывают транзакцию.

## Как читать рекомендации

`qualification_fit.semantic_similarity` — близость текста к CV, **не покрытие навыков**. При готовом Luna-разборе отдельно доступны оценка требований по рубрике и точные цитаты. `career_alignment` хранит близость к цели и пояснение Luna, если оно есть. Application priority сохраняет исходный рейтинг и ограниченную явную поправку +0.03 для ⭐. 👎 исключает позицию для текущей версии CV. Это начальная эвристика; качество не измерено по найму/конверсии.

API-off никогда не включает платный Luna/embeddings автоматически. Если нет векторов, доступны прочитанные карточки без подтверждённого рейтинга и подготовка без API. Чтобы Luna выполнялась **до** рекомендаций, владелец явно задаёт `luna_top` и разрешает API в «Сегодня → Поиск по расписанию». Иначе подробный разбор запускается после выбора вакансии. Наличие NL-команды не выдаёт разрешения на расходы.

## Проверки и границы доказательства

Полный изолированный прогон: **305 Python / 292 JavaScript**, успешен. Основной новый набор: [`test_career_milestone.py`](../../src/tests/test_career_milestone.py), 16 тестов. Он исполняет настоящий backend/application code с временной SQLite; внешние модели, Telegram transport и Chrome DOM заменены fixtures. [`preparation-bridge.mjs`](../../hh-research-extension/fixtures/preparation-bridge.mjs) исполняет настоящий `wfPrepare`; fixture покрывает заполнение и prepared receipt, без submit. Это не живое подтверждение совместимости формы HH.

| Проверка | Подтверждение |
|---|---|
| Точный запрос пользователя → 4 источника/период/темы/limit | `test_exact_user_query_persists_four_sources_period_and_topics_across_restart` |
| Telegram → search → real ranker → Luna validation → draft → actual wfPrepare → Telegram preview → CRM preparing | `test_telegram_search_luna_draft_real_browser_worker_then_human_review_no_submit` |
| Двойная кнопка | одна application_preparations и prepare; старый revision отвергается |
| Chrome offline/sleep, перезапуск | `test_career_agent`: 8 часов ожидания, восстановление чтения, поздние receipts, пауза не снимается |
| Luna error / неопределённый платный запрос | `test_model_failure_and_restart_preserve_preparation_without_paid_repeat`, `test_ambiguous_processing_is_not_replayed_and_offline_never_calls_model` |
| Устаревшее/чужое подтверждение | `test_workflow.test_expired_permission_or_different_worker_never_claims`; owner guard в milestone/telegram flow tests |
| Закрытая вакансия / изменённый CV/JD / новая редакция | `test_workflow.test_closed_changed_cv_and_changed_job_block_approval`, `test_permission_exact_content_single_use_and_edit_revokes` |
| Частичный сбор, смена фильтра, backlog, cached JD | milestone tests + `crawl.test.mjs` |
| Конфликт Giga / replay / неожиданный DB failure | `test_giga_link_conflict_isolated_valid_statuses_commit_and_notify_once` |

Команды: `.venv/bin/python /tmp/test_career_isolated.py` (временная копия без секретов/production DB; сценарий запуска воспроизводит обычный `unittest discover -s src/tests -t .`), `node hh-research-extension/scripts/check.mjs`. Прямой запуск старой полной Python suite из рабочего каталога нежелателен: некоторые legacy тесты создают app без отдельного archive_path.

## Живая проверка 19.10.2026

Точный запрос пользователя отправлен в собственный Telegram-бот Bani Bot. Сохранён запуск `f95ef3c54ae41c65b6f75c40` с четырьмя компаниями, четырьмя направлениями, периодом 7 дней и лимитом 10. Chrome действительно получил задания; в SQLite сохранены 24 полных описания: 4 Авито, 20 Ozon. У всех 24 отсутствовала подтверждённая дата публикации, поэтому строгая подборка за семь дней пуста. Платных запросов и реальных отправок откликов не было. Это подтверждает живую часть Telegram → очередь → Chrome → SQLite, а не весь Definition of Done.

Яндекс: старая ссылка `?professions=ml-developer` перенаправляет на `/jobs/professions/ml-developer`; исправлена узкая проверка этого перехода без ослабления проверки остальных адресов/фильтров. В отдельной проверочной вкладке ресурсы `jobs.s3.yandex.net` также завершались сетевыми ошибками, включая `ERR_ADDRESS_UNREACHABLE` и тайм-аут. Сбер: `ERR_ADDRESS_UNREACHABLE`; VPN не менялся. Эти источники нельзя записать как успешно прочитанные.

Ozon: в Chrome проверено, что нативное поле поиска меняет URL на `?search=ML` (20 результатов) и `?search=PyTorch` (6 результатов); общий список показывал 347 вакансий. По последнему пожеланию пользователя автоматический ML-поиск выполняет **только два отдельных запроса ML и PyTorch**, с объединением ID и однократным чтением полного текста. Аналитические темы остаются в цели ранжирования. Явный search в переданной ссылке сохраняется. Объединение запросов и общий бюджет проверены fixtures, полный повтор автоматического Ozon-сбора после этой правки ещё не является живым доказательством.

После обновления подтверждены health API 13 и версия установленного расширения 0.11.16. Плановый поиск был поставлен на паузу через общий task control и возобновлён после перезапуска backend/бота с тем же ID `daced96e278277dba58f9633`; история управления содержит pause revision 1 и resume revision 2. Новая команда Chrome сохранена в очереди с `search_terms=[ML, PyTorch]`; режим API остался выключенным. Возобновление очереди не считается завершённым чтением источника.

## Что ещё не считать готовым

- Полный живой сценарий на всех четырёх карьерных сайтах и HH, с текущими DOM/данными/моделью, пока не подтверждён. Offline fixtures не заменяют такую проверку.
- На company boards пока нужно открыть анкету и передать её через панель. Согласованный перенос полей реализован; финальная отправка вручную. Универсальный автоматический open-form/submit отсутствует.
- Отдельные board crawlers могут закончить partial из-за неподдержанной load-more/pagination; автоматическое продолжение checkpoint реализовано для HH.
- Автовыбор разных CV по каждой вакансии не реализован: используется явно выбранный CV; замена не угадывается.
- Единого TTL для всех Giga answer/start approvals ещё нет; HH/company permissions имеют 15 минут и проверку версии.
- Без API и недостающих embeddings/Luna нельзя обещать персональный рейтинг всех новых текстов. Копирование промпта — сознательная offline ветка, а не автоматический E2E.
- Локальные процессы и Chrome не работают во время полноценного сна ноутбука. Задачи ждут доступного backend/executor; Telegram не запускает физически спящий Chrome.

## Следующие этапы

**P0:** завершить контролируемую живую проверку HH до preview, затем по одному company board (Yandex → T-Bank → Avito → Ozon → Sber); записывать фактическое подтверждение каждой capability. Закрыть generic open-form/capture и продолжение board pagination; отдельная отправка только после конкретного owner approval и устойчивого success detector.

**P1:** source provenance и устойчивый список результатов на всех клиентах, явный выбор/рекомендация CV, общая TTL-политика Giga, измерение ranking quality на размеченной выборке.

**P2:** конверсия/карьерная аналитика, обоснованный always-on режим. Self-healing crawlers, новый Telegram Client API и MCP Apps UI не входят в текущую итерацию.
