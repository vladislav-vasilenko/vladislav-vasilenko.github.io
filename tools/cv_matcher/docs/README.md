# Документация Career Intelligence Platform

**Начать следующую работу с [отчёта о фактическом состоянии — 20.10.2026](handoff/2026-10-20-agent-planning-brief.md).** Он отделяет реализованное от планов и live-проверок; включает последние пользовательские правки и входные данные для очереди откликов. Новая фаза пока не запускается.

| Документ | Зачем читать |
|---|---|
| [Handoff для планировщика](handoff/2026-10-20-agent-planning-brief.md) | Основной актуальный пакет для передачи другому агенту |
| [Фактическая архитектура](architecture/current-state.md) | Подробная исходная карта стека и потоков, с датированными уточнениями |
| [Целевое состояние](architecture/target-state.md) | Архитектурные границы и цели; это не свидетельство готовности |
| [Разрывы](architecture/gap-analysis.md) | История findings и текущие незавершённые пункты |
| [Идеи будущего развития](ideas/README.md) | Тематический backlog, приоритеты, связь с текущим кодом и полные исходные предложения |
| [Roadmap](roadmap.md) | Материал для пересмотра плана, не автоматический список к исполнению |
| [Структура проекта и автозаполнение](architecture/repository-and-autofill.md) | Причины остановки corporate worker, границы двух расширений, рефакторинг workflow и проверки |
| [Общий application layer](architecture/application-layer.md) | Реальные API/MCP/task controls и их ограничения |
| [Telegram E2E](integration/telegram-career-e2e.md) | Что фактически прошло/не прошло живую проверку |
| [Бесплатное поднятие HH-резюме](integration/hh-resume-bump.md) | Настройки Web/Telegram, очередь Chrome, cooldown и границы проверки |
| [Аналитика, Telegram и последние правки](integration/career-analytics-telegram.md) | Карта/воронка, taxonomy, batch/offline, manual marks, проверки |
| [Пользовательский flow Telegram](telegram_user_flow.md) | Меню, ожидание Chrome, продолжение сценария |

Полные Python проверки запускать изолированно: `.venv/bin/python scripts/test-isolated.py`. JS: `node hh-research-extension/scripts/check.mjs`. Production `.cache`, `.env`, tokens и sessions не включать в пакет документации.

- [Гибридный сбор: Python и Chrome, проверенное состояние](architecture/hybrid-collection.md)
- [Надёжность сбора и дозагрузка архива — обновление 22.10.2026](architecture/hybrid-collection.md#рефакторинг-надёжности--22102026)
- [Идея: восстановление DOM-адаптеров через Luna](ideas/llm-adapter-repair.md)

- [Разбор нескольких резюме под трек: API и без API](architecture/resume-portfolio-review.md)

- [Карьерная траектория: редактируемые этапы, подтверждения и черновик под вакансию](architecture/career-trajectory.md)

- [Два проекта: портфолио и подготовка откликов](../../../docs/workspace.md)
- [Сущности и связи карьерной системы](../../../docs/career-domain-model.md)
