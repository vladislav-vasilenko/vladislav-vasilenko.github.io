import sys

file_path = 'src/scraper.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# Новый код инициализации браузера (стабильный для Mac)
replacement = """            # На Mac используем системный Chrome и headless=False для стабильности
            try:
                browser = p.chromium.launch(channel="chrome", headless=False, args=["--disable-dev-shm-usage", "--no-sandbox"])
            except:
                browser = p.chromium.launch(headless=False)
"""

# Индексы строк (из результатов grep: 257, 339, 429)
lines[256] = replacement # HHScraper
lines[338] = replacement # OzonScraper
lines[428] = replacement # AvitoScraper

with open(file_path, 'w') as f:
    f.writelines(lines)

print("✅ Файл src/scraper.py успешно обновлен. Браузеры переключены на системный Chrome (headless=False).")
