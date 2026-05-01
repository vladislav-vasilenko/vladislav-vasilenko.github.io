import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def scrape_linkedin_connections(user_data_dir: str, output_file: str, max_scrolls: int = 50):
    with sync_playwright() as p:
        print(f"Launching browser with user data dir: {user_data_dir}")
        # Use persistent context to keep login session
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False, # Better to be non-headless for LinkedIn to handle captchas/logins manually if needed
            channel="chrome", # <--- Используем системный Chrome, чтобы избежать SIGBUS на Mac ARM64
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        li_at = os.environ.get("LINKEDIN_LI_AT")
        if li_at:
            print("Found LINKEDIN_LI_AT in .env, injecting auth cookie...")
            clean_cookie = li_at.strip().strip("'\"")
            browser.add_cookies([{
                "name": "li_at",
                "value": clean_cookie,
                "domain": ".www.linkedin.com",
                "path": "/",
                "secure": True,
                "httpOnly": True
            }])

        page = browser.new_page()

        print("Navigating to LinkedIn connections page...")
        for attempt in range(3):
            try:
                page.goto("https://www.linkedin.com/mynetwork/invite-connect/connections/", timeout=60000)
                break
            except Exception as e:
                print(f"Navigation error (attempt {attempt+1}): {e}")
                if attempt == 2:
                    raise
                time.sleep(2)

        # Handle login if redirected to a login or checkpoint page
        if "/login" in page.url or "checkpoint" in page.url or "authwall" in page.url:
            email = os.environ.get("LINKEDIN_EMAIL")
            password = os.environ.get("LINKEDIN_PASSWORD")
            
            if email and password and ("login" in page.url or "authwall" in page.url):
                print("Attempting auto-login using credentials from .env...")
                try:
                    page.fill("input[name='session_key'], input[id='username']", email)
                    page.fill("input[name='session_password'], input[id='password']", password)
                    page.click("button[type='submit']")
                    time.sleep(3) # Wait for navigation to start
                except Exception as e:
                    print(f"Auto-login fill failed: {e}")
            
            # If still not on the right page (e.g., 2FA or Captcha required)
            if "mynetwork/invite-connect/connections" not in page.url:
                print("Please complete any remaining login steps (2FA/Captcha) manually in the opened browser window.")
                page.wait_for_url("**/mynetwork/invite-connect/connections/**", timeout=300000) # 5 mins to login
                print("Login completed, continuing...")
                time.sleep(3)

        print(f"Current URL: {page.url}")
        print(f"Page Title: {page.title()}")
        page.screenshot(path="debug_linkedin.png")
        
        print("Waiting 5 seconds for page to render...")
        time.sleep(5)
        
        # Save HTML for debugging
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("Saved raw HTML to debug.html")
        
        print("Scrolling down to load all connections...")
        # Scroll to bottom repeatedly to load all connections
        prev_height = -1
        scroll_count = 0
        while scroll_count < max_scrolls:
            # Get current scroll height
            curr_height = page.evaluate("document.body.scrollHeight")
            if curr_height == prev_height:
                print("Reached bottom of the page.")
                break
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2) # Wait for network requests
            
            prev_height = curr_height
            scroll_count += 1
            print(f"Scrolled {scroll_count}/{max_scrolls} times...")

        print("Extracting connection data...")
        connections = []
        
        # LinkedIn DOM changes often. These selectors try to be generic.
        # Usually connections are list items.
        cards = page.locator("li.mn-connection-card")
        
        count = cards.count()
        print(f"Found {count} connection cards.")
        
        for i in range(count):
            card = cards.nth(i)
            try:
                # Extract URL
                link_el = card.locator("a[data-control-name='connection_profile']")
                if link_el.count() == 0:
                     link_el = card.locator("a.mn-connection-card__link")
                
                url = link_el.get_attribute("href") if link_el.count() > 0 else ""
                if url and not url.startswith("http"):
                    url = "https://www.linkedin.com" + url

                # Extract Name
                name_el = card.locator(".mn-connection-card__name")
                name = name_el.inner_text().strip() if name_el.count() > 0 else "Unknown"
                
                # Clean up name (sometimes contains 'Member’s name')
                name = name.replace("Member’s name", "").strip()

                # Extract Headline (Occupation)
                headline_el = card.locator(".mn-connection-card__occupation")
                headline = headline_el.inner_text().strip() if headline_el.count() > 0 else ""

                if name != "Unknown":
                    connections.append({
                        "id": url.split("/in/")[-1].strip("/") if "/in/" in url else url,
                        "name": name,
                        "headline": headline,
                        "url": url
                    })
            except Exception as e:
                print(f"Error parsing card {i}: {e}")

        # Fallback if the above selectors fail (LinkedIn A/B testing)
        if len(connections) == 0:
            print("Standard selectors failed. Trying fallback extraction...")
            # Just grab all profile links on the page that look like connections
            all_links = page.locator("a").all()
            for link in all_links:
                href = link.get_attribute("href") or ""
                if "/in/" in href and "miniProfile" not in href:
                    name_text = link.inner_text().strip()
                    if name_text and "\n" not in name_text: # Simple heuristic to avoid complex cards
                        connections.append({
                             "id": href.split("/in/")[-1].strip("/"),
                             "name": name_text,
                             "headline": "Extracted via fallback",
                             "url": "https://www.linkedin.com" + href if href.startswith("/") else href
                        })
            # deduplicate by url
            unique_conns = {c["url"]: c for c in connections}.values()
            connections = list(unique_conns)

        print(f"Successfully extracted {len(connections)} connections.")

        # Save to JSON
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(connections, f, ensure_ascii=False, indent=2)
        
        print(f"Saved connections to {output_file}")
        
        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape LinkedIn Connections")
    parser.add_argument("--user-data-dir", default="./linkedin_profile", help="Path to save browser session")
    parser.add_argument("--out", default="data/linkedin_connections.json", help="Output JSON file")
    parser.add_argument("--max-scrolls", type=int, default=50, help="Max times to scroll down")
    
    args = parser.parse_args()
    
    scrape_linkedin_connections(args.user_data_dir, args.out, args.max_scrolls)
