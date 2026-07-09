const DEFAULT_SOURCE = "../.cache/scraper-tests/sber.json";

const state = {
  vacancies: [],
  filtered: [],
  selectedId: null,
  sourceName: "",
};

const els = {
  sourceLabel: document.querySelector("#sourceLabel"),
  loadDefaultBtn: document.querySelector("#loadDefaultBtn"),
  fileInput: document.querySelector("#fileInput"),
  searchInput: document.querySelector("#searchInput"),
  companySelect: document.querySelector("#companySelect"),
  locationSelect: document.querySelector("#locationSelect"),
  sortSelect: document.querySelector("#sortSelect"),
  visibleCount: document.querySelector("#visibleCount"),
  totalCount: document.querySelector("#totalCount"),
  vacancyList: document.querySelector("#vacancyList"),
  detail: document.querySelector("#detail"),
};

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const normalize = (value) => String(value ?? "").toLowerCase();

function toVacancyArray(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.vacancies)) return payload.vacancies;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}

function dateRank(value) {
  const raw = String(value ?? "");
  const parsed = Date.parse(raw);
  if (!Number.isNaN(parsed)) return parsed;
  const match = raw.match(/(\d{1,2})\s+([а-яё]+)/i);
  if (!match) return 0;
  const months = {
    января: 0,
    февраля: 1,
    марта: 2,
    апреля: 3,
    мая: 4,
    июня: 5,
    июля: 6,
    августа: 7,
    сентября: 8,
    октября: 9,
    ноября: 10,
    декабря: 11,
  };
  const month = months[match[2].toLowerCase()];
  if (month === undefined) return 0;
  return new Date(new Date().getFullYear(), month, Number(match[1])).getTime();
}

function locationText(vacancy) {
  const locations = vacancy.locations;
  if (Array.isArray(locations)) return locations.filter(Boolean).join(", ");
  return String(locations ?? "");
}

function setVacancies(vacancies, sourceName) {
  state.vacancies = vacancies.filter((item) => item && typeof item === "object");
  state.selectedId = state.vacancies[0]?.id ?? null;
  state.sourceName = sourceName;
  els.sourceLabel.textContent = `${sourceName} · ${state.vacancies.length} vacancies`;
  populateFilters();
  applyFilters();
}

function populateFilters() {
  const companies = [...new Set(state.vacancies.map((v) => v.company).filter(Boolean))].sort();
  const locations = [...new Set(state.vacancies.flatMap((v) => {
    if (Array.isArray(v.locations)) return v.locations;
    return v.locations ? [v.locations] : [];
  }).filter(Boolean))].sort();

  els.companySelect.innerHTML = `<option value="">All companies</option>${companies
    .map((company) => `<option value="${escapeHtml(company)}">${escapeHtml(company)}</option>`)
    .join("")}`;
  els.locationSelect.innerHTML = `<option value="">All locations</option>${locations
    .map((location) => `<option value="${escapeHtml(location)}">${escapeHtml(location)}</option>`)
    .join("")}`;
}

function applyFilters() {
  const q = normalize(els.searchInput.value).trim();
  const company = els.companySelect.value;
  const location = els.locationSelect.value;
  const sort = els.sortSelect.value;

  state.filtered = state.vacancies.filter((vacancy) => {
    const haystack = normalize([
      vacancy.title,
      vacancy.company,
      vacancy.pub_date,
      locationText(vacancy),
      vacancy.description,
      vacancy.origin_query,
    ].join(" "));
    if (q && !haystack.includes(q)) return false;
    if (company && vacancy.company !== company) return false;
    if (location && !locationText(vacancy).includes(location)) return false;
    return true;
  });

  state.filtered.sort((a, b) => {
    if (sort === "title_asc") return String(a.title ?? "").localeCompare(String(b.title ?? ""));
    if (sort === "company_asc") return String(a.company ?? "").localeCompare(String(b.company ?? ""));
    return dateRank(b.pub_date) - dateRank(a.pub_date);
  });

  if (!state.filtered.some((v) => v.id === state.selectedId)) {
    state.selectedId = state.filtered[0]?.id ?? null;
  }
  renderList();
  renderDetail();
}

