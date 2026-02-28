const CV_API_URL = 'https://vladislav-vasilenko-github-io.vercel.app/api/cv?lang=en';

let cvData = null;

async function loadCV() {
  const statusEl = document.getElementById('status');
  statusEl.textContent = 'Loading CV data...';
  statusEl.style.color = 'var(--accent)';

  try {
    const res = await fetch(CV_API_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    cvData = await res.json();
    statusEl.textContent = `Loaded ${cvData.experience.length} positions`;
    statusEl.style.color = '#10b981';
    document.getElementById('autofill-btn').disabled = false;
  } catch (err) {
    statusEl.textContent = `Failed to load CV: ${err.message}`;
    statusEl.style.color = '#ef4444';
  }
}

document.getElementById('autofill-btn').disabled = true;
loadCV();

document.getElementById('autofill-btn').addEventListener('click', async () => {
  if (!cvData) return;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  const statusEl = document.getElementById('status');
  statusEl.textContent = 'Injecting...';
  statusEl.style.color = 'var(--accent)';

  chrome.tabs.sendMessage(tab.id, {
    action: 'autofill_experience',
    data: cvData.experience
  }, (response) => {
    if (chrome.runtime.lastError) {
      statusEl.textContent = 'Error: Content script not loaded';
      statusEl.style.color = '#ef4444';
    } else if (response && response.status === 'success') {
      statusEl.textContent = `Success! Filled ${response.filled} sections`;
      statusEl.style.color = '#10b981';
    }
  });
});
