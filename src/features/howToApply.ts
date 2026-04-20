import { type Lang, type Experience } from '../i18n';

interface ApplyResponse {
    score?: number;
    summary?: string;
    pros?: string[];
    cons?: string[];
    strengths?: string[];
    weaknesses?: string[];
    improvement_tips?: string[];
    adapted_bullets?: string[];
    application_message?: string;
    error?: string;
}

export function initializeHowToApply(app: HTMLElement, lang: Lang, experience: Experience[] = []) {
    const modal = app.querySelector<HTMLDivElement>('#how-to-apply-modal');
    const openBtn = app.querySelector<HTMLButtonElement>('.how-to-apply-btn');
    const closeBtn = modal?.querySelector<HTMLButtonElement>('.close-modal');
    const runBtn = app.querySelector<HTMLButtonElement>('#how-to-apply-btn-run');
    const vacancyInput = app.querySelector<HTMLTextAreaElement>('#how-to-apply-vacancy-input');
    const modelSelect = app.querySelector<HTMLSelectElement>('#how-to-apply-model-select');
    const resultsDiv = app.querySelector<HTMLDivElement>('#how-to-apply-results');
    const resultsContent = app.querySelector<HTMLDivElement>('.how-to-apply-content');
    const turnstileContainer = app.querySelector<HTMLDivElement>('#how-to-apply-turnstile-container');

    if (!openBtn || !modal || !turnstileContainer || !runBtn || !vacancyInput || !resultsDiv || !resultsContent) return;

    let turnstileWidgetId: string | null = null;

    openBtn.addEventListener('click', () => {
        modal.classList.add('visible');
        document.body.style.overflow = 'hidden';

        const ts = (window as any).turnstile;
        if (ts && !turnstileWidgetId) {
            turnstileWidgetId = ts.render(turnstileContainer, {
                sitekey: '0x4AAAAAACkZtRaBl09-ithU',
                theme: 'light',
            });
        }
    });

    const closeModal = () => {
        modal.classList.remove('visible');
        document.body.style.overflow = '';
        resultsDiv.classList.add('hidden');
        resultsContent.innerHTML = '';
        vacancyInput.value = '';
        const ts = (window as any).turnstile;
        if (ts && turnstileWidgetId) ts.reset(turnstileWidgetId);
    };

    closeBtn?.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

    runBtn.addEventListener('click', async () => {
        const text = vacancyInput.value.trim();
        if (text.length < 100) {
            alert(lang === 'ru' ? 'Текст вакансии слишком короткий.' : 'Vacancy text is too short.');
            return;
        }

        const ts = (window as any).turnstile;
        if (!ts) {
            alert(lang === 'ru' ? 'Ошибка: Cloudflare Turnstile не загружен.' : 'Error: Cloudflare Turnstile not loaded.');
            return;
        }
        const token = ts.getResponse();
        if (!token) {
            alert(lang === 'ru' ? 'Подтвердите, что вы человек.' : 'Please confirm you are human.');
            return;
        }

        const [provider, model] = (modelSelect?.value || 'openai:gpt-5.4').split(':');

        resultsDiv.classList.remove('hidden');
        resultsDiv.classList.add('loading');
        runBtn.disabled = true;

        try {
            const response = await fetch('https://vladislav-vasilenko-github-io.vercel.app/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vacancyText: text, turnstileToken: token, lang, provider, model })
            });

            const data: ApplyResponse = await response.json();
            if (data.error) throw new Error(data.error);

            resultsDiv.classList.remove('loading');

            const tips = data.improvement_tips || [];
            const adapted = data.adapted_bullets || [];
            const appMsg = (data.application_message || '').trim();
            const strengths = data.strengths || [];
            const weaknesses = data.weaknesses || [];
            const score = typeof data.score === 'number' ? data.score : null;

            const encodedMsg = encodeURIComponent(appMsg);

            resultsContent.innerHTML = `
                ${score !== null ? `
                <div class="score-row">
                  <div class="score-circle">
                    <svg viewBox="0 0 36 36" class="circular-chart">
                      <path class="circle-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                      <path class="circle" stroke-dasharray="${score}, 100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                      <text x="18" y="20.35" class="percentage">${score}%</text>
                    </svg>
                  </div>
                  <p class="summary-text">${data.summary || ''}</p>
                </div>` : ''}

                ${tips.length > 0 ? `
                <div class="apply-block apply-block--tips">
                  <h4>🛠️ ${lang === 'ru' ? 'Что поправить в резюме (первый этап отсева)' : 'What to fix in the CV (first screening stage)'}</h4>
                  <ol>${tips.map(t => `<li>${escapeHtml(t)}</li>`).join('')}</ol>
                </div>` : ''}

                ${adapted.length > 0 ? `
                <div class="apply-block apply-block--adapted">
                  <div class="apply-block-head">
                    <h4>📄 ${lang === 'ru' ? 'Исправленные буллиты опыта под эту вакансию' : 'Adapted experience bullets for this vacancy'}</h4>
                    <button class="apply-copy-btn" data-copy-payload="${encodeURIComponent(adapted.join('\n• '))}">
                      ${lang === 'ru' ? '📋 Копировать' : '📋 Copy'}
                    </button>
                  </div>
                  <ul>${adapted.map(b => `<li>${escapeHtml(b)}</li>`).join('')}</ul>
                </div>` : ''}

                ${appMsg ? `
                <div class="apply-block apply-block--message">
                  <div class="apply-block-head">
                    <h4>✉️ ${lang === 'ru' ? 'Текст отклика для модальной формы' : 'Application message for the modal form'}</h4>
                    <button class="apply-copy-btn" data-copy-payload="${encodedMsg}">
                      ${lang === 'ru' ? '📋 Копировать' : '📋 Copy'}
                    </button>
                  </div>
                  <div class="apply-message-body">${escapeHtml(appMsg)}</div>
                </div>` : ''}

                ${(strengths.length || weaknesses.length) ? `
                <div class="analysis-grid">
                  ${strengths.length ? `
                  <div class="analysis-col">
                    <h4>💪 ${lang === 'ru' ? 'Сильные стороны' : 'Strengths'}</h4>
                    <ul>${strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
                  </div>` : ''}
                  ${weaknesses.length ? `
                  <div class="analysis-col">
                    <h4>⚠️ ${lang === 'ru' ? 'Точки роста' : 'Weaknesses'}</h4>
                    <ul>${weaknesses.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>
                  </div>` : ''}
                </div>` : ''}

                <div class="apply-block apply-block--adapt-cv">
                  <h4>📝 ${lang === 'ru' ? 'Сгенерировать адаптированное резюме (Markdown)' : 'Generate adapted CV (Markdown)'}</h4>
                  <p class="apply-hint">${lang === 'ru'
                      ? 'Отметьте общие секции и конкретные позиции опыта, которые переписать под эту вакансию. Остальные останутся как в исходном CV.'
                      : 'Select the general sections and specific experience positions to rewrite for this vacancy. The rest stays untouched.'}</p>

                  <div class="adapt-cv-section-group">
                    <strong>${lang === 'ru' ? 'Общие секции:' : 'General sections:'}</strong>
                    <div class="adapt-cv-sections">
                      <label><input type="checkbox" value="headline" checked> ${lang === 'ru' ? 'Headline / Заголовок' : 'Headline / Title'}</label>
                      <label><input type="checkbox" value="summary" checked> ${lang === 'ru' ? 'Обо мне / Summary' : 'Summary / About'}</label>
                      <label><input type="checkbox" value="skills" checked> ${lang === 'ru' ? 'Навыки' : 'Skills'}</label>
                      <label><input type="checkbox" value="education"> ${lang === 'ru' ? 'Образование' : 'Education'}</label>
                    </div>
                  </div>

                  ${experience.length > 0 ? `
                  <div class="adapt-cv-section-group">
                    <div class="adapt-cv-exp-header">
                      <strong>${lang === 'ru' ? 'Позиции опыта (перепишем буллиты):' : 'Experience positions (rewrite bullets):'}</strong>
                      <div class="adapt-cv-exp-toggles">
                        <button type="button" class="adapt-cv-exp-all">${lang === 'ru' ? 'Все' : 'All'}</button>
                        <button type="button" class="adapt-cv-exp-none">${lang === 'ru' ? 'Ни одной' : 'None'}</button>
                      </div>
                    </div>
                    <div class="adapt-cv-experience">
                      ${experience.map(exp => `
                        <label class="adapt-cv-exp-item">
                          <input type="checkbox" class="adapt-cv-exp-checkbox" value="${escapeHtml(exp.id)}">
                          <span class="adapt-cv-exp-company">${escapeHtml(exp.company)}</span>
                          <span class="adapt-cv-exp-role">${escapeHtml(exp.role)}</span>
                          <span class="adapt-cv-exp-period">${escapeHtml(exp.period)}</span>
                        </label>
                      `).join('')}
                    </div>
                  </div>` : ''}

                  <div class="adapt-cv-tone">
                    <label>${lang === 'ru' ? 'Стиль:' : 'Tone:'}</label>
                    <select id="adapt-cv-tone-select">
                      <option value="concise">${lang === 'ru' ? 'Сжатый' : 'Concise'}</option>
                      <option value="balanced" selected>${lang === 'ru' ? 'Сбалансированный' : 'Balanced'}</option>
                      <option value="detailed">${lang === 'ru' ? 'Подробный' : 'Detailed'}</option>
                    </select>
                  </div>
                  <button id="adapt-cv-run-btn" class="primary-btn adapt-cv-btn">
                    ${lang === 'ru' ? '⚡ Сгенерировать Markdown' : '⚡ Generate Markdown'}
                  </button>
                  <div id="adapt-cv-output" class="adapt-cv-output hidden"></div>
                </div>
            `;

            resultsContent.querySelectorAll<HTMLButtonElement>('.apply-copy-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const payload = decodeURIComponent(btn.dataset.copyPayload || '');
                    try {
                        await navigator.clipboard.writeText(payload);
                        const original = btn.innerHTML;
                        btn.innerHTML = lang === 'ru' ? '✅ Скопировано' : '✅ Copied';
                        setTimeout(() => { btn.innerHTML = original; }, 2500);
                    } catch (err) {
                        alert(lang === 'ru' ? 'Не удалось скопировать.' : 'Copy failed.');
                    }
                });
            });

            // --- Adapted CV (Markdown) generation ---
            const adaptBtn = resultsContent.querySelector<HTMLButtonElement>('#adapt-cv-run-btn');
            const adaptOutput = resultsContent.querySelector<HTMLDivElement>('#adapt-cv-output');
            const toneSelect = resultsContent.querySelector<HTMLSelectElement>('#adapt-cv-tone-select');

            // Bulk toggles for experience positions
            resultsContent.querySelector<HTMLButtonElement>('.adapt-cv-exp-all')?.addEventListener('click', () => {
                resultsContent.querySelectorAll<HTMLInputElement>('.adapt-cv-exp-checkbox').forEach(cb => cb.checked = true);
            });
            resultsContent.querySelector<HTMLButtonElement>('.adapt-cv-exp-none')?.addEventListener('click', () => {
                resultsContent.querySelectorAll<HTMLInputElement>('.adapt-cv-exp-checkbox').forEach(cb => cb.checked = false);
            });

            adaptBtn?.addEventListener('click', async () => {
                const selectedSections = Array.from(
                    resultsContent.querySelectorAll<HTMLInputElement>('.adapt-cv-sections input[type="checkbox"]:checked')
                ).map(cb => cb.value);

                const selectedExperienceIds = Array.from(
                    resultsContent.querySelectorAll<HTMLInputElement>('.adapt-cv-exp-checkbox:checked')
                ).map(cb => cb.value);

                // If any experience position is selected, include "experience" as a section signal.
                if (selectedExperienceIds.length > 0 && !selectedSections.includes('experience')) {
                    selectedSections.push('experience');
                }

                if (selectedSections.length === 0 && selectedExperienceIds.length === 0) {
                    alert(lang === 'ru' ? 'Выберите хотя бы одну секцию или позицию опыта.' : 'Select at least one section or experience position.');
                    return;
                }

                if (!adaptOutput) return;
                adaptOutput.classList.remove('hidden');
                adaptOutput.innerHTML = `<div class="analysis-loader"><div class="spinner"></div><span>${lang === 'ru' ? 'Собираем Markdown-резюме...' : 'Building Markdown resume...'}</span></div>`;
                adaptBtn.disabled = true;

                try {
                    const response = await fetch('https://vladislav-vasilenko-github-io.vercel.app/api/adapt-cv', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            vacancyText: text,
                            lang,
                            provider,
                            model,
                            sections: selectedSections,
                            experience_ids: selectedExperienceIds,
                            tone: toneSelect?.value || 'balanced'
                        })
                    });
                    const out = await response.json();
                    if (out.error) throw new Error(out.error);

                    const md = (out.markdown || '').trim();
                    const encoded = encodeURIComponent(md);
                    const changed = (out.changed_sections || []).join(', ');
                    const notes = (out.notes || '').trim();

                    adaptOutput.innerHTML = `
                        <div class="adapt-cv-meta">
                            ${changed ? `<span class="adapt-cv-changed">${lang === 'ru' ? 'Изменено:' : 'Changed:'} ${escapeHtml(changed)}</span>` : ''}
                            ${notes ? `<span class="adapt-cv-notes">${escapeHtml(notes)}</span>` : ''}
                        </div>
                        <div class="adapt-cv-actions">
                            <button class="apply-copy-btn" data-copy-payload="${encoded}">
                                ${lang === 'ru' ? '📋 Копировать Markdown' : '📋 Copy Markdown'}
                            </button>
                            <button class="adapt-cv-download-btn">
                                ${lang === 'ru' ? '⬇️ Скачать .md' : '⬇️ Download .md'}
                            </button>
                        </div>
                        <textarea class="adapt-cv-textarea" readonly>${escapeHtml(md)}</textarea>
                    `;

                    adaptOutput.querySelector<HTMLButtonElement>('.apply-copy-btn')?.addEventListener('click', async (e) => {
                        const btn = e.currentTarget as HTMLButtonElement;
                        try {
                            await navigator.clipboard.writeText(md);
                            const original = btn.innerHTML;
                            btn.innerHTML = lang === 'ru' ? '✅ Скопировано' : '✅ Copied';
                            setTimeout(() => { btn.innerHTML = original; }, 2500);
                        } catch {
                            alert(lang === 'ru' ? 'Не удалось скопировать.' : 'Copy failed.');
                        }
                    });

                    adaptOutput.querySelector<HTMLButtonElement>('.adapt-cv-download-btn')?.addEventListener('click', () => {
                        const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `cv-adapted-${Date.now()}.md`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                    });
                } catch (err: any) {
                    adaptOutput.innerHTML = `<p class="error-text">${err.message || 'Error occurred.'}</p>`;
                } finally {
                    adaptBtn.disabled = false;
                }
            });
        } catch (error: any) {
            resultsDiv.classList.remove('loading');
            resultsContent.innerHTML = `<p class="error-text">${error.message || 'Error occurred.'}</p>`;
        } finally {
            runBtn.disabled = false;
        }
    });
}

function escapeHtml(s: string): string {
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
