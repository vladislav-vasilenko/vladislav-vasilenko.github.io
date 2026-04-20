interface Vacancy {
    id: string;
    title: string;
    company: string;
    pub_date?: string;
    link: string;
    ats_score: number;
    cosine_distance: number;
    reasoning: string;
    missing_keywords: string[];
    is_good_match: boolean;
    adapted_bullets?: string[];
    sphere?: string;
    matched_keywords?: string[];
    origin_queries?: string[];
    cl_path?: string;
    is_big_tech?: boolean;
    is_foreign?: boolean;
    improvement_tips?: string[];
    application_message?: string;
}

interface ScatterPoint {
    id: string;
    title: string;
    company: string;
    sphere?: string;
    ats_score?: number;
    is_big_tech?: boolean;
    is_foreign?: boolean;
    is_cv: boolean;
    x: number;
    y: number;
    z: number;
}

interface MatcherData {
    last_updated: string;
    total_jobs_in_db?: number;
    vacancies: Vacancy[];
    scatter_3d?: ScatterPoint[];
}

let allVacancies: Vacancy[] = [];
let scatterData: ScatterPoint[] = [];

async function loadData() {
    try {
        // Cache busting: добавляем timestamp, чтобы браузер не брал старый json из кэша
        const response = await fetch(`/matcher_data.json?t=${new Date().getTime()}`);
        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status}`);
        }
        
        const data: MatcherData = await response.json();
        allVacancies = data.vacancies;
        if (data.scatter_3d) {
            scatterData = data.scatter_3d;
        }
        
        // Update timestamp & total DB sum
        const dt = new Date(data.last_updated);
        document.getElementById('last-updated')!.textContent = `Last Pipeline Run: ${dt.toLocaleString()}`;
        
        if (data.total_jobs_in_db !== undefined) {
             document.getElementById('total-db-count')!.textContent = `Total AI Market DB: ${data.total_jobs_in_db} vacancies parsed`;
        } else {
             document.getElementById('total-db-count')!.style.display = 'none';
        }
        
        // Populate Company Filter
        const companies = new Set(allVacancies.map(v => v.company));
        const companySelect = document.getElementById('company-filter') as HTMLSelectElement;
        
        companies.forEach(comp => {
            const opt = document.createElement('option');
            opt.value = comp;
            opt.textContent = comp;
            companySelect.appendChild(opt);
        });
        
        document.getElementById('loading')!.style.display = 'none';
        
        if (scatterData.length > 0) {
            render3DChart();
            
            // Setup Toggle Button
            const toggleBtn = document.getElementById('toggle-3d-btn')!;
            const plotDiv = document.getElementById('scatter-3d-plot')!;
            toggleBtn.style.display = 'inline-block';
            toggleBtn.addEventListener('click', () => {
                 if (plotDiv.style.display === 'none') {
                     plotDiv.style.display = 'block';
                 } else {
                     plotDiv.style.display = 'none';
                 }
            });
            // Auto-hide initially to save space, user can click to open
            plotDiv.style.display = 'none';
        }
        
        renderVacancies();
    } catch (e) {
        document.getElementById('loading')!.textContent = `❌ Error loading data: ${e}. Have you run 'uv run cv_matcher.py' at least once?`;
    }
}

function renderHtml(v: Vacancy): string {
    const scoreClass = v.ats_score >= 80 ? 'ats-high' : (v.ats_score >= 50 ? 'ats-med' : 'ats-low');
    let goodMatchBadge = v.is_good_match ? '<span class="badge" style="background: #28a745; color: white;">Best Match</span>' : '';
    let bigTechBadge = v.is_big_tech ? `<span class="badge" style="background: #007bff; color: white; margin-left: 5px;">🏛️ Tier-1 ${v.is_foreign ? 'Global' : 'BigTech'}</span>` : '';
    let foreignBadge = v.is_foreign ? '<span class="badge" style="background: #e83e8c; color: white; margin-left: 5px;">🌍 International</span>' : '';

    let missingKeywordsHtml = '';
    if (v.missing_keywords && v.missing_keywords.length > 0) {
        missingKeywordsHtml = `<div class="missing">⚠️ Missing JD Keywords: ${v.missing_keywords.join(', ')}</div>`;
    }
    
    let adaptedBulletsHtml = '';
    if (v.adapted_bullets && v.adapted_bullets.length > 0) {
        adaptedBulletsHtml = `
            <div style="margin-top: 10px; padding: 15px; background: #eef2f5; border-left: 4px solid #007bff; border-radius: 4px;">
                <strong style="color: #0056b3; font-size: 13px;">💡 Smart CV Adaptation for this role:</strong>
                <ul style="margin: 5px 0 10px 0; padding-left: 20px; font-size: 13px; color: #444;">
                    ${v.adapted_bullets.map(b => `<li>${b}</li>`).join('')}
                </ul>
                <a href="/adapted_cvs/${v.id}.html" target="_blank" style="display: inline-block; background: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 13px; font-weight: bold;">📄 Открыть адаптированное резюме (HTML/PDF)</a>
            </div>
        `;
    }
    
    let matchedKeywordsHtml = '';
    if (v.matched_keywords && v.matched_keywords.length > 0) {
        matchedKeywordsHtml = `
            <div style="margin-top: 5px;">
                <strong style="font-size: 12px; color: #28a745;">✅ Matched Skills:</strong>
                <div style="display: flex; flex-wrap: wrap; gap: 5px; margin-top: 3px;">
                    ${v.matched_keywords.map(k => `<span class="badge" style="background: #d4edda; color: #155724; border: 1px solid #c3e6cb; font-size: 11px; padding: 2px 6px;">${k}</span>`).join('')}
                </div>
            </div>
        `;
    }

    let originQueriesHtml = '';
    if (v.origin_queries && v.origin_queries.length > 0) {
        originQueriesHtml = `
            <div style="margin-top: 10px; font-size: 11px; color: #999; border-top: 1px dashed #eee; pt: 5px;">
                🔍 Found via: ${v.origin_queries.join(', ')}
            </div>
        `;
    }

    let clButton = '';
    if (v.cl_path) {
        clButton = `
            <button class="cl-btn" onclick="copyCL('${v.cl_path}', this)" style="margin-top: 10px; padding: 6px 12px; background: #6f42c1; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px;">
                📝 Copy AI Cover Letter
            </button>
        `;
    }

    let improvementTipsHtml = '';
    if (v.improvement_tips && v.improvement_tips.length > 0) {
        improvementTipsHtml = `
            <div style="margin-top: 10px; padding: 15px; background: #fff8e1; border-left: 4px solid #f0ad4e; border-radius: 4px;">
                <strong style="color: #8a6d3b; font-size: 13px;">🛠️ Что поправить в CV под первый этап отсева:</strong>
                <ol style="margin: 5px 0 0 0; padding-left: 22px; font-size: 13px; color: #444; line-height: 1.5;">
                    ${v.improvement_tips.map(t => `<li style="margin-bottom: 5px;">${t}</li>`).join('')}
                </ol>
            </div>
        `;
    }

    let applicationMessageHtml = '';
    if (v.application_message && v.application_message.trim().length > 0) {
        const encoded = encodeURIComponent(v.application_message);
        applicationMessageHtml = `
            <div style="margin-top: 10px; padding: 15px; background: #e8f5e9; border-left: 4px solid #28a745; border-radius: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <strong style="color: #1b5e20; font-size: 13px;">✉️ Текст отклика (для модальной формы):</strong>
                    <button onclick="copyApplicationMsg(decodeURIComponent('${encoded}'), this)" style="padding: 5px 10px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold;">
                        📋 Скопировать
                    </button>
                </div>
                <div style="font-size: 13px; color: #2e3b2e; white-space: pre-wrap; line-height: 1.5; background: white; padding: 10px; border-radius: 4px; border: 1px solid #c8e6c9;">${v.application_message}</div>
            </div>
        `;
    }

    return `
        <div class="vacancy-card ${v.is_big_tech ? 'big-tech-highlight' : ''} ${v.is_foreign ? 'foreign-highlight' : ''}">
            <div class="v-header">
                <div>
                    <a href="${v.link}" target="_blank" class="v-title">${v.is_foreign ? '🌍 ' : ''}${v.title}</a>
                    <div class="v-company">🏢 ${v.company} &bull; 🕒 ${v.pub_date || 'Неизвестно'} ${goodMatchBadge} ${bigTechBadge} ${foreignBadge}</div>
                </div>
                <div style="font-size: 12px; color: #666; background: #f0f0f0; padding: 2px 8px; border-radius: 10px;">${v.sphere || 'Other'}</div>
            </div>
            <div class="scores">
                <span class="badge ${scoreClass}">ATS Score: ${v.ats_score}%</span>
                <span class="badge">Cosine Distance: ${(v.cosine_distance).toFixed(3)}</span>
            </div>
            <div class="reasoning">
                <strong>AI Review:</strong> ${v.reasoning}
            </div>
            ${matchedKeywordsHtml}
            ${missingKeywordsHtml}
            ${improvementTipsHtml}
            ${applicationMessageHtml}
            ${clButton}
            ${adaptedBulletsHtml}
            ${originQueriesHtml}
        </div>
    `;
}

function renderVacancies() {
    const companyFilter = (document.getElementById('company-filter') as HTMLSelectElement).value;
    const scoreFilter = parseInt((document.getElementById('score-filter') as HTMLSelectElement).value, 10);
    
    const container = document.getElementById('results-container')!;
    
    const filtered = allVacancies.filter(v => {
        const matchesCompany = companyFilter === 'All' || v.company === companyFilter;
        const matchesScore = v.ats_score >= scoreFilter;
        return matchesCompany && matchesScore;
    });
    
    if (filtered.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding: 20px; color:#888;">No vacancies match your filters.</div>`;
        return;
    }
    
    container.innerHTML = filtered.map(renderHtml).join('');
}

