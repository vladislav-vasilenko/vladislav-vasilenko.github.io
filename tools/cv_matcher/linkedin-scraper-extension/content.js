(async () => {
    console.log("LinkedIn Connections Scraper started...");
    
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    
    // 1. Scroll to the bottom
    let prevHeight = 0;
    while (true) {
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(1500); 
        let newHeight = document.body.scrollHeight;
        if (newHeight === prevHeight) {
            console.log("Reached bottom of page.");
            break;
        }
        prevHeight = newHeight;
    }
    
    // 2. Extract connections
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
    
    console.log(`Extracted ${connections.length} connections.`);
    
    // 3. Download JSON
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(connections, null, 2));
    const dlAnchorNode = document.createElement('a');
    dlAnchorNode.setAttribute("href", dataStr);
    dlAnchorNode.setAttribute("download", "linkedin_connections.json");
    document.body.appendChild(dlAnchorNode);
    dlAnchorNode.click();
    dlAnchorNode.remove();
    
    alert(`Successfully scraped and downloaded ${connections.length} connections!`);
})();
