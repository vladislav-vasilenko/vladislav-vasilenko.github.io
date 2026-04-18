import sys

file_path = 'src/scraper.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# Универсальный код запуска с максимальной защитой от падений
stable_launch = """            # На Mac используем системный Chrome + Disable GPU для стабильности.
            # Если падает - переключаемся на нативный WebKit.
            try:
                browser = p.chromium.launch(
                    channel="chrome", 
                    headless=False, 
                    args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-software-rasterizer"]
                )
            except Exception as e:
                print(f"      ⚠️ Ошибка запуска Chrome, пробуем WebKit: {e}")
                try:
                    browser = p.webkit.launch(headless=True)
                except:
                    browser = p.chromium.launch(headless=False, args=["--disable-gpu"])
"""

# Индексы строк для замены (на основе актуального состояния файла)
# HHScraper (~257), OzonScraper (~339), AvitoScraper (~429)
# Мы заменим блоки инициализации целиком

def replace_block(lines, start_idx, target_pattern, replacement):
    for i in range(start_idx, start_idx + 20):
        if i < len(lines) and target_pattern in lines[i]:
            lines[i] = replacement
            # Убираем следующие строки до context = ...
            j = i + 1
            while j < len(lines) and "context =" not in lines[j]:
                lines[j] = ""
                j += 1
            return True
    return False

replace_block(lines, 250, "p.chromium.launch", stable_launch)
replace_block(lines, 330, "p.chromium.launch", stable_launch)
replace_block(lines, 420, "p.chromium.launch", stable_launch)

with open(file_path, 'w') as f:
    f.writelines(lines)

print("✅ Файл src/scraper.py обновлен: добавлен No-GPU режим и автоматический переход на WebKit.")
