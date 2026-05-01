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

    // Создаем плавающую кнопку
    const btn = document.createElement('button');
    btn.innerText = "📥 Scrape Connections";
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
    
    // Ждем полной загрузки страницы перед добавлением кнопки
    window.addEventListener('load', () => {
        document.body.appendChild(btn);
    });

    btn.addEventListener('click', async () => {
        btn.innerText = "⏳ Скроллим вниз... (Не трогай страницу)";
        btn.disabled = true;
        btn.style.backgroundColor = '#666';
        
        console.log("LinkedIn Connections Scraper started...");
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        
        // 1. Скроллим до самого низа
        let prevHeight = 0;
        while (true) {
            window.scrollTo(0, document.body.scrollHeight);
            await sleep(1500); 
            let newHeight = document.body.scrollHeight;
            if (newHeight === prevHeight) {
                console.log("Достигли низа списка.");
                break;
            }
            prevHeight = newHeight;
        }
        
        // 2. Извлекаем данные
        const connections = [];
        const allLinks = document.querySelectorAll('a[href*="/in/"]');
        const processedUrls = new Set();

        allLinks.forEach(link => {
            const url = link.href.split('?')[0]; 
            if (url.includes('miniProfile') || processedUrls.has(url)) return;
            
            const card = link.closest('li');
            if (!card) return;

            try {
                let name = "Unknown";
                const nameEl = card.querySelector('.mn-connection-card__name') || link;
                if (nameEl) name = nameEl.innerText.replace("Member’s name", "").replace(/\n/g, "").trim();

                let headline = "";
                const headlineEl = card.querySelector('.mn-connection-card__occupation');
                if (headlineEl) headline = headlineEl.innerText.trim();

                let id = url.split('/in/')[1]?.replace('/', '') || url;

                if (name && name !== "Unknown") {
                    connections.push({ id, name, headline, url });
                    processedUrls.add(url);
                }
            } catch (e) {
                console.error("Error parsing card:", e);
            }
        });
        
        console.log(`Собрано ${connections.length} контактов.`);
        
        // 3. Скачиваем JSON файл
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(connections, null, 2));
        const dlAnchorNode = document.createElement('a');
        dlAnchorNode.setAttribute("href", dataStr);
        dlAnchorNode.setAttribute("download", "linkedin_connections.json");
        document.body.appendChild(dlAnchorNode);
        dlAnchorNode.click();
        dlAnchorNode.remove();
        
        btn.innerText = `✅ Скачано ${connections.length} контактов!`;
        btn.style.backgroundColor = '#057642';
        
        // Возвращаем кнопку в исходное состояние через 5 секунд
        setTimeout(() => {
            btn.innerText = "📥 Scrape Connections";
            btn.disabled = false;
            btn.style.backgroundColor = '#0a66c2';
        }, 5000);
    });
})();
