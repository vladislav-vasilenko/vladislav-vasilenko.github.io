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
}

interface ScatterPoint {
    id: string;
    title: string;
    company: string;
    is_cv: boolean;
    x: number;
    y: number;
    z: number;
}

interface MatcherData {
    last_updated: string;
    vacancies: Vacancy[];
    scatter_3d?: ScatterPoint[];
}

let allVacancies: Vacancy[] = [];
let scatterData: ScatterPoint[] = [];

async function loadData() {
    try {
        const response = await fetch('/matcher_data.json');
        if (!response.ok) {
            throw new Error(`HTTP Error: ${response.status}`);
        }
        
        const data: MatcherData = await response.json();
        allVacancies = data.vacancies;
        if (data.scatter_3d) {
            scatterData = data.scatter_3d;
        }
        
        // Update timestamp
        const dt = new Date(data.last_updated);
        document.getElementById('last-updated')!.textContent = `Last Updated: ${dt.toLocaleString()} (via Github Actions)`;
        
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
        }
        
        renderVacancies();
    } catch (e) {
        document.getElementById('loading')!.textContent = `❌ Error loading data: ${e}. Have you run 'uv run cv_matcher.py' at least once?`;
    }
}

function renderHtml(v: Vacancy): string {
    const scoreClass = v.ats_score >= 80 ? 'ats-high' : (v.ats_score >= 50 ? 'ats-med' : 'ats-low');
    const goodMatchBadge = v.is_good_match ? `<span title="Passed Hard Requirements">⭐ Good Match</span>` : '';
    
    let missingKeywordsHtml = '';
    if (v.missing_keywords && v.missing_keywords.length > 0) {
        missingKeywordsHtml = `<div class="missing">⚠️ Missing CV Keywords: ${v.missing_keywords.join(', ')}</div>`;
    }
    
    return `
        <div class="vacancy-card">
            <div class="v-header">
                <div>
                    <a href="${v.link}" target="_blank" class="v-title">${v.title}</a>
                    <div class="v-company">🏢 ${v.company} &bull; 🕒 ${v.pub_date || 'Неизвестно'} ${goodMatchBadge}</div>
                </div>
            </div>
            <div class="scores">
                <span class="badge ${scoreClass}">ATS Score: ${v.ats_score}%</span>
                <span class="badge">Cosine Distance: ${(v.cosine_distance).toFixed(3)}</span>
            </div>
            <div class="reasoning">
                <strong>AI Review:</strong> ${v.reasoning}
            </div>
            ${missingKeywordsHtml}
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

    const cvTrace = {
        x: cvPoint ? [cvPoint.x] : [],
        y: cvPoint ? [cvPoint.y] : [],
        z: cvPoint ? [cvPoint.z] : [],
        mode: 'markers+text',
        type: 'scatter3d',
        name: 'My CV',
        text: ['⭐ YOUR RESUME'],
        textposition: 'top center',
        marker: { size: 12, color: 'red', symbol: 'diamond' },
        hoverinfo: 'text'
    };

    const jobsTrace = {
        x: jobPoints.map(p => p.x),
        y: jobPoints.map(p => p.y),
        z: jobPoints.map(p => p.z),
        mode: 'markers',
        type: 'scatter3d',
        name: 'Vacancies',
        text: jobPoints.map(p => `${p.title}<br>${p.company}`),
        marker: { size: 6, color: '#007bff', opacity: 0.8 },
        hoverinfo: 'text'
    };

    const layout = {
        margin: { l: 0, r: 0, b: 0, t: 30 },
        title: '3D Semantic Space (PCA) of Vacancies & CV',
        scene: {
            xaxis: { title: 'PCA 1' },
            yaxis: { title: 'PCA 2' },
            zaxis: { title: 'PCA 3' }
        }
    };

    Plotly.newPlot('scatter-3d-plot', [cvTrace, jobsTrace], layout);
}

// Attach Event Listeners
document.getElementById('company-filter')?.addEventListener('change', renderVacancies);
document.getElementById('score-filter')?.addEventListener('change', renderVacancies);

// Init
document.addEventListener("DOMContentLoaded", () => {
    loadData();
});
