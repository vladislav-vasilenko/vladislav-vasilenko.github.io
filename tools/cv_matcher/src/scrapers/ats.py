"""Employers on applicant-tracking systems with open job-board APIs. No browser needed."""
from __future__ import annotations

from datetime import datetime, timezone
import html
from typing import Any, Dict, List, Optional, Set

from bs4 import BeautifulSoup
import requests

from ._base import BaseScraper
from ..board_import import identity

USER_AGENT = 'CVMatcher/0.11 public vacancy collector'


class JobBoardScraper(BaseScraper):
    """Reads one whole board in a single request and keeps only what is still needed."""

    board = ''
    adapter = ''

    def _listing(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def _row(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def _build(self, link, title, description, **fields) -> Optional[Dict[str, Any]]:
        own = identity(link or '')
        if not own or not title or not title.strip():
            return None
        text = description.strip()
        return {**own, 'title': title.strip(), 'company': self.company_name, 'description': text,
                'description_quality': 'full' if len(text) >= 150 else 'snippet', 'source_page': own['link'],
                'adapter_version': self.adapter, 'description_fetched_at': datetime.now(timezone.utc).isoformat(), **fields}

    def fetch_jobs(self, query: str, existing_ids: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        self._new_report()
        known = existing_ids or set()
        needle = (query or '').strip().lower()
        self._emit('source_start', company=self.company_name, query=query, limit=self.limit)
        try:
            jobs = self._listing()
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            self._emit('error', company=self.company_name, message=type(error).__name__)
            raise RuntimeError(self.company_name + ': ' + type(error).__name__) from error
        self.report['listed'] = len(jobs)
        result = []
        for job in jobs:
            if self.limit and len(result) >= self.limit:
                break
            row = self._row(job)
            if not row or row['id'] in known:
                continue
            if needle and needle not in (row['title'] + ' ' + row['description']).lower():
                continue
            result.append(row)
            self._emit('vacancy', id=row['id'], title=row['title'], company=self.company_name, link=row['link'])
        self.report['accepted'] = len(result)
        self._finish_coverage(len(result))
        print(f'  {self.company_name}: новых {len(result)}, просмотрено {len(jobs)}')
        return result

    def _get(self, url: str) -> Dict[str, Any]:
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=60)
        response.raise_for_status()
        return response.json()


class GreenhouseScraper(JobBoardScraper):
    adapter = 'greenhouse-api-v1'

    def _listing(self):
        return self._get(f'https://boards-api.greenhouse.io/v1/boards/{self.board}/jobs?content=true')['jobs']

    def _row(self, job):
        text = BeautifulSoup(html.unescape(job.get('content') or ''), 'html.parser').get_text('\n', strip=True)
        place = (job.get('location') or {}).get('name') or ''
        return self._build(job.get('absolute_url'), job.get('title'), text, pub_date=job.get('first_published') or 'Recently',
                           locations=[part.strip() for part in place.split('|') if part.strip()],
                           teams=[d['name'] for d in job.get('departments') or [] if d.get('name')], origin_query='')


class AshbyScraper(JobBoardScraper):
    adapter = 'ashby-api-v1'

    def _listing(self):
        data = self._get(f'https://api.ashbyhq.com/posting-api/job-board/{self.board}?includeCompensation=true')['jobs']
        return [job for job in data if job.get('isListed', True)]

    def _row(self, job):
        places = [job.get('location'), *[p.get('location') for p in job.get('secondaryLocations') or [] if isinstance(p, dict)]]
        pay = (job.get('compensation') or {}).get('compensationTierSummary') or ''
        return self._build(job.get('jobUrl'), job.get('title'), job.get('descriptionPlain') or '', pub_date=job.get('publishedAt') or 'Recently',
                           locations=[p for p in places if p], teams=[t for t in (job.get('department'), job.get('team')) if t],
                           compensation=pay, origin_query='')


# Each board was checked against the company's own text or careers page on 2026-11-04.
BOARDS = {
    'anthropic': ('Anthropic', GreenhouseScraper, 'anthropic'),
    'openai': ('OpenAI', AshbyScraper, 'openai'),
    'xai': ('xAI / SpaceXSI', GreenhouseScraper, 'xai'),
    'cohere': ('Cohere', AshbyScraper, 'cohere'),
    'perplexity': ('Perplexity', AshbyScraper, 'perplexity'),
    'thinkingmachines': ('Thinking Machines', AshbyScraper, 'thinkingmachines'),
    'physicalintelligence': ('Physical Intelligence', AshbyScraper, 'physicalintelligence'),
    'togetherai': ('Together AI', GreenhouseScraper, 'togetherai'),
    'elevenlabs': ('ElevenLabs', AshbyScraper, 'elevenlabs'),
    'cursor': ('Cursor', AshbyScraper, 'cursor'),
    'scaleai': ('Scale AI', GreenhouseScraper, 'scaleai'),
    'figure': ('Figure', GreenhouseScraper, 'figureai'),
    'characterai': ('Character.AI', AshbyScraper, 'character'),
    'reka': ('Reka', AshbyScraper, 'reka'),
    'liquidai': ('Liquid AI', AshbyScraper, 'liquid-ai'),
    'worldlabs': ('World Labs', AshbyScraper, 'worldlabs'),
    'runway': ('Runway', AshbyScraper, 'runway'),
    'poolside': ('Poolside', AshbyScraper, 'poolside'),
    'lumaai': ('Luma AI', AshbyScraper, 'lumaai'),
    'higgsfield': ('Higgsfield', AshbyScraper, 'higgsfieldai'),
    'pika': ('Pika', AshbyScraper, 'pika'),
    'midjourney': ('Midjourney', AshbyScraper, 'midjourney'),
    'suno': ('Suno', AshbyScraper, 'suno'),
    'synthesia': ('Synthesia', AshbyScraper, 'synthesia'),
    'heygen': ('HeyGen', GreenhouseScraper, 'heygen'),
    'krea': ('Krea', AshbyScraper, 'krea'),
}
BOARD_SCRAPERS = {key: type(key.title() + 'Scraper', (base,), {'company_name': label, 'id_prefix': key, 'board': board}) for key, (label, base, board) in BOARDS.items()}
AnthropicScraper, OpenAIScraper = BOARD_SCRAPERS['anthropic'], BOARD_SCRAPERS['openai']
