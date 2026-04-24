"""Anti-detection helpers for Playwright.

Goals:
  - remove the obvious `navigator.webdriver` flag
  - present a realistic desktop Chrome fingerprint (plugins, languages, chrome.runtime)
  - rotate user-agent and viewport per run
  - add realistic locale / timezone / accept-language headers

Not a silver bullet — aggressive sites (LinkedIn, Indeed) still win.
Good enough for Sber / Yandex / Google / Meta when combined with `storage_state`.
"""

import random
from typing import Any, Dict, Optional


# Injected before any page navigates. Keeps the patches idempotent.
STEALTH_INIT_JS = """
(() => {
  // 1. navigator.webdriver → undefined
  Object.defineProperty(Navigator.prototype, 'webdriver', {
    get: () => undefined,
    configurable: true,
  });

  // 2. Pretend we have a few plugins (headless Chrome has zero)
  Object.defineProperty(navigator, 'plugins', {
    get: () => [
      { name: 'PDF Viewer', filename: 'internal-pdf-viewer', length: 1 },
      { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', length: 1 },
      { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', length: 1 },
    ],
  });

  // 3. Languages match locale
  Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'ru'],
  });

  // 4. window.chrome presence (real Chrome has this object)
  if (!window.chrome) {
    window.chrome = { runtime: {}, app: { isInstalled: false } };
  }

  // 5. permissions.query returns "granted" for notifications instead of "denied"
  //    (headless Chrome gives a mismatch between Notification.permission and query result)
  const origQuery = navigator.permissions ? navigator.permissions.query.bind(navigator.permissions) : null;
  if (origQuery) {
    navigator.permissions.query = (p) =>
      p && p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission, onchange: null })
        : origQuery(p);
  }

  // 6. WebGL vendor/renderer — some sites fingerprint this
  try {
    const proto = WebGLRenderingContext.prototype;
    const origParam = proto.getParameter;
    proto.getParameter = function (param) {
      if (param === 37445) return 'Intel Inc.';                // UNMASKED_VENDOR_WEBGL
      if (param === 37446) return 'Intel Iris OpenGL Engine';  // UNMASKED_RENDERER_WEBGL
      return origParam.call(this, param);
    };
  } catch (e) { /* ignore */ }
})();
"""


# Recent stable desktop Chrome user agents (rotated per run)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Common desktop resolutions
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1680, "height": 1050},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
]


def stealth_context_kwargs(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return realistic BrowserContext kwargs for new_context()."""
    kwargs: Dict[str, Any] = {
        "user_agent": random.choice(USER_AGENTS),
        "viewport": random.choice(VIEWPORTS),
        "locale": "en-US",
        "timezone_id": "Europe/Moscow",
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not=A?Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Upgrade-Insecure-Requests": "1",
        },
    }
    if extra:
        kwargs.update(extra)
    return kwargs


def apply_stealth(context) -> None:
    """Inject stealth init-script into a BrowserContext. Must be called before goto()."""
    context.add_init_script(STEALTH_INIT_JS)


def human_pause(min_ms: int = 600, max_ms: int = 2400) -> int:
    """Random delay in ms — for per-click / per-navigation jitter."""
    return random.randint(min_ms, max_ms)
