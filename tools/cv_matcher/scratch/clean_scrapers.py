import sys

file_path = 'src/scraper.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# Окончательный чистый блок инициализации
clean_init = """            # На Mac используем системный Chrome + Disable GPU для стабильности.
            # Если падает - переключаемся на нативный WebKit.
            try:
                browser = p.chromium.launch(
                    channel="chrome", 
                    headless=False, 
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
                )
            except Exception as e:
                print(f"      ⚠️ Проблема с Chrome ({e}), переключаемся на WebKit...")
                try:
                    browser = p.webkit.launch(headless=True)
                except:
                    browser = p.chromium.launch(headless=False, args=["--disable-gpu"])
"""

# Ищем и заменяем старые блоки
import re

def clean_file(content):
    # Паттерн ищет блоки от "with sync_playwright" до "context ="
    pattern = r'(with sync_playwright\(\) as p:\s+)(?:.|\n)*?(\s+context = browser\.new_context\()'
    return re.sub(pattern, r'\1' + clean_init + r'\2', content)

content = "".join(lines)
new_content = clean_file(content)

with open(file_path, 'w') as f:
    f.write(new_content)

print("✅ Код в scraper.py очищен и готов к работе.")
