# ADR 0002 — Назначение SQLite и ChromaDB без преждевременной миграции

> Сверка 22.10.2026. Решение сохраняется. Реализован [GitHub artifact → SQLite importer](../../integration/github-import-and-portfolio.md); это не миграция CRM в Chroma. Публичный JSON и личная БД имеют разные контракты.

Дата: 19.10.2026. Статус: сохранить оба существующих назначения; миграция не выполнялась.

## Факты

Личная SQLite `.cache/applications/state.sqlite3` — источник состояния текущего веба, расширения и Telegram. Она уже хранит не только транзакции, но и embeddings: [AnalysisStore](../../../src/analysis_store.py), [CachedEmbeddings](../../../src/resume_source.py), [rank_vacancies](../../../src/extension_ranking.py). Для рейтинга используются прямые cosine/dot comparisons нормализованных chunks, без отдельного ANN index.

Во время аудита read-only snapshot показал: 6 CV, 1969 вакансий, 2307 векторов `text-embedding-3-small` размерности 1536, 2399 chunk bindings и 21 ranking run. Числа изменяемы; это диагностический срез, не норматив/метрика качества. Он вместе с вызовами кода подтверждает, что семантическое сравнение текущим продуктом не потеряно.

`chroma_db/chroma.sqlite3` содержит одну collection `vacancies`, размерность 1536, 2453 embedding rows. Это внутренняя SQLite Chroma, **не тот же файл**, что application archive. [RAGDatabase](../../../src/rag_db.py) использует Chroma cosine collection/query и whole-document representation с title/description/location, может выбирать Ollama/OpenAI/cv-api backend. Совпадение 1536 измерений не доказывает совпадение модели, preprocessing и namespace конкретных сохранённых векторов.

Старые [server.py](../../../server.py)/[cv_matcher.py](../../../cv_matcher.py)/batch scripts используют Chroma и JSON exports. Основной `:8788` ranking/бот напрямую Chroma не запрашивает. В коде **уже есть частичный мост**: [BaseScraper.fetch_jobs](../../../src/scrapers/_base.py) вызывает [normalize_browser_rows / archive_browser_rows](../../../src/collection_contract.py) для поддержанных company records, затем результат может индексироваться старым RAG path. Поэтому контуры не полностью изолированы, но общей транзакции/единого векторного пространства и синхронизации результатов анализа у них нет. HH и неизвестные источники этим мостом автоматически не охвачены.

## Решение

1. Считать SQLite archive авторитетным источником личных CV/JD versions, application/CRM, approvals, commands, observations и результатов текущего ranking/analysis.
2. Сохранить Chroma как существующий индекс старого/batch/public discovery пути. Не объявлять его отключённым только по возрасту модуля; последнее успешное deployment/live использование отдельно не проверено.
3. Проверить уже имеющийся мост на одинаковых source IDs/provenance/quality и устранить расхождения. Не писать повторный importer с теми же обязанностями.
4. Не переносить векторы ни в одну сторону по совпадению dimension. Установить модель, текстовую нормализацию, chunking и namespace; на неизвестном происхождении не подставлять вектор в текущий рейтинг.
5. Не заводить третье хранилище или новый vector DB. Измерить latency/memory полного current ranking и retrieval workload. Если прямое сравнение перестанет удовлетворять требованиям, предложить производный Chroma index актуальных version IDs, который можно пересоздать из авторитетных данных, с отдельным ADR.

## Альтернативы и последствия

Массовая миграция Chroma→SQLite сейчас рискует смешать whole-document и chunk vectors; обратная миграция не нужна для работы текущего рейтинга. Два файла можно сохранять, если явно определены ownership и происхождение. Запись snapshots в SQLite не означает автоматический импорт Chroma scores или готовность cloud Telegram.

Приёмка будущей интеграции: одна source vacancy сохраняет устойчивый ID; разные версии не смешиваются; повтор импорта idempotent; личные данные не публикуются; текущий рейтинг совпадает с baseline, пока алгоритм намеренно не изменён. ANN index при необходимости остаётся производным, approvals/CRM в него не переезжают.
