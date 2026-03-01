import { type Lang } from '../i18n';

export function initializeCompliance(app: HTMLElement, lang: Lang) {
    const modal = app.querySelector<HTMLDivElement>('#compliance-modal');
    const complianceBtn = app.querySelector<HTMLButtonElement>('.compliance-btn');
    const closeBtn = app.querySelector<HTMLButtonElement>('.close-modal');
    const analyzeBtn = app.querySelector<HTMLButtonElement>('#analyze-btn');
    const vacancyInput = app.querySelector<HTMLTextAreaElement>('#vacancy-input');
    const resultsDiv = app.querySelector<HTMLDivElement>('#analysis-results');
    const resultsContent = app.querySelector<HTMLDivElement>('.results-content');
    const turnstileContainer = app.querySelector<HTMLDivElement>('#turnstile-container');

    let turnstileWidgetId: string | null = null;

    if (complianceBtn && modal && turnstileContainer) {
        complianceBtn.addEventListener('click', () => {
            modal.classList.add('visible');
            document.body.style.overflow = 'hidden';

            const ts = (window as any).turnstile;
            if (ts && !turnstileWidgetId) {
                turnstileWidgetId = ts.render(turnstileContainer, {
                    sitekey: '0x4AAAAAACkZtRaBl09-ithU', // Managed via Vercel env in prod
                    theme: 'light',
                });
            }
        });

        const closeModal = () => {
            modal.classList.remove('visible');
            document.body.style.overflow = '';
            if (resultsDiv) resultsDiv.classList.add('hidden');
            if (resultsContent) resultsContent.innerHTML = '';
            if (vacancyInput) vacancyInput.value = '';
            const ts = (window as any).turnstile;
            if (ts && turnstileWidgetId) {
                ts.reset(turnstileWidgetId);
            }
        };

        if (closeBtn) closeBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        if (analyzeBtn && vacancyInput && resultsDiv && resultsContent) {
            analyzeBtn.addEventListener('click', async () => {
                const text = vacancyInput.value.trim();
                if (text.length < 100) {
                    alert(lang === 'ru' ? 'Текст слишком короткий.' : 'Text is too short.');
                    return;
                }

                const ts = (window as any).turnstile;
                const token = ts ? ts.getResponse() : '';

                resultsDiv.classList.remove('hidden');
                resultsDiv.classList.add('loading');
                analyzeBtn.disabled = true;

                try {
                    const response = await fetch('https://vladislav-vasilenko-github-io.vercel.app/api/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ vacancyText: text, turnstileToken: token, lang })
                    });

                    const data = await response.json();
                    if (data.error) throw new Error(data.error);

                    resultsDiv.classList.remove('loading');
                    resultsContent.innerHTML = `
            <div class="score-row">
              <div class="score-circle">
                <svg viewBox="0 0 36 36" class="circular-chart">
                  <path class="circle-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                  <path class="circle" stroke-dasharray="${data.score}, 100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                  <text x="18" y="20.35" class="percentage">${data.score}%</text>
                </svg>
              </div>
              <p class="summary-text">${data.summary}</p>
            </div>
            <div class="analysis-grid">
              <div class="analysis-col">
                <h4>✅ ${lang === 'ru' ? 'Плюсы' : 'Pros'}</h4>
                <ul>${data.pros.map((p: string) => `<li>${p}</li>`).join('')}</ul>
              </div>
              <div class="analysis-col">
                <h4>❌ ${lang === 'ru' ? 'Минусы' : 'Cons'}</h4>
                <ul>${data.cons.map((c: string) => `<li>${c}</li>`).join('')}</ul>
              </div>
            </div>
            <div class="analysis-grid">
              <div class="analysis-col">
                <h4>💪 ${lang === 'ru' ? 'Сильные стороны' : 'Strengths'}</h4>
                <ul>${data.strengths.map((s: string) => `<li>${s}</li>`).join('')}</ul>
              </div>
              <div class="analysis-col">
                <h4>⚠️ ${lang === 'ru' ? 'Точки роста' : 'Weaknesses'}</h4>
                <ul>${data.weaknesses.map((w: string) => `<li>${w}</li>`).join('')}</ul>
              </div>
            </div>
          `;
                } catch (error: any) {
                    resultsDiv.classList.remove('loading');
                    resultsContent.innerHTML = `<p class="error-text">${error.message || 'Error occurred.'}</p>`;
                } finally {
                    analyzeBtn.disabled = false;
                }
            });
        }
    }
}
