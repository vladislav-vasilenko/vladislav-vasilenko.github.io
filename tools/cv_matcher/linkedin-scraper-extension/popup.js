document.getElementById('scrapeBtn').addEventListener('click', async () => {
    const status = document.getElementById('status');
    status.innerText = "Starting scraper...";
    
    // Get current active tab
    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (!tab.url.includes("linkedin.com/mynetwork/invite-connect/connections")) {
        status.innerText = "Error: Please open the LinkedIn Connections page to use this tool.";
        return;
    }

    status.innerText = "Scraping in progress. Please wait and keep the tab open (it will scroll automatically)...";

    // Inject the content script
    chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
    });
});
