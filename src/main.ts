import './style.css';
import { getLang, setLang, loadContent, type Lang, type CVContent } from './i18n';
import { exportPDF, exportDOC, exportMarkdown, copyAsText } from './export';

type SkillsView = 'cards' | 'hex' | 'orbit';
const SKILLS_VIEW_KEY = 'cv-skills-view';
const PROFILE_VIEW_KEY = 'cv-profile-view';
const SHORT_VIEW_KEY = 'cv-short-view';
const COLLAPSE_VIEW_KEY = 'cv-collapse-view';

type ViewMode = 'technical' | 'product';

function getSkillsView(): SkillsView {
  const v = localStorage.getItem(SKILLS_VIEW_KEY);
  if (v === 'cards' || v === 'hex' || v === 'orbit') return v;
  return 'cards';
}

function getViewMode(): ViewMode {
  const v = localStorage.getItem(PROFILE_VIEW_KEY);
  if (v === 'technical' || v === 'product') return v;
  return 'technical';
}

function getShortView(): boolean {
  return localStorage.getItem(SHORT_VIEW_KEY) === 'true';
}

function getCollapseView(): boolean {
  return localStorage.getItem(COLLAPSE_VIEW_KEY) === 'true';
}

let currentLang: Lang = getLang();
let currentViewMode: ViewMode = getViewMode();

function renderSkillsSummary(cv: CVContent, lang: Lang): string {
  return `
    <div class="skills-summary print-only">
      ${cv.techStack.categories.map(cat => `
        <div class="skills-summary-row">
          <strong>${cat.label[lang]}:</strong> ${cat.items.map(i => i.name).join(', ')}
        </div>
      `).join('')}
    </div>
  `;
}

function renderCardsView(cv: CVContent, lang: Lang): string {
  return cv.techStack.categories.map((cat) => `
    <div class="stack-category">
      <h3>${cat.label[lang]}</h3>
      <div class="stack-tags">
        ${cat.items.map((item) => {
    const iconSrc = item.icon
      ? `https://cdn.simpleicons.org/${item.icon}/${item.color.slice(1)}`
      : '';
    const iconEl = item.icon
      ? `<img src="${iconSrc}" alt="" width="16" height="16" loading="lazy" />`
      : '';
    return `<a class="stack-tag" href="${item.url}" target="_blank" rel="noopener" style="--color: ${item.color}">${iconEl}${item.name}</a>`;
  }).join('')}
      </div>
    </div>
  `).join('');
}

function renderHexView(cv: CVContent, lang: Lang): string {
  return cv.techStack.categories.map((cat) => `
    <div class="hex-category">
      <h3>${cat.label[lang]}</h3>
      <div class="hex-grid">
        ${cat.items.map((item) => {
    const iconSrc = item.icon
      ? `https://cdn.simpleicons.org/${item.icon}/white`
      : '';
    const iconEl = item.icon
      ? `<img src="${iconSrc}" alt="${item.name}" width="22" height="22" loading="lazy" />`
      : `<span class="hex-letter">${item.name.charAt(0)}</span>`;
    return `
            <a class="hex-cell" href="${item.url}" target="_blank" rel="noopener" style="--color: ${item.color}">
              <div class="hex-inner">
                ${iconEl}
                <span class="hex-name">${item.name}</span>
              </div>
            </a>`;
  }).join('')}
      </div>
    </div>
  `).join('');
}

function renderOrbitView(cv: CVContent, lang: Lang): string {
  const categories = cv.techStack.categories;
  return `
    <div class="orbit-view-controls no-print">
      ${categories.map(cat => `
        <button class="orbit-filter-btn active" data-ring="${cat.ring}" style="--color: ${cat.items[0]?.color || 'var(--color-accent)'}">
          ${cat.label[lang]}
        </button>
      `).join('')}
    </div>
    <div class="orbit-container">
      <div class="orbit-center">AI / ML</div>
      ${categories.map((cat) => `
        <div class="orbit-ring ring-${cat.ring}" style="--item-count: ${cat.items.length}">
          <span class="ring-label">${cat.label[lang]}</span>
          ${cat.items.map((item, i) => {
    const angle = (360 / cat.items.length) * i;
    const iconSrc = item.icon
      ? `https://cdn.simpleicons.org/${item.icon}/white`
      : '';
    const fallback = !item.icon
      ? `<span class="orbit-fallback" style="background: ${item.color}">${item.name.charAt(0)}</span>`
      : `<img src="${iconSrc}" alt="${item.name}" width="24" height="24" loading="lazy" />`;
    return `
              <a class="orbit-item"
                 href="${item.url}" target="_blank" rel="noopener"
                 style="--angle: ${angle}deg; --color: ${item.color}"
                 title="${item.name}">
                <span class="orbit-icon">${fallback}</span>
                <span class="orbit-tooltip">${item.name}</span>
              </a>
            `;
  }).join('')}
        </div>
      `).join('')}
    </div>
  `;
}