function highlight(text) {
  const q = els.searchInput.value.trim();
  const escaped = escapeHtml(text);
  if (!q) return escaped;
  const safeQ = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return escaped.replace(new RegExp(`(${safeQ})`, "ig"), "<mark>$1</mark>");
}

function renderList() {
  els.visibleCount.textContent = state.filtered.length;
  els.totalCount.textContent = state.vacancies.length;
  els.vacancyList.innerHTML = state.filtered.map((vacancy) => {
    const active = vacancy.id === state.selectedId ? " active" : "";
    const loc = locationText(vacancy);
    return `
      <li>
        <button class="vacancyItem${active}" type="button" data-id="${escapeHtml(vacancy.id)}">
          <h3>${highlight(vacancy.title || "Untitled")}</h3>
          <div class="metaLine">
            <span class="tag">${escapeHtml(vacancy.company || "Unknown")}</span>
            ${vacancy.pub_date ? `<span class="tag">${escapeHtml(vacancy.pub_date)}</span>` : ""}
            ${loc ? `<span class="tag">${escapeHtml(loc)}</span>` : ""}
          </div>
        </button>
      </li>`;
  }).join("");
}

function renderDetail() {
  const vacancy = state.filtered.find((item) => item.id === state.selectedId);
  if (!vacancy) {
    els.detail.innerHTML = `
      <div class="emptyState">
        <h2>No vacancy selected</h2>
        <p>Adjust filters or open another JSON file.</p>
      </div>`;
    return;
  }

  const loc = locationText(vacancy);
  els.detail.innerHTML = `
    <article class="detailCard">
      <header class="detailHead">
        <h2>${highlight(vacancy.title || "Untitled")}</h2>
        <div class="metaLine">
          <span class="tag">${escapeHtml(vacancy.company || "Unknown")}</span>
          ${vacancy.pub_date ? `<span class="tag">${escapeHtml(vacancy.pub_date)}</span>` : ""}
          ${loc ? `<span class="tag">${escapeHtml(loc)}</span>` : ""}
          ${vacancy.origin_query ? `<span class="tag">query: ${escapeHtml(vacancy.origin_query)}</span>` : ""}
          ${vacancy.id ? `<span class="tag">${escapeHtml(vacancy.id)}</span>` : ""}
        </div>
        <div class="detailActions">
          ${vacancy.link ? `<a href="${escapeHtml(vacancy.link)}" target="_blank" rel="noreferrer">Open source</a>` : ""}
        </div>
      </header>
      <section class="description">${highlight(vacancy.description || "No description")}</section>
    </article>`;
}

async function loadUrl(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const payload = await response.json();
  setVacancies(toVacancyArray(payload), url);
}

async function loadFile(file) {
  const text = await file.text();
  const payload = JSON.parse(text);
  setVacancies(toVacancyArray(payload), file.name);
}

els.loadDefaultBtn.addEventListener("click", async () => {
  try {
    await loadUrl(DEFAULT_SOURCE);
  } catch (error) {
    els.sourceLabel.textContent = `Cannot load ${DEFAULT_SOURCE}: ${error.message}`;
  }
});

els.fileInput.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    await loadFile(file);
  } catch (error) {
    els.sourceLabel.textContent = `Cannot parse ${file.name}: ${error.message}`;
  }
});

els.vacancyList.addEventListener("click", (event) => {
  const button = event.target.closest(".vacancyItem");
  if (!button) return;
  state.selectedId = button.dataset.id;
  renderList();
  renderDetail();
});

els.searchInput.addEventListener("input", applyFilters);
els.companySelect.addEventListener("change", applyFilters);
els.locationSelect.addEventListener("change", applyFilters);
els.sortSelect.addEventListener("change", applyFilters);

loadUrl(DEFAULT_SOURCE).catch(() => {
  els.sourceLabel.textContent = `Start local server to load ${DEFAULT_SOURCE}, or open JSON manually`;
});
