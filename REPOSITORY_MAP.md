# Карта репозитория

Основная точка входа: [README](README.md). [Как устроено портфолио](docs/workspace.md) · [Сущности системы](docs/career-domain-model.md). Машиночитаемые пути: [workspace.projects.json](workspace.projects.json).

В репозитории несколько связанных продуктов, а не один общий frontend:

- `src/` + `content/` + `public/` — публичное CV/портфолио на TypeScript/Vite; `dist/` — производная сборка.
- `cv-api/` — отдельные облачные функции публичного проекта.
- `autofill-extension/` — сохранённый legacy Workday companion. С версии 1.1.1 не внедряется на все HTTPS-сайты и не является исполнителем корпоративной очереди.

Для персональных форм Yandex/Sber/Ozon/Avito использовать локальный Career workflow и основной Chrome executor. Не смешивать публичное CV с выбранным снимком резюме, не объединять manifests и не удалять `content/` как «дублирующий код».