function renderSocialBar(lang: Lang, cv: CVContent): string {
  const messengerBtn = lang === 'ru'
    ? `<a class="social-link social-link--telegram" href="https://vsvladis.t.me/" target="_blank" rel="noopener" aria-label="Telegram">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
      </a>`
    : `<a class="social-link social-link--whatsapp" href="https://wa.me/79963288498" target="_blank" rel="noopener" aria-label="WhatsApp">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/></svg>
      </a>`

  const calendlyBtn = cv.contact.calendly
    ? `<a class="social-link social-link--calendly" href="${cv.contact.calendly}" target="_blank" rel="noopener" aria-label="Calendly" title="${cv.labels.scheduleCall}">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM9 14H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2zm-8 4H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2z"/></svg>
      </a>`
    : '';

  return `
    <div class="header-social-row">
      <div class="header-social">
        <a class="social-link social-link--github" href="https://github.com/vladislav-vasilenko" target="_blank" rel="noopener" aria-label="GitHub">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
        </a>
        <a class="social-link social-link--linkedin" href="https://linkedin.com/in/tech" target="_blank" rel="noopener" aria-label="LinkedIn">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
        </a>
        ${messengerBtn}
        ${calendlyBtn}
        <button class="social-link social-link--email" aria-label="Email" title="${lang === 'ru' ? 'Нажмите, чтобы скопировать email' : 'Click to copy email'}">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M1.5 8.67v8.58a3 3 0 0 0 3 3h15a3 3 0 0 0 3-3V8.67l-8.928 5.493a3 3 0 0 1-3.144 0L1.5 8.67Z"/><path d="M22.5 6.908V6.75a3 3 0 0 0-3-3h-15a3 3 0 0 0-3 3v.158l9.714 5.978a1.5 1.5 0 0 0 1.572 0L22.5 6.908Z"/></svg>
        </button>
        <span class="print-only-email">${cv.contact.email}</span>
      </div>
      <div class="header-languages">
        ${cv.languages.map(l => `<span class="lang-tag">${l}</span>`).join('')}
      </div>
    </div>
  `;
}

