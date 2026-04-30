"""Debug: intercept Google Careers XHR/fetch responses to find the jobs API."""
import sys, os, json, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.scrapers._stealth import STEALTH_INIT_JS
from urllib.parse import quote
from playwright.sync_api import sync_playwright

query = "Machine Learning Engineer"
listing_url = f"https://www.google.com/about/careers/applications/jobs/results/?q={quote(query)}"

captured = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-gpu"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    ctx.add_init_script(STEALTH_INIT_JS)
    page = ctx.new_page()

    def on_response(resp):
        url = resp.url
        ct = resp.headers.get("content-type", "")
        if "json" in ct or "javascript" in ct or "proto" in ct:
            try:
                body = resp.text()
                if len(body) > 500 and ("job" in body.lower() or "position" in body.lower() or "title" in body.lower()):
                    captured.append({"url": url[:150], "size": len(body), "snippet": body[:300]})
            except:
                pass

    page.on("response", on_response)
    page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)

    print(f"\n=== Captured {len(captured)} responses with job-related content ===")
    for c in captured:
        print(f"\n  URL: {c['url']}")
        print(f"  Size: {c['size']} bytes")
        print(f"  Snippet: {c['snippet'][:200]}...")

    browser.close()
