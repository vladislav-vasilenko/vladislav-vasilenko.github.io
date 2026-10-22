# Personal Portfolio & Career Workspace

Два связанных проекта: публичное профессиональное портфолио и локальная система подготовки качественных откликов.

| Проект | Где находится | Запуск |
|---|---|---|
| Личное портфолио · TypeScript/Vite | `src/`, `content/`, `public/` | `npm run portfolio:dev` |
| Career Workspace · Python/SQLite/Web/Chrome | `tools/cv_matcher/` | `npm run career:dev` |

[Структура и совместная работа проектов](docs/workspace.md) · [Сущности и связи системы](docs/career-domain-model.md) · [Документация Career Workspace](tools/cv_matcher/docs/README.md)

`workspace.projects.json` задаёт явные точки входа. `npm run workspace:list` показывает их, `npm run workspace:check` проверяет структуру.

Публичный CV передаётся в локальный сервис через экспорт выбранной версии в Markdown и проверяемый импорт. Частные подтверждения, трудовые документы, история откликов и токены остаются локальными. Автоматической публикации правок нет.

`cv-api/`, `matcher.html`, `scrape.html` и `autofill-extension/` — отдельные/исторические части. Их границы описаны в [карте репозитория](REPOSITORY_MAP.md); они не заменяют локальный сервис на порту 8788.