function renderPage(lang: Lang): void {
  const cv = loadContent(lang);
  const app = document.querySelector<HTMLDivElement>('#app')!;
  const skillsView = getSkillsView();
  const isShortView = getShortView();
  const isCollapsed = getCollapseView();

  app.innerHTML = `
    <div class="cv">
      <header class="cv-header">
        <div class="header-controls">
          <div class="profile-toggle no-print">
            <button class="profile-btn ${currentViewMode === 'technical' ? 'active' : ''}" data-view="technical">
              <span>⚙️</span> ${cv.labels.profileTechnical}
            </button>
            <button class="profile-btn ${currentViewMode === 'product' ? 'active' : ''}" data-view="product">
              <span>💼</span> ${cv.labels.profileProduct}
            </button>
          </div>
          <div class="export-dropdown">
            <button class="export-btn" aria-label="${cv.labels.export}">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 1v9M4.5 6.5 8 10l3.5-3.5M2 12v2h12v-2"/>
              </svg>
              ${cv.labels.export}
            </button>
            <div class="export-menu">
              <button class="export-option" data-action="copy">${cv.labels.copyText}</button>
              <button class="export-option" data-action="pdf">${cv.labels.exportPdf}</button>
              <button class="export-option" data-action="doc">${cv.labels.exportDoc}</button>
              <button class="export-option" data-action="md">${cv.labels.exportMd}</button>
            </div>
          </div>
          <div class="lang-toggle">
            <button class="lang-btn ${lang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
            <button class="lang-btn ${lang === 'ru' ? 'active' : ''}" data-lang="ru">RU</button>
          </div>
        </div>
        <div class="cv-header-main">
          <img src="/profile.jpg" alt="${cv.name}" class="cv-profile-image" />
          <div class="cv-header-content">
            <h1>${cv.name}</h1>
            <p class="cv-title">${currentViewMode === 'product' ? cv.productTitle : cv.title}</p>
            ${renderSocialBar(lang, cv)}
            <div class="mobile-email-row print-only">
               <span class="email-label">${lang === 'ru' ? 'Email:' : 'Email:'}</span>
               <span class="email-value">${cv.contact.email}</span>
            </div>
          </div>
        </div>
        <div class="cv-contact">
          ${cv.contact.location ? `<span>${cv.contact.location}</span>` : ''}
          <span class="print-only"><a href="tel:${cv.contact.phone.replace(/[\s()-]/g, '')}">${cv.contact.phone}</a></span>
          <span class="print-only">${cv.contact.email}</span>
          ${cv.contact.citizenship ? `<span>${cv.contact.citizenship}</span>` : ''}
          ${cv.contact.relocation ? `<span>${cv.contact.relocation}</span>` : ''}
        </div>
        ${renderSkillsSummary(cv, lang)}
      </header>

      <section class="cv-section">
        <h2>${cv.labels.about}</h2>
        <div class="about-text">${currentViewMode === 'product' ? cv.productAboutHtml : cv.aboutHtml}</div>
      </section>

      <section class="cv-section">
        <h2>${cv.labels.employment}</h2>
        <p>${cv.employment}</p>
      </section>

      <section class="cv-section">
        <div class="section-header-row">
            <h2>${cv.labels.experience}</h2>
            <div class="view-toggle no-print">
                <button class="exp-toggle-btn ${isShortView ? 'active' : ''}" data-view="short" title="${cv.labels.profileShort}">
                    <span>📄</span>
                </button>
                <button class="exp-toggle-btn ${isCollapsed ? 'active' : ''}" data-view="collapse" title="${cv.labels.profileCollapse}">
                    <span>↔️</span>
                </button>
            </div>
        </div>
        <div id="history" class="history">
          ${cv.experience
      .filter(exp => exp.profiles.includes(currentViewMode))
      .map(
        (exp) => `
            <div class="entry row timeline-item">
              <div class="timespan">
                ${exp.period}
              </div>
              <div class="ico">
                <div class="entry-dot"></div>
                ${exp.logo ? `<img src="${exp.logo}" alt="${exp.company}" ${exp.logoWidth ? `style="max-width: ${exp.logoWidth}"` : ''} loading="lazy">` : ''}
              </div>
              <div class="desc">
                <div class="timeline-header-karpathy">
                    <h3>${exp.role}</h3>
                    <p class="company">${exp.url
            ? `<a href="${exp.url}" target="_blank" rel="noopener">${exp.company}</a>`
            : exp.company
          }${exp.location ? ` — ${exp.location}` : ''}${exp.industry ? ` <span class="industry">(${exp.industry})</span>` : ''
          }</p>
                </div>
                <div class="exp-description ${isCollapsed ? 'collapsed' : ''}">${isShortView ? exp.shortDescriptionHtml : exp.descriptionHtml}</div>
              </div>
            </div>
          `
      )
      .join('')}
        </div>
      </section>

      <section class="cv-section">
        <h2>${cv.labels.education}</h2>
        <div class="education-list">
          ${cv.education
      .map(
        (edu) => `
            <div class="education-item">
              <span class="edu-year">${edu.year}</span>
              <div>
                <strong>${edu.institution}</strong>
                <p>${edu.program}</p>
              </div>
            </div>
          `
      )
      .join('')}
        </div>
      </section>

      <section class="cv-section cv-section--stack stack-view--${skillsView} no-print">
        <div class="section-header-row">
          <h2>${cv.labels.skills}</h2>
          <div class="view-toggle">
            <button class="view-toggle-btn">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="8" cy="8" r="6"/><path d="M8 5v6M5 8h6"/>
              </svg>
              <span class="view-toggle-label">${skillsView === 'cards' ? cv.labels.viewCards :
      skillsView === 'hex' ? cv.labels.viewHex :
        cv.labels.viewOrbit
    }</span>
            </button>
            <div class="view-menu">
              <button class="view-option ${skillsView === 'cards' ? 'active' : ''}" data-view="cards">${cv.labels.viewCards}</button>
              <button class="view-option ${skillsView === 'hex' ? 'active' : ''}" data-view="hex">${cv.labels.viewHex}</button>
              <button class="view-option ${skillsView === 'orbit' ? 'active' : ''}" data-view="orbit">${cv.labels.viewOrbit}</button>
            </div>
          </div>
        </div>
        <div class="stack-cards">${renderCardsView(cv, lang)}</div>
        <div class="stack-hex">${renderHexView(cv, lang)}</div>
        <div class="stack-orbit">${renderOrbitView(cv, lang)}</div>
      </section>

    </div>
  `;

  // Language toggle
  app.querySelectorAll<HTMLButtonElement>('.lang-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const newLang = btn.dataset.lang as Lang;
      currentLang = newLang;
      setLang(newLang);
      renderPage(newLang);
    });
  });

  // Experience toggle
  app.querySelectorAll<HTMLButtonElement>('.exp-toggle-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      if (view === 'short') {
        const isShort = getShortView();
        localStorage.setItem(SHORT_VIEW_KEY, String(!isShort));
        renderPage(currentLang);
      } else if (view === 'collapse') {
        const isCollapsed = getCollapseView();
        localStorage.setItem(COLLAPSE_VIEW_KEY, String(!isCollapsed));
        renderPage(currentLang);
      }
    });
  });

  // Profile toggle
  app.querySelectorAll<HTMLButtonElement>('.profile-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const newViewMode = btn.dataset.view;
      if (newViewMode && newViewMode !== currentViewMode) {
        currentViewMode = newViewMode as ViewMode;
        localStorage.setItem(PROFILE_VIEW_KEY, newViewMode);
        renderPage(currentLang);
      }
    });
  });

  // Export dropdown
  const exportBtn = app.querySelector<HTMLButtonElement>('.export-btn')!;
  const exportMenu = app.querySelector<HTMLDivElement>('.export-menu')!;

  exportBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    exportMenu.classList.toggle('open');
    viewMenu.classList.remove('open');
  });

  app.querySelectorAll<HTMLButtonElement>('.export-option').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const action = btn.dataset.action;
      exportMenu.classList.remove('open');

      const isShort = getShortView();
      const isCollapsed = getCollapseView();
      const filteredExperience = cv.experience
        .filter(exp => exp.profiles.includes(currentViewMode))
        .map(exp => ({
          ...exp,
          descriptionHtml: isCollapsed ? '' : (isShort ? exp.shortDescriptionHtml : exp.descriptionHtml),
          shortDescriptionHtml: isCollapsed ? '' : (isShort ? exp.shortDescriptionHtml : exp.descriptionHtml),
          descriptionMd: isCollapsed ? '' : (isShort ? exp.shortDescriptionMd : exp.descriptionMd),
          shortDescriptionMd: isCollapsed ? '' : (isShort ? exp.shortDescriptionMd : exp.descriptionMd)
        }));

      const filteredCv = {
        ...cv,
        experience: filteredExperience,
        aboutHtml: currentViewMode === 'product' ? cv.productAboutHtml : cv.aboutHtml,
        aboutMd: currentViewMode === 'product' ? cv.productAboutMd : cv.aboutMd
      };

      switch (action) {
        case 'copy':
          await copyAsText(filteredCv);
          showToast(cv.labels.copied);
          break;
        case 'pdf':
          exportPDF();
          break;
        case 'doc':
          exportDOC(filteredCv);
          break;
        case 'md':
          exportMarkdown(filteredCv);
          break;
      }
    });
  });

  // Skills view toggle
  const viewToggleBtn = app.querySelector<HTMLButtonElement>('.view-toggle-btn')!;
  const viewMenu = app.querySelector<HTMLDivElement>('.view-menu')!;

  viewToggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    viewMenu.classList.toggle('open');
    exportMenu.classList.remove('open');
  });

  app.querySelectorAll<HTMLButtonElement>('.view-option').forEach((btn) => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view as SkillsView;
      localStorage.setItem(SKILLS_VIEW_KEY, view);
      viewMenu.classList.remove('open');
      const section = app.querySelector('.cv-section--stack')!;
      section.className = `cv-section cv-section--stack stack-view--${view}`;
      app.querySelector('.view-toggle-label')!.textContent =
        view === 'cards' ? cv.labels.viewCards :
          view === 'hex' ? cv.labels.viewHex :
            cv.labels.viewOrbit;
      app.querySelectorAll('.view-option').forEach((o) => o.classList.remove('active'));
      btn.classList.add('active');

      // Re-bind orbit filters if switching to orbit view
      if (view === 'orbit') {
        bindOrbitFilters();
      }
    });
  });

  function bindOrbitFilters() {
    app.querySelectorAll<HTMLButtonElement>('.orbit-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const ring = btn.dataset.ring;
        const ringEl = app.querySelector(`.orbit-ring.ring-${ring}`);
        if (ringEl) {
          const isActive = btn.classList.toggle('active');
          ringEl.classList.toggle('hidden', !isActive);
        }
      });
    });
  }

  if (skillsView === 'orbit') {
    bindOrbitFilters();
  }

  // Close all dropdowns on outside click
  document.addEventListener('click', () => {
    exportMenu.classList.remove('open');
    viewMenu.classList.remove('open');
  });

  exportMenu.addEventListener('click', (e) => e.stopPropagation());
  viewMenu.addEventListener('click', (e) => e.stopPropagation());

  // Email copy button
  const emailBtn = document.querySelector<HTMLButtonElement>('.social-link--email');
  if (emailBtn) {
    let timeout: number | null = null;
    emailBtn.addEventListener('click', async () => {
      const email = cv.contact.email;

      if (emailBtn.classList.contains('revealed')) {
        window.location.href = `mailto:${email}`;
        return;
      }

      await navigator.clipboard.writeText(email);
      emailBtn.classList.add('revealed');
      emailBtn.innerHTML = `<span class="email-text">${email}</span>`;
      showLocalToast(cv.labels.copied, emailBtn);

      if (timeout) clearTimeout(timeout);
      timeout = window.setTimeout(() => {
        emailBtn.classList.remove('revealed');
        emailBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M1.5 8.67v8.58a3 3 0 0 0 3 3h15a3 3 0 0 0 3-3V8.67l-8.928 5.493a3 3 0 0 1-3.144 0L1.5 8.67Z"/><path d="M22.5 6.908V6.75a3 3 0 0 0-3-3h-15a3 3 0 0 0-3 3v.158l9.714 5.978a1.5 1.5 0 0 0 1.572 0L22.5 6.908Z"/></svg>`;
        timeout = null;
      }, 5000);
    });
  }
}

function showLocalToast(message: string, target: HTMLElement): void {
  const existing = document.querySelector('.toast--local');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast toast--local';
  toast.textContent = message;
  document.body.appendChild(toast);

  const rect = target.getBoundingClientRect();
  toast.style.top = `${rect.bottom + 10}px`;
  toast.style.left = `${rect.left + rect.width / 2}px`;

  requestAnimationFrame(() => {
    toast.classList.add('toast--visible');
  });

  setTimeout(() => {
    toast.classList.remove('toast--visible');
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

function showToast(message: string): void {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('toast--visible');
  });

  setTimeout(() => {
    toast.classList.remove('toast--visible');
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

const initialLang = getLang();
setLang(initialLang);
renderPage(initialLang);
