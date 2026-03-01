import './style.css';
import { getLang, setLang, loadContent, type Lang } from './i18n';
import {
  getViewMode, getSkillsView, getShortView, getCollapseView,
  setViewMode, toggleShortView, toggleCollapseView, type ViewMode
} from './state';
import { renderFullPage } from './render';
import { showLocalToast } from './features/toast';
import { initializeCompliance } from './features/compliance';
import { initializeExport } from './features/exportUI';
import { initializeSkills } from './features/skillsUI';

let currentLang: Lang = getLang();
let currentViewMode: ViewMode = getViewMode();

function renderPage(lang: Lang): void {
  const cv = loadContent(lang);
  const app = document.querySelector<HTMLDivElement>('#app')!;
  const skillsView = getSkillsView();
  const isShortView = getShortView();
  const isCollapsed = getCollapseView();

  app.innerHTML = renderFullPage(cv, lang, currentViewMode, skillsView, isShortView, isCollapsed);

  // --- Feature Initializations ---
  initializeCompliance(app, lang);
  initializeExport(app, cv, currentViewMode);
  const skillsResult = initializeSkills(app, cv);

  if (skillsView === 'orbit') {
    skillsResult.bindOrbitFilters(app);
  }

  // --- Core UI Events ---

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
        toggleShortView();
      } else if (view === 'collapse') {
        toggleCollapseView();
      }
      renderPage(currentLang);
    });
  });

  // Profile toggle
  app.querySelectorAll<HTMLButtonElement>('.profile-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const newViewMode = btn.dataset.view as ViewMode;
      if (newViewMode && newViewMode !== currentViewMode) {
        currentViewMode = newViewMode;
        setViewMode(newViewMode);
        renderPage(currentLang);
      }
    });
  });

  // Email copy button
  const emailBtn = app.querySelector<HTMLButtonElement>('.social-link--email');
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

      if (timeout) window.clearTimeout(timeout);
      timeout = window.setTimeout(() => {
        emailBtn.classList.remove('revealed');
        emailBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M1.5 8.67v8.58a3 3 0 0 0 3 3h15a3 3 0 0 0 3-3V8.67l-8.928 5.493a3 3 0 0 1-3.144 0L1.5 8.67Z"/><path d="M22.5 6.908V6.75a3 3 0 0 0-3-3h-15a3 3 0 0 0-3 3v.158l9.714 5.978a1.5 1.5 0 0 0 1.572 0L22.5 6.908Z"/></svg>`;
        timeout = null;
      }, 5000);
    });
  }

  // Global dropdown closer
  document.addEventListener('click', () => {
    app.querySelector('.export-menu')?.classList.remove('open');
    app.querySelector('.view-menu')?.classList.remove('open');
  });
}

// Initial Render
const initialLang = getLang();
setLang(initialLang);
renderPage(initialLang);
