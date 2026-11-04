# Stage 4: macOS Dock app

The user wants to launch this service from the macOS Dock, like `/Users/vladmac/Documents/ChatGPT/telegram-crm/scripts`. Report: `reports/04-macos-dock-app.json`.

## Reference

- `install_macos_app.py` builds an AppleScript app with `osacompile` into `~/Applications`, sets the bundle ID and icon, ad-hoc signs it with `codesign`, adds one Dock entry through `defaults`, and restarts the Dock.
- `service.py` has `start`, `stop`, `status` and `url`, with a lock file, health check, log file, PID file, and a check that the PID belongs to this service before stopping it.
- `make_icon.swift` draws the icon.

## Differences here

- Port 8788. `/health` requires the token, so send `X-Resume-Import-Token` from `.cache/resume_import/token.txt` and check `"service":"cv-matcher-local"`.
- The browser needs a login. `POST /archive/open` with the token returns a one-time `#connect=` URL valid for 60 s. Open that URL so there's no token prompt.
- Never print the token or put it in the app bundle. The app only calls the script, which reads the token from disk.
- Refuse to overwrite an app with a different bundle ID.
- The service loads `.env` itself. Logs go to `.cache/`, which is ignored by git.

Installing changes `~/Applications` and the Dock, which the user explicitly asked for.
