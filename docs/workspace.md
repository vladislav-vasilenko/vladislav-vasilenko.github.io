# Портфолио

Репозиторий содержит сайт резюме на TypeScript и Vite. Исходники в `src/`, контент резюме
в `content/`, публичные файлы в `public/`. Сайт собирается и развёртывается через
`.github/workflows/deploy.yml`.

```sh
bun install
bun run dev
bun run build
node --test tools/tests/*.test.mjs
```

`workspace.projects.json` описывает точки входа сайта. Команда `npm run workspace:check`
проверяет пути и индекс Git на локальные секреты. Экспорт CV в Markdown, PDF и DOC доступен
в интерфейсе сайта.

Career Intelligence поддерживается отдельно. Портфолио не запускает его сбор, тесты или RAG.
Опубликованные ранее файлы вакансий и опыт HH остаются доступными как статические данные.
