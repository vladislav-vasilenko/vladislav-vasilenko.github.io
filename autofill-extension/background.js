chrome.runtime.onInstalled.addListener(() => {
    chrome.contextMenus.create({
        id: "smart-fill-ai",
        title: "✨ Smart Fill with AI",
        contexts: ["editable"]
    });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === "smart-fill-ai") {
        chrome.tabs.sendMessage(tab.id, { action: "trigger_ai_fill" });
    }
});