// Plotly Render Logic
function render3DChart() {
    const plotDiv = document.getElementById('scatter-3d-plot')!;
    plotDiv.style.display = 'block';

    const cvPoint = scatterData.find(p => p.is_cv);
    const jobPoints = scatterData.filter(p => !p.is_cv);

    // Get Plotly from window
    const Plotly = (window as any).Plotly;
    if (!Plotly) return;

    // Группируем вакансии по сферам
    const spheres = [...new Set(jobPoints.map(p => p.sphere || 'Other'))];
    
    // Цветовая палитра для сфер
    const colorMap: Record<string, string> = {
        'GenAI / LLM': '#FFD700',      // Gold
        'Computer Vision': '#2ECC71',  // Emerald Green
        'ML / Data Science': '#9B59B6', // Amethyst Purple
        'Audio / Speech': '#E67E22',   // Carrot Orange
        'Backend': '#3498DB',          // Peter River Blue
        'Mobile': '#1ABC9C',           // Turquoise
        'Product / Management': '#F1C40F', // Sun Flower Yellow
        'Other': '#BDC3C7'             // Silver
    };

    const traces: any[] = [];

    // Трейс для Резюме
    if (cvPoint) {
        traces.push({
            x: [cvPoint.x],
            y: [cvPoint.y],
            z: [cvPoint.z],
            mode: 'markers+text',
            type: 'scatter3d',
            name: '⭐ ВАШЕ РЕЗЮМЕ',
            text: ['ВАШЕ РЕЗЮМЕ'],
            textposition: 'top center',
            marker: { size: 10, color: '#E74C3C', symbol: 'diamond', line: { color: 'white', width: 2 } },
            hoverinfo: 'text'
        });
    }

    // Трейсы для каждой сферы
    spheres.forEach(sphere => {
        const points = jobPoints.filter(p => (p.sphere || 'Other') === sphere);
        
        // Вычисляем размеры на основе ats_score (от 4 до 15)
        const sizes = points.map(p => {
            const score = p.ats_score || 0;
            return 4 + (score / 100) * 12; 
        });

        // Вычисляем прозрачность на основе ats_score (от 0.3 до 1.0)
        const opacities = points.map(p => {
            const score = p.ats_score || 0;
            return 0.3 + (score / 100) * 0.7;
        });

        traces.push({
            x: points.map(p => p.x),
            y: points.map(p => p.y),
            z: points.map(p => p.z),
            mode: 'markers',
            type: 'scatter3d',
            name: sphere,
            text: points.map(p => `${p.is_foreign ? '🌍 ' : ''}${p.title}<br>${p.company}${p.is_big_tech ? ' (Tier-1)' : ''}<br>Сфера: ${sphere}<br>ATS Match: ${p.ats_score || 0}%`),
            marker: { 
                size: sizes, 
                symbol: points.map(p => {
                    if (p.is_foreign) return p.is_big_tech ? 'star' : 'square';
                    return p.is_big_tech ? 'diamond' : 'circle';
                }),
                color: colorMap[sphere] || '#7F8C8D', 
                opacity: opacities,
                line: {
                    color: points.map(p => {
                        if (p.is_foreign) return '#FF00FF'; // Neon Magenta for International
                        return p.is_big_tech ? '#FFFFFF' : colorMap[sphere] || '#7F8C8D';
                    }),
                    width: points.map(p => p.is_foreign ? 2.0 : (p.is_big_tech ? 1.5 : 0.5))
                }
            },
            hoverinfo: 'text'
        });
    });

    const layout = {
        margin: { l: 0, r: 0, b: 0, t: 30 },
        paper_bgcolor: '#f4f7f6',
        scene: {
            xaxis: { title: 'PCA 1', gridcolor: '#eee' },
            yaxis: { title: 'PCA 2', gridcolor: '#eee' },
            zaxis: { title: 'PCA 3', gridcolor: '#eee' },
            bgcolor: '#ffffff'
        },
        legend: {
            orientation: 'h',
            y: 0
        },
        title: {
            text: 'Семантическая карта рынка (кластеризация по сферам)',
            font: { size: 16, color: '#2c3e50' }
        }
    };

    Plotly.newPlot('scatter-3d-plot', traces, layout);
}

