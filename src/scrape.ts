const SERVER = "http://localhost:8787";
const JOB_KEY = "scrape_job_id";

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
const serverBadge  = document.getElementById("server-badge")!;
const offlineNotice = document.getElementById("offline-notice")!;
const sourceGroups = document.getElementById("source-groups")!;
const chipArea     = document.getElementById("chip-area")!;
const chipInput    = document.getElementById("chip-input") as HTMLInputElement;
const customTA     = document.getElementById("custom-queries") as HTMLTextAreaElement;
const limitInput   = document.getElementById("limit-input") as HTMLInputElement;
const startBtn     = document.getElementById("start-btn") as HTMLButtonElement;
const livePanel    = document.getElementById("live-panel")!;
const progressBar  = document.getElementById("progress-bar")!;
const progressLabel = document.getElementById("progress-label")!;
const progressCount = document.getElementById("progress-count")!;
const last5List    = document.getElementById("last5-list")!;
const logWrap      = document.getElementById("log-wrap")!;
const doneBanner   = document.getElementById("done-banner")!;
const doneText     = document.getElementById("done-text")!;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let sourcesData: Record<string, string[]> = {};
let authEnv: Record<string, boolean> = {};
let defaultQueries: string[] = [];
let chips: string[] = [];
let currentEs: EventSource | null = null;
let progressTotal = 0;
const last5: { title: string; company: string; link: string }[] = [];

// ---------------------------------------------------------------------------
// Health check + source loading
// ---------------------------------------------------------------------------
async function init() {
    try {
        const r = await fetch(`${SERVER}/health`, { signal: AbortSignal.timeout(3000) });
        if (!r.ok) throw new Error();
        const data = await r.json();
        serverBadge.textContent = `✓ Server online (${data.registry_size} sources)`;
        serverBadge.className = "server-badge ok";
        offlineNotice.classList.remove("visible");
        await loadSources();
        startBtn.disabled = false;
        tryReconnect();
    } catch {
        serverBadge.textContent = "✗ Server offline";
        serverBadge.className = "server-badge err";
        offlineNotice.classList.add("visible");
        startBtn.disabled = true;
    }
}

async function loadSources() {
    const r = await fetch(`${SERVER}/scrape/sources`);
    const data = await r.json();
    sourcesData = data.groups;
    authEnv = data.auth_env ?? {};
    defaultQueries = data.default_queries ?? [];

    // Render chip set from default queries
    chips = [...defaultQueries];
    renderChips();

    // Render source checkboxes grouped
    const groupLabels: Record<string, string> = {
        ru: "🇷🇺 RU",
        international: "🌍 International",
        faang: "⭐ FAANG",
    };
    sourceGroups.innerHTML = "";
    for (const [group, keys] of Object.entries(sourcesData)) {
        if (group === "all") continue;
        const el = document.createElement("div");
        el.className = "source-group";
        el.innerHTML = `
            <div class="source-group-header">
                <strong>${groupLabels[group] ?? group}</strong>
                <button class="group-toggle" data-group="${group}">all</button>
            </div>
            <div class="source-list" id="grp-${group}"></div>
        `;
        const list = el.querySelector(`#grp-${group}`)!;
        for (const key of keys as string[]) {
            const hasAuth = authEnv[key];
            const item = document.createElement("label");
            item.className = "source-item";
            item.innerHTML = `
                <input type="checkbox" data-source="${key}" checked />
                ${key}
                ${hasAuth ? `<span class="auth-tag">🔐 auth</span>` : ""}
            `;
            list.appendChild(item);
        }
        sourceGroups.appendChild(el);
    }

    // Group toggle buttons (select all / none)
    sourceGroups.querySelectorAll<HTMLButtonElement>(".group-toggle").forEach(btn => {
        btn.addEventListener("click", () => {
            const group = btn.dataset.group!;
            const boxes = sourceGroups.querySelectorAll<HTMLInputElement>(
                `#grp-${group} input[type="checkbox"]`
            );
            const allChecked = [...boxes].every(b => b.checked);
            boxes.forEach(b => { b.checked = !allChecked; });
            btn.textContent = allChecked ? "all" : "none";
        });
    });
}

// ---------------------------------------------------------------------------
// Query mode toggle
// ---------------------------------------------------------------------------
document.querySelectorAll<HTMLInputElement>('input[name="mode"]').forEach(radio => {
    radio.addEventListener("change", () => {
        document.getElementById("panel-cv")!.classList.toggle("active", radio.value === "cv-matched");
        document.getElementById("panel-custom")!.classList.toggle("active", radio.value === "custom");
    });
});

// ---------------------------------------------------------------------------
// Chip management
// ---------------------------------------------------------------------------
function renderChips() {
    // Remove existing chips (keep the input)
    chipArea.querySelectorAll(".chip").forEach(c => c.remove());
    for (const q of chips) {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.innerHTML = `${q} <button class="chip-remove" title="Remove">×</button>`;
        chip.querySelector(".chip-remove")!.addEventListener("click", () => {
            chips = chips.filter(c => c !== q);
            renderChips();
        });
        chipArea.insertBefore(chip, chipInput);
    }
}

chipInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && chipInput.value.trim()) {
        e.preventDefault();
        const v = chipInput.value.trim();
        if (!chips.includes(v)) chips.push(v);
        chipInput.value = "";
        renderChips();
    }
    if (e.key === "Backspace" && chipInput.value === "" && chips.length) {
        chips.pop();
        renderChips();
    }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function getSelectedSources(): string[] {
    return [...sourceGroups.querySelectorAll<HTMLInputElement>("input[data-source]:checked")]
        .map(b => b.dataset.source!);
}

