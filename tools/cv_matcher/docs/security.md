# Секреты, учётные данные и локальное состояние

Дата: 24.10.2026. Область: `tools/cv_matcher`, корневые workflows GitHub Actions и `cv-api`. Репозиторий публичный: всё, что попало в индекс git, следует считать опубликованным.

## Где какие секреты живут

| Данные | Файл или место | Кто читает | В git |
|---|---|---|---|
| `OPENAI_API_KEY`, `COVER_LETTER_MODEL`, `OPENAI_EMBEDDING_MODEL`, `EMBEDDINGS_PROVIDER`, `OLLAMA_HOST`, `OLLAMA_EMBEDDING_MODEL` | `tools/cv_matcher/.env` | `resume_import_server.py`, `src/` | никогда |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_OWNER_ID`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_DIGEST_TIMES`, `TELEGRAM_DIGEST_TIMEZONE` | `tools/cv_matcher/.env` (образец имён — `telegram.env.example`) | `telegram_recruiter.py`, `src/career_notifications.py` | никогда |
| `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET` | `tools/cv_matcher/.env`; выданные токены — `.cache/calendar/oauth.json` | `src/google_calendar_sync.py`, `src/calendar_routes.py` | никогда |
| Код сопряжения расширения | `.cache/resume_import/token.txt`; в расширении — `storage.session` (при «запомнить» — `storage.local`) | расширение → заголовок `X-Resume-Import-Token` только на `http://127.0.0.1:8788` | никогда |
| Сессия Telethon, storage states Playwright | `.cache/`, `.auth/` | `telegram_recruiter.py`, `scripts/scrape_online.py` | никогда |
| Личный архив | `state.sqlite3` и прочие `*.sqlite3`/`*.db` | сервис | никогда |
| `API_SECRET`, `CV_API_URL` | `tools/cv_matcher/.env` (клиент) и переменные окружения Vercel (`cv-api`, вместе с `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TURNSTILE_SECRET_KEY`) | `cv_matcher.py`, `cv-api/api/*.js` | никогда |
| `GOOGLE_STORAGE_STATE_B64`, `META_STORAGE_STATE_B64`, `OPENAI_API_KEY` | GitHub Actions secrets | `.github/workflows/daily-scrape.yml`, `rag_updater.yml` | только как secrets |
| `LINKEDIN_LI_AT`, `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` | `tools/cv_matcher/.env` | только legacy `scripts/scrape_linkedin.py` | никогда; ключи удалить вместе со скриптом |

Расширение не получает ни ключ OpenAI, ни токены Telegram: оно знает только код сопряжения, а сервер держит остальное. Cookies и пароли LinkedIn сервису не передаются; расширение читает уже открытую вкладку.

## Правила

- `.gitignore` перечисляет `.env`, `.cache/`, `.auth/`, `chroma_db/`, `*.sqlite3`, но ignore-правила не снимают с учёта файл, который уже был закоммичен. Проверять индекс: `git ls-files | grep -E '(^|/)\.env$'` должно быть пустым.
- `npm run workspace:check` с 24.10.2026 падает, если в индексе есть `.env`, `*.sqlite*`, `*.db`, `token.txt`, `.cache/`, `.auth/`, `chroma_db/`, `google_state.json` или `linkedin_profile/`. Запускать перед каждым коммитом.
- Не делать `git add -A` / `git add .` из `tools/cv_matcher`; добавлять файлы по именам и смотреть `git status --short` перед коммитом.
- Рекомендуется локальный сканер секретов, например `gitleaks protect --staged` в pre-commit hook; хуки не хранятся в репозитории, поэтому их нужно включить на каждом рабочем месте.
- Новая переменная окружения добавляется сначала в `.env.example` (только имя), затем в таблицу выше.

## Инцидент 24.10.2026: `.env` в публичной истории

**Что произошло.** `tools/cv_matcher/.env` был закоммичен в `ff34f15` (17.04.2026) и `c706d32` (01.05.2026) и оставался на учёте до 24.10.2026, несмотря на запись в `.gitignore`. В зафиксированной версии были непустые `API_SECRET`, `CV_API_URL`, `LINKEDIN_LI_AT`, `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`. В рабочей копии к тому же файлу были добавлены `OPENAI_API_KEY` и `TELEGRAM_*`; они не были закоммичены, но один `git add -A` отделял их от публикации. Те же коммиты добавили `data/linkedin_connections.json` и `src/debug_linkedin_connections.html` с персональными данными контактов LinkedIn.

**Сделано 24.10.2026.** `git rm --cached tools/cv_matcher/.env` и `git rm --cached -r tools/cv_matcher/chroma_db` (файлы остались на диске, из индекса удалены); добавлена проверка в `workspace:check`; `.env.example` перечисляет все имена переменных.

**Что должен сделать владелец (нельзя выполнить из репозитория):**

1. LinkedIn: сменить пароль и завершить все сессии в настройках аккаунта; это обнуляет утёкший cookie `li_at`. Включить двухфакторную аутентификацию.
2. Vercel (`cv-api`): задать новый `API_SECRET`; старое значение считать известным. Проверить расход `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` в этом проекте и при сомнении перевыпустить ключи.
3. OpenAI: перевыпустить `OPENAI_API_KEY` из `.env` как меру предосторожности (значение не было закоммичено, но лежало рядом с утёкшими).
4. Telegram: при сомнении перевыпустить токен бота через BotFather; `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` не были закоммичены.
5. Закоммитить снятие с учёта (`git commit -m "chore: stop tracking .env and chroma_db"`) и затем переписать историю:

```sh
brew install git-filter-repo        # или pip install git-filter-repo
git clone --mirror git@github.com:vladislav-vasilenko/vladislav-vasilenko.github.io.git purge.git
cd purge.git
git filter-repo --invert-paths \
  --path tools/cv_matcher/.env \
  --path tools/cv_matcher/chroma_db \
  --path tools/cv_matcher/data/linkedin_connections.json \
  --path tools/cv_matcher/src/debug_linkedin_connections.html
git push --force --mirror
```

   После этого все рабочие копии клонируются заново (старые клоны содержат прежние объекты), GitHub Pages переразвёртывается из нового `main`, а в поддержку GitHub отправляется запрос на очистку кэшированных просмотров коммитов. Форки, если они есть, сохраняют старую историю.

6. Проверка: `git log --all -- tools/cv_matcher/.env` в новом клоне пуст; `npm run workspace:check` проходит; `.env` на диске заполнен новыми значениями.

## Персональные данные третьих лиц

Отдельно от учётных данных: `public/linkedin_clusters.json` (937 контактов LinkedIn с именами, заголовками и ссылками) публикуется на GitHub Pages и читается `public/network.html`; `tools/cv_matcher/data/linkedin_connections.json` и `src/debug_linkedin_connections.html` на учёте. Это наследие legacy-скрейпера (`linkedin-scraper-extension/`, `scripts/scrape_linkedin.py`, `scripts/cluster_linkedin.py`). Решение об удалении файлов с сайта и из истории принимает владелец; команда `filter-repo` выше уже включает два последних пути. Подробности — в корневом [обзоре 24.10.2026](../../../docs/code-review-2026-10-24.md).
