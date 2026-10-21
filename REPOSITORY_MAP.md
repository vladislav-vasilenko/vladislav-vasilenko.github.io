# Карта репозитория

В репозитории несколько связанных продуктов, а не один общий frontend:

- `src/` + `content/` + `public/` — публичное CV/портфолио на TypeScript/Vite; `dist/` — производная сборка.
- `cv-api/` — отдельные облачные функции публичного проекта.
- `tools/cv_matcher/` — персональный Career Intelligence: Python/SQLite backend, локальный Web, Telegram/MCP и Chrome workflow.
- `autofill-extension/` — сохранённый legacy Workday companion. С версии 1.1.1 не внедряется на все HTTPS-сайты и не является исполнителем корпоративной очереди.
- `tools/cv_matcher/hh-research-extension/` — основной исполнитель локального сервиса для HH и поддержанных карьерных сайтов.

Для персональных форм Yandex/Sber/Ozon/Avito использовать локальный Career workflow и основной Chrome executor. Не смешивать публичное CV с выбранным снимком резюме, не объединять manifests и не удалять `content/` как «дублирующий код».

[Подробный аудит, причины ошибок и план устранения дублирования](tools/cv_matcher/docs/architecture/repository-and-autofill.md).
