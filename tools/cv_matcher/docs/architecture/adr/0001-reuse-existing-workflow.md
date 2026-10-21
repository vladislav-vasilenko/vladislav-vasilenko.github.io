# ADR 0001 — Career Agent поверх существующего domain workflow

Дата: 19.10.2026. Статус: рекомендовано по результатам аудита; новый agent runtime не внедрён.

## Контекст

Уже есть [ApplicationStore](../../../src/application_store.py), [WorkflowMixin](../../../src/application_workflow.py), [discovery.start/advance](../../../src/discovery.py), [WorkflowBot](../../../src/workflow_bot.py), браузерные workers и durable receipts. Очередь умеет `discover`, `collect`, `resume_import`, `refresh`, `sync`, `prepare`, `execute`, `career_fill`. Согласования фиксируют версии/форму/текст и расходуются однократно. Построение второй CRM, command queue или approval engine продублирует уже проверенные инварианты.

## Решение

Добавлять тонкое планирование над существующими функциями. Backend остаётся владельцем состояний, очереди, проверок, разрешений и истории. «Агент» выбирает допустимый следующий шаг и предлагает контент; не переписывает SQL/state machine в MCP tool и не управляет DOM произвольным JS.

Первый сценарий: поиск → уже имеющийся рейтинг → Luna analysis → CRM case → browser prepare → preview владельцу → ожидание human approval. Использовать существующий pending digest/discovery и возвращать их IDs, а не создавать вторую оркестрацию коллекций. Повторный tool call должен возвращать текущее состояние/кэш либо конкретную причину нового действия.

Новые абстракции вводить только на подтверждённых швах: typed contracts, correlation/context reference, capabilities и model cost policy. Agent framework не нужен для линейного bounded сценария. Сложный граф/фреймворк имеет смысл только после измеренной необходимости ветвления и воспроизведения.

## Рассмотренные альтернативы

- Новый Application Agent с собственной БД/очередью: отклонён — дублирование, две правды о разрешении и отправке.
- LLM непосредственно кликает browser tools: отклонён как основной product executor — нет общего single-use intent и recovery; CUA остаётся инструментом разработки/живой диагностики.
- Всё оставить независимыми кнопками: недостаточно — пользователь не получает общего next action и наблюдаемого жизненного цикла.

## Проверка и последствия

[test_architecture_flow.py](../../../src/tests/test_architecture_flow.py) проверяет существующие backend seams на временной SQLite: discovery command/result → реальный ranker с fake embedding backend → настоящий analysis validator с fake Luna → routes make/draft/prepare → browser prepared/result → needs_approval → fake owner notification. Настоящие Chrome/MCP/Telegram/OpenAI в тесте не участвуют. До разрешения отсутствует `execute`; cookie UI не может забрать browser command.

Это подтверждает переиспользуемость backend. Тест не доказывает наличие MCP сервера, универсального company submit или единого сохранённого trace ID. Эти границы остаются задачами [roadmap](../../roadmap.md).
