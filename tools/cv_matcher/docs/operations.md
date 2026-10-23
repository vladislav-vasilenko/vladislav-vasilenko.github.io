# Запуск, проверка и диагностика

Актуализировано 22.10.2026. Все пути `.cache/...` ниже относятся к `tools/cv_matcher`. Для первого запуска — [quickstart](applicant_quickstart.md).

## Команды из корня репозитория

```sh
npm run workspace:check
npm run career:dev
```

Локальный основной сервис: <http://127.0.0.1:8788/>. Legacy `server.py:8787` не обслуживает персональный архив. Зависимости Career Workspace: `uv sync` из `tools/cv_matcher`; портфолио — зависимости корневого package manifest. MCP extra устанавливается отдельно: `uv sync --extra mcp`.

Проверки запускаются отдельно от рабочего сервера:

```sh
npm run career:test
npm run career:check
npm run portfolio:test
npm run portfolio:build
```

`career:test` использует `scripts/test-isolated.py`: временная копия исходников без рабочей `.env`, `.cache`, sessions и credentials. Прямой `unittest discover` из рабочего каталога не использовать как стандартный полный прогон. `career:check` проверяет generated adapters, синтаксис и Node tests. Реальные CLI-scraper тесты не запускать как незаметную часть offline regression.

## Что проверяется

| Контур | Точки проверки |
|---|---|
| Архив/версии/дедупликация | `src/tests/test_archive.py`, `test_collection_contract.py` |
| Hybrid/backfill/progress | `test_hybrid_collection.py`, `test_collection_backfill.py`, `test_agent_progress.py` |
| Траектории/навыки | `test_career_trajectory.py`, `test_career_skills.py` |
| CV/дополнительные документы | `test_resume_portfolio.py`, `test_resume_files.py`, `test_resume_documents.py` |
| GitHub Runs/импорт | `test_github_collection.py` |
| Публичная проекция | `test_portfolio_publication.py`, `test_portfolio_visuals.py`, корневые `tools/tests/` |
| Исполнитель/адаптеры | `hh-research-extension/scripts/check.mjs` |

Последний зафиксированный полный backend-прогон при подготовке портфолио: **472 Python tests**; JS-контура — **385 tests**. При исправлении мобильного меню повторно прошли **11 portfolio tests** и production build. Числа описывают конкретные прогоны, а не гарантированный размер будущего набора. Обновление документации не запускает платные модели или реальные отклики.

## Диагностика по симптомам

| Симптом | Проверить | Следующее действие |
|---|---|---|
| Сайт 8788 не открывается | Процесс основного сервиса, порт, лог `.cache/runtime/local-service.log` | Запустить основной сервис; не подменять его legacy 8787 |
| После restart нет доступа | Cookie-сессия была в памяти | Открыть сервис через новую одноразовую ссылку расширения |
| `waiting_chrome` | Открыт ли Chrome, выданы ли нужные host permissions, свежий heartbeat | Подключить и перезагрузить worker; задача ожидания не равна успешному сбору |
| Дозагрузка стоит на HH | Загруженная версия worker и protocol 2 | Reload расширения 0.11.22+, смотреть source reason/progress |
| `Resource::kQuotaBytes quota exceeded` | Соединение с SQLite, режим сбора, старая версия worker | Сначала сохранить/синхронизировать доступные данные; обновить расширение. Не очищать хранилище до проверки архива |
| Карточек много, полных JD мало | Статусы full/snippet/needs_review, ошибки/ограничения источника | Запустить дозагрузку; login/CAPTCHA/unsupported layout требуют отдельного решения |
| HH negotiations открыт долго | Текущая sync-команда, heartbeat, deadline и причина ошибки | Различать фоновую синхронизацию откликов и сбор вакансий |
| GitHub Run успешен, данных нет | Import cursor, artifact run/attempt, ошибки источников | Отдельно запустить импорт; success workflow не равен полным данным |
| Title сайта старый | Основной CV, preview JSON, commit SHA, Pages Run и браузерный cache | Проверить последовательно источник → публикацию → deployment |
| Сайт пустой | Pages source и артефакт dist | Использовать deploy workflow; не отдавать TypeScript из root |
| Все точки Learning Map имеют один X | Тип действия и текущая оценка часов | Равная оценка даёт равный X; не рисовать выдуманный разброс |
| LinkedIn не доступен в расширении | Capability ещё не реализована | См. [план LinkedIn](integration/linkedin-adapters.md), старый Python scraper её не заменяет |

## GitHub Pages

Workflow `.github/workflows/deploy.yml` собирает публичный сайт. Проверить итоговый `conclusion`, head SHA и живые `/`, `/ru/`, `hh-experience.json`, manifests и `sw.js`. Ожидание Actions/окружения не означает ошибку Vite; сначала прочитать job/status. Настройки видимости, защиты окружения и permissions не менять ради обхода очереди.

Автопубликация JSON в локальном сервисе может создавать новые коммиты main независимо от рабочего checkout. Перед push получить актуальный remote, проверить diff и объединить историю без force push. `.env`, личная SQLite и credential files не должны попадать в stage. Статус «JSON опубликован» и «новый Pages сайт доступен» показывают разные стадии.

## Резервные копии и восстановление

История и векторы находятся в SQLite. Для полной переносимой копии остановить процессы записи и сохранить согласованное состояние БД либо использовать корректный SQLite backup API. Простое копирование одного файла во время WAL-записи может потерять последние изменения. Хранить резервные копии приватно.

JSON-экспорт архива содержит приватные данные; это не публичная проекция портфолио. Обратное восстановление в расширение объединяет записи и не является восстановлением всей серверной БД из произвольного JSON. Проверить количество сущностей/версий, источники и отсутствие повторных действий после восстановления. Перенос credentials выполняется отдельно.

## Границы проверки

Локальная авторизация и флаги health подтверждают доступность реализации, не успешность каждой внешней capability. DOM площадок меняется. Чтение, заполнение и подтверждённая отправка проверяются отдельно. Для нового adapter нужны очищенные fixtures и controlled live read; не использовать настоящую отправку или платный запрос как автоматическую проверку документации.
