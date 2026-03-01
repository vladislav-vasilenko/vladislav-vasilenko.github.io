chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: "smart-fill-ai",
        title: "✨ Smart Fill with AI",
        contexts: ["editable"]
    });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === "smart-fill-ai") {
        chrome.tabs.sendMessage(tab.id, { action: "trigger_ai_fill" }, (response) => {
            if (chrome.runtime.lastError) {
                console.error("[AutoFill Magic] Error:", chrome.runtime.lastError.message);
                chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: () => alert("⚠️ Please refresh the page! \n\nThe extension was updated, and the connection to this tab was lost.")
                });
            }
        });
    }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'generate_ai_answer') {
        fetch('https://vladislav-vasilenko-github-io.vercel.app/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request.data)
        })
            .then(async res => {
                const text = await res.text();
                if (!res.ok) {
                    console.error("[AutoFill Magic] API Error Text:", text);
                    throw new Error(`HTTP ${res.status}: ${text.slice(0, 100)}`);
                }
                try {
                    return JSON.parse(text);
                } catch (e) {
                    console.error("[AutoFill Magic] JSON Parse Error. Raw text:", text);
                    throw new Error("Invalid JSON response from server");
                }
            })
            .then(data => sendResponse({ success: true, data }))
            .catch(err => {
                console.error("[AutoFill Magic] Fetch Error:", err);
                sendResponse({ success: false, error: err.message });
            });
        return true; // Keep channel open for async response
    }
});