function getQueries(): string[] {
    const mode = (document.querySelector<HTMLInputElement>('input[name="mode"]:checked'))?.value;
    if (mode === "custom") {
        return customTA.value.split("\n").map(s => s.trim()).filter(Boolean);
    }
    return chips.filter(Boolean);
}

function log(msg: string, cls: "info" | "ok" | "warn" | "err" | "vacancy" = "info") {
    const line = document.createElement("p");
    line.className = `log-line ${cls}`;
    line.textContent = `${new Date().toLocaleTimeString()} — ${msg}`;
    logWrap.appendChild(line);
    logWrap.scrollTop = logWrap.scrollHeight;
}

function pushVacancy(title: string, company: string, link: string) {
    last5.unshift({ title, company, link });
    if (last5.length > 5) last5.pop();
    last5List.innerHTML = last5.map(v => `
        <li>
            <a href="${v.link}" target="_blank" rel="noopener">${v.title}</a>
            <span class="last5-company">· ${v.company}</span>
        </li>
    `).join("");
}

function setProgress(done: number, total: number, label: string) {
    progressTotal = total;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    (progressBar as HTMLElement).style.width = `${pct}%`;
    progressLabel.textContent = label;
    progressCount.textContent = total > 0 ? `${done} / ${total}` : "";
}

// ---------------------------------------------------------------------------
// SSE event handling
// ---------------------------------------------------------------------------
function handleEvent(e: MessageEvent) {
    let data: Record<string, unknown>;
    try { data = JSON.parse(e.data); } catch { return; }

    switch (data.type) {
        case "ping":
            break;
        case "progress":
            setProgress(data.done as number, data.total as number,
                `Scraping ${data.source}…`);
            log(`▶ Starting ${data.source} (${data.done}/${data.total})`, "info");
            break;
        case "source_start":
            log(`🔍 ${data.company}: query "${data.query}"`, "info");
            break;
        case "source_done":
            log(`✓ ${data.company}: ${data.count} found`, "ok");
            break;
        case "vacancy":
            pushVacancy(data.title as string, data.company as string, data.link as string);
            log(`  + ${data.title} @ ${data.company}`, "vacancy");
            break;
        case "error":
            log(`✗ ${data.source}: ${data.message}`, "err");
            break;
        case "done":
            setProgress(progressTotal, progressTotal, "Done!");
            log(`✅ Scraping complete — ${data.total_new} new, ${data.total_in_db} total in DB`, "ok");
            doneText.textContent = `✅ Done! ${data.total_new} new vacancies added. Run cv_matcher.py for ATS scoring.`;
            doneBanner.classList.add("visible");
            currentEs?.close();
            currentEs = null;
            localStorage.removeItem(JOB_KEY);
            startBtn.disabled = false;
            startBtn.textContent = "Start Scraping";
            break;
    }
}

// ---------------------------------------------------------------------------
// Start / reconnect
// ---------------------------------------------------------------------------
async function startScraping() {
    const sources = getSelectedSources();
    const queries = getQueries();
    if (!sources.length) { alert("Select at least one source."); return; }
    if (!queries.length) { alert("Add at least one query."); return; }

    startBtn.disabled = true;
    startBtn.textContent = "Scraping…";
    livePanel.classList.add("visible");
    doneBanner.classList.remove("visible");
    last5.splice(0);
    last5List.innerHTML = '<li style="color:#999;border:none;background:none">Waiting for first vacancy…</li>';
    logWrap.innerHTML = "";
    setProgress(0, sources.length, "Starting…");

    const body = {
        sources,
        queries,
        mode: (document.querySelector<HTMLInputElement>('input[name="mode"]:checked'))?.value ?? "cv-matched",
        limit: parseInt(limitInput.value) || 20,
    };

    log(`Launching job: ${sources.length} sources, ${queries.length} queries`, "info");

    try {
        const r = await fetch(`${SERVER}/scrape/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!r.ok) throw new Error(await r.text());
        const { job_id } = await r.json();
        localStorage.setItem(JOB_KEY, job_id);
        openStream(job_id);
    } catch (err) {
        log(`Failed to start: ${err}`, "err");
        startBtn.disabled = false;
        startBtn.textContent = "Start Scraping";
    }
}

function openStream(jobId: string) {
    if (currentEs) currentEs.close();
    const es = new EventSource(`${SERVER}/scrape/stream/${jobId}`);
    currentEs = es;
    es.onmessage = handleEvent;
    es.onerror = () => {
        log("SSE connection lost — will retry in 5s", "warn");
    };
}

async function tryReconnect() {
    const jobId = localStorage.getItem(JOB_KEY);
    if (!jobId) return;
    try {
        const r = await fetch(`${SERVER}/scrape/jobs`);
        const jobs = await r.json();
        const job = jobs[jobId];
        if (!job) { localStorage.removeItem(JOB_KEY); return; }
        if (job.status === "running") {
            log(`Reconnecting to job ${jobId}…`, "warn");
            livePanel.classList.add("visible");
            startBtn.disabled = true;
            startBtn.textContent = "Scraping…";
            openStream(jobId);
        } else {
            localStorage.removeItem(JOB_KEY);
        }
    } catch {
        localStorage.removeItem(JOB_KEY);
    }
}

// ---------------------------------------------------------------------------
// Wire up
// ---------------------------------------------------------------------------
startBtn.addEventListener("click", startScraping);
init();