// Attach Event Listeners
document.getElementById('company-filter')?.addEventListener('change', renderVacancies);
document.getElementById('score-filter')?.addEventListener('change', renderVacancies);

// Helper for copying the application message (modal form text)
(window as any).copyApplicationMsg = async (text: string, btn: HTMLButtonElement) => {
    try {
        await navigator.clipboard.writeText(text);
        const original = btn.innerHTML;
        btn.innerHTML = '✅ Скопировано';
        setTimeout(() => { btn.innerHTML = original; }, 2500);
    } catch (err) {
        console.error('Clipboard failed:', err);
        alert('Не удалось скопировать в буфер обмена.');
    }
};

// Helper for copying Cover Letter
(window as any).copyCL = async (path: string, btn: HTMLButtonElement) => {
    try {
        const response = await fetch(path);
        const text = await response.text();
        await navigator.clipboard.writeText(text);
        
        const originalText = btn.innerHTML;
        btn.innerHTML = '✅ Copied to Clipboard!';
        btn.style.background = '#28a745';
        
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.style.background = '#6f42c1';
        }, 3000);
    } catch (err) {
        console.error('Failed to copy CL:', err);
        alert('Failed to load cover letter.');
    }
};

// Init
document.addEventListener("DOMContentLoaded", () => {
    loadData();
});
