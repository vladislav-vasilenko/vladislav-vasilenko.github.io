# Career Intelligence — документация

Актуализировано 24.10.2026 по исходникам. Основной локальный сервис — `resume_import_server.py` (FastAPI, `127.0.0.1:8788`), веб — `archive-web`, исполнитель Chrome — `hh-research-extension`. Версия исходников расширения **0.13.2**, HTTP health **14**, протокол дозагрузки **2**. Это единственное место, где документация называет текущие версии; загруженная в Chrome версия проверяется отдельно на странице диагностики расширения.

## Начать здесь

| Задача | Документ |
|---|---|
| Запустить сервис и пройти основной сценарий | [Краткое руководство](applicant_quickstart.md) |
| Понять компоненты и ограничения | [Фактическая архитектура](architecture/current-state.md) |
| Увидеть сущности и связи | [Модель данных](architecture/domain-model.md) |
| Сбор, полные описания и резервный способ | [Гибридный сбор](architecture/hybrid-collection.md) |
| Эксплуатация, проверки, ошибки и резервные копии | [Операционное руководство](operations.md) |
| Секреты, `.env`, индекс git и ротация | [Безопасность](security.md) |
| Найти любой документ и его статус | [Каталог](catalog.md) |
| Что реализовано и что делать дальше | [Roadmap](roadmap.md), [обновление 24.10](release_2026_10_24.md) |

## Пользовательские сценарии

- [Редактируемая карьерная траектория](architecture/career-trajectory.md): цель → этапы → критерии → подтверждения → подбор вакансий/CV.
- [Навыки и доказательства](architecture/skills-intelligence.md): обязательность требований, приоритет ближайшего действия, практика отдельно от обучения.
- [Сравнение документов и потоки чанков](integration/resume-comparison.md); [разбор нескольких CV, документов и хронологии](architecture/resume-portfolio-review.md).
- [Поиск, оценка и отклик](workflow_and_adapters.md), [CRM откликов](application_crm.md), [режимы рейтинга](crm_ranking_modes.md), [формы и адаптеры](architecture/repository-and-autofill.md).
- [Архив, версии и векторы](local_archive.md), [панели на карьерных сайтах](career_widgets.md), [компании и регионы](usage/company-filter.md).
- [Команды вакансий, контакты и исследовательские стримы](architecture/vacancy-teams.md).
- [Общий application layer и MCP](architecture/application-layer.md); [Telegram](telegram_user_flow.md), [расписание и напоминания](integration/telegram-notifications.md), [userbot Telethon](telegram_userbot.md).

## Интеграции

- [LinkedIn — профиль, вакансии, чаты и контакты](integration/linkedin-adapters.md) и [анализ переписки](integration/linkedin-chat-advice.md): управление из отдельного раздела; границы живой проверки указаны по capability.
- [GitHub Runs → SQLite и HH → портфолио](integration/github-import-and-portfolio.md).
- [Публичные визуализации, мобильный сайт, SEO и PWA](integration/public-portfolio.md).
- [Бесплатное поднятие HH-резюме](integration/hh-resume-bump.md).
- [Два проекта в одном репозитории](../../../docs/workspace.md), [публикация портфолио](../../../docs/portfolio-publication.md).

## Как читать статусы

«Реализовано» означает наличие соответствующего кода. Автотесты с подменами не доказывают работу изменившегося внешнего сайта. Живые проверки фиксируются отдельно с датой и объёмом. Размеры тестовых наборов указываются только в [operations](operations.md); числа в релизных заметках относятся к их датам.

`release_*.md` — история релизов; `ideas/` — backlog; `ideas/sources/` — сохранённые исходные тексты пользователя, не инструкции к исполнению. ADR описывают решения; уточнения статуса реализации находятся в начале документа. `gap-analysis.md` и `target-state.md` — планы со срезом 19–22.10; фактическое состояние сверяется с [current-state](architecture/current-state.md). Удалённые 24.10.2026 устаревшие документы перечислены в конце [каталога](catalog.md).

## Общие границы

SQLite, `.env`, tokens, сессии и трудовые документы остаются локально и никогда не попадают в индекс git ([правила и проверка](security.md)). Публичный сайт получает только разрешённую JSON-проекцию. GitHub Actions не хостит личную SQLite. Просмотр, сравнение и экспорт промптов не вызывают модели; новые embeddings и API-разборы имеют отдельные действия. Отсутствие текста/упоминания/ответа не доказывает закрытие вакансии, отсутствие навыка или отказ.

Из корня репозитория: `npm run workspace:check`, `npm run career:test`, `npm run career:check`, `npm run portfolio:test`, `npm run portfolio:build`. Полный Python-набор запускается изолированно; инструкции и границы проверок — в [operations](operations.md).
