// ==UserScript==
// @name         LinkedIn Connections Scraper
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Scrape LinkedIn connections and download as JSON
// @author       Antigravity
// @match        https://www.linkedin.com/mynetwork/invite-connect/connections/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    const btn = document.createElement('button');
    btn.innerText = "Scrape Connections";
    btn.style.position = 'fixed';
    btn.style.bottom = '20px';
    btn.style.left = '20px';
    btn.style.zIndex = '99999';
    btn.style.padding = '12px 16px';
    btn.style.backgroundColor = '#0a66c2';
    btn.style.color = 'white';
    btn.style.border = 'none';
    btn.style.borderRadius = '24px';
    btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    btn.style.cursor = 'pointer';
    btn.style.fontWeight = 'bold';
    btn.style.fontSize = '14px';

    window.addEventListener('load', () => {
        document.body.appendChild(btn);
    });

    btn.addEventListener('click', async () => {
        btn.innerText = "Scrolling...";
        btn.disabled = true;
        btn.style.backgroundColor = '#666';

        const sleep = ms => new Promise(r => setTimeout(r, ms));
        let prevHeight = 0;
        while (true) {
            window.scrollTo(0, document.body.scrollHeight);
            await sleep(1500);
            const newHeight = document.body.scrollHeight;
            if (newHeight === prevHeight) break;
            prevHeight = newHeight;
        }

        const connections = [];
        const processedUrls = new Set();
        document.querySelectorAll('a[href*="/in/"]').forEach(link => {
            const url = link.href.split('?')[0];
            if (url.includes('miniProfile') || processedUrls.has(url)) return;

            const card = link.closest('li');
            if (!card) return;

            const nameEl = card.querySelector('.mn-connection-card__name') || link;
            const headlineEl = card.querySelector('.mn-connection-card__occupation');
            const name = (nameEl?.innerText || '')
                .replace("Member's name", "")
                .replace("Member’s name", "")
                .replace(/\n/g, "")
                .trim();
            const headline = (headlineEl?.innerText || '').trim();
            const id = url.split('/in/')[1]?.replace('/', '') || url;

            if (name) {
                connections.push({ id, name, headline, url });
                processedUrls.add(url);
            }
        });

        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(connections, null, 2));
        const dlAnchorNode = document.createElement('a');
        dlAnchorNode.setAttribute("href", dataStr);
        dlAnchorNode.setAttribute("download", "linkedin_connections.json");
        document.body.appendChild(dlAnchorNode);
        dlAnchorNode.click();
        dlAnchorNode.remove();

        btn.innerText = `Downloaded ${connections.length}`;
        btn.style.backgroundColor = '#057642';
        setTimeout(() => {
            btn.innerText = "Scrape Connections";
            btn.disabled = false;
            btn.style.backgroundColor = '#0a66c2';
        }, 5000);
    });
})();
