import sys
from src.scrapers.faang import GoogleCareersScraper

def test_google():
    scraper = GoogleCareersScraper(limit=5, stealth=True)
    jobs = scraper.fetch_jobs("Machine Learning Engineer")
    for j in jobs:
        print(f"[{j['id']}] {j['title']}")
        print(j['description'][:100] + "...\n")

if __name__ == "__main__":
    test_google()
