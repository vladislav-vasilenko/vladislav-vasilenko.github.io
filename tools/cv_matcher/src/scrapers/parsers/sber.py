"""Browser-side Sber parser helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable
from urllib.parse import urlparse


SBER_PARSER_VERSION = "sber-browser-parser-v2-concurrent-details"

SBER_DEEP_PARSE_JS = r"""
async ({ limit, detailConcurrency, detailDelayMs, detailTimeoutMs, maxEmptyScrolls, scrollDelayMs }) => {
    const SEARCH_CONFIG = {
        cardSelector: '.styled__Card-sc-192d1yv-1.fmUtEX, article, li, div',
        linkSelector: 'a[href*="/search/"]',
        titleSelector: 'a.styled__TitleWithGradeWrapper-sc-192d1yv-2, a[href*="/search/"]',
        locationSelector: 'div[color="textPrimaryMuted"]',
        dateSelector: 'div[color="textSecondary"]',
        loadMoreText: /показать|загрузить|ещ[её]|more|load/i,
    };
    const DETAIL_CONFIG = {
        blockSelector: '.styled__Container-sc-bjz37r-0.byODeX, section, article',
        titleSelector: '.styled__FontWrapper-sc-kir5f-0.kUhDsX h3, h2, h3',
        listItemsSelector: 'ul > li',
        paragraphSelector: 'p',
    };
    const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const log = (message) => console.log(`[sber-parser] ${message}`);
    const toAbsolute = (href) => {
        try {
            return new URL(href, window.location.origin).href.split('?')[0].split('#')[0].replace(/\/$/, '');
        } catch {
            return '';
        }
    };
    const isVisible = (el) => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const scrollTargets = () => {
        const targets = [document.scrollingElement || document.documentElement, document.body];
        for (const el of document.querySelectorAll('main, [role="main"], section, div')) {
            if (!isVisible(el)) continue;
            if (el.scrollHeight > el.clientHeight + 120) targets.push(el);
        }
        return Array.from(new Set(targets)).sort((a, b) => {
            const aScore = (a.scrollHeight - a.clientHeight) * Math.max(a.clientHeight, 1);
            const bScore = (b.scrollHeight - b.clientHeight) * Math.max(b.clientHeight, 1);
            return bScore - aScore;
        }).slice(0, 8);
    };
    const clickLoadMore = () => {
        const controls = Array.from(document.querySelectorAll('button, a[role="button"], a'));
        for (const control of controls) {
            const text = clean(control.textContent);
            if (!text || !SEARCH_CONFIG.loadMoreText.test(text) || !isVisible(control)) continue;
            try {
                control.click();
                log(`clicked pagination control: ${text.slice(0, 60)}`);
                return true;
            } catch {}
        }
        return false;
    };
    const fetchTextWithTimeout = async (url, timeoutMs) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const response = await fetch(url, {
                credentials: 'include',
                headers: { accept: 'text/html,application/xhtml+xml' },
                cache: 'no-store',
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.text();
        } finally {
            clearTimeout(timer);
        }
    };
    const scrollPage = async () => {
        const beforeHeight = document.documentElement.scrollHeight;
        window.scrollBy(0, Math.floor(window.innerHeight * 0.9));
        window.dispatchEvent(new WheelEvent('wheel', { deltaY: window.innerHeight, bubbles: true }));
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'PageDown', code: 'PageDown', bubbles: true }));

        for (const target of scrollTargets()) {
            const delta = Math.max(600, Math.floor((target.clientHeight || window.innerHeight) * 0.9));
            target.scrollTop = Math.min(target.scrollTop + delta, target.scrollHeight);
            target.dispatchEvent(new Event('scroll', { bubbles: true }));
            target.dispatchEvent(new WheelEvent('wheel', { deltaY: delta, bubbles: true }));
        }
        const clicked = clickLoadMore();
        await delay(scrollDelayMs);
        return { clicked, heightChanged: document.documentElement.scrollHeight !== beforeHeight };
    };

    const foundLinks = new Map();
    let emptyScrollCount = 0;

    log(`version=sber-browser-parser-v2-concurrent-details`);
    while (emptyScrollCount < maxEmptyScrolls && (!limit || foundLinks.size < limit)) {
        const candidates = document.querySelectorAll(SEARCH_CONFIG.linkSelector);
        let currentLoopNew = 0;

        candidates.forEach((titleLink) => {
            if (limit && foundLinks.size >= limit) return;

            const url = toAbsolute(titleLink.getAttribute('href'));
            if (!url || !/\/search\/[^/]*\d{4,}/.test(url) || foundLinks.has(url)) return;

            const candidate = titleLink.closest(SEARCH_CONFIG.cardSelector) || titleLink.parentElement || titleLink;
            const locations = candidate.querySelectorAll(SEARCH_CONFIG.locationSelector);
            foundLinks.set(url, {
                title: clean(titleLink.textContent) || 'Sber Vacancy',
                city: clean(locations[0]?.textContent) || '',
                company: clean(locations[1]?.textContent) || 'ПАО Сбербанк',
                date: clean(candidate.querySelector(SEARCH_CONFIG.dateSelector)?.textContent) || 'Недавно',
                url,
                details: {},
            });
            currentLoopNew++;
        });

        log(`collected=${foundLinks.size}, new=${currentLoopNew}, empty=${emptyScrollCount}`);
        const scrollResult = await scrollPage();
        emptyScrollCount = currentLoopNew > 0 || scrollResult.clicked || scrollResult.heightChanged
            ? 0
            : emptyScrollCount + 1;
    }

    const parseDetail = async (item, index, total) => {
        if (index === 1 || index % 10 === 0) log(`fetching details ${index}/${total}: ${item.url}`);
        try {
            const htmlText = await fetchTextWithTimeout(item.url, detailTimeoutMs);
            const doc = new DOMParser().parseFromString(htmlText, 'text/html');
            const h1 = clean(doc.querySelector('h1')?.textContent);
            if (h1) item.title = h1;

            const blocks = doc.querySelectorAll(DETAIL_CONFIG.blockSelector);
            blocks.forEach((block) => {
                const blockTitle = clean(block.querySelector(DETAIL_CONFIG.titleSelector)?.textContent);
                if (!blockTitle || blockTitle.length > 120) return;

                const lis = Array.from(block.querySelectorAll(DETAIL_CONFIG.listItemsSelector))
                    .map((li) => clean(li.textContent))
                    .filter(Boolean);
                if (lis.length > 0) {
                    item.details[blockTitle] = lis;
                    return;
                }

                const pText = Array.from(block.querySelectorAll(DETAIL_CONFIG.paragraphSelector))
                    .map((p) => clean(p.textContent))
                    .filter(Boolean)
                    .join('\n');
                if (pText) item.details[blockTitle] = pText;
            });

            if (Object.keys(item.details).length === 0) {
                const mainText = clean(doc.querySelector('main, article, body')?.textContent);
                if (mainText) item.details['Описание'] = mainText.slice(0, 6000);
            }
        } catch (error) {
            item.details = { 'Ошибка': `Не удалось загрузить страницу вакансии: ${error.message}` };
            log(`detail failed ${index}/${total}: ${error.message}`);
        }
        await delay(detailDelayMs);
        return item;
    };

    const items = Array.from(foundLinks.values()).slice(0, limit || undefined);
    log(`list collection done: ${foundLinks.size} links; fetching ${items.length} details with concurrency=${detailConcurrency}`);
    let nextIndex = 0;
    let completed = 0;
    const workerCount = Math.max(1, Math.min(detailConcurrency || 1, items.length || 1));
    const workers = Array.from({ length: workerCount }, async () => {
        while (nextIndex < items.length) {
            const current = nextIndex++;
            await parseDetail(items[current], current + 1, items.length);
            completed++;
            if (completed === items.length || completed % 10 === 0) {
                log(`details progress ${completed}/${items.length}`);
            }
        }
    });
    await Promise.all(workers);

    return items;
}
"""


_SBER_ID_RE = re.compile(r"/search/(?:[^/?#]+-)?(\d{4,})(?:/|\?|#|$)")


def sber_id_from_url(url: str) -> str:
    """Extract Sber's trailing numeric vacancy id from a search detail URL."""
    path = urlparse(url).path
    match = _SBER_ID_RE.search(path)
    if match:
        return match.group(1)
    return path.rstrip("/").split("-")[-1]


def compose_sber_description(details: Dict[str, Any]) -> str:
    """Format browser-parsed Sber detail sections into searchable text."""
    parts = []
    for title, value in details.items():
        if title == "Ошибка":
            continue
        if isinstance(value, list):
            text = "\n".join(f"- {v}" for v in value if v)
        else:
            text = str(value or "").strip()
        if text:
            parts.append(f"{title}:\n{text}")
    return "\n\n".join(parts)


def sber_locations(raw: Dict[str, Any]) -> Iterable[str]:
    city = str(raw.get("city") or "").strip()
    if city and city != "Не указан":
        yield city
