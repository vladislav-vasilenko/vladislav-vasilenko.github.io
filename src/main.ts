import './style.css';
import { getLang, setLang, loadContent, type Lang } from './i18n';
import {
  getViewMode, getSkillsView, getShortView, getCollapseView, getTechProfile,
  setViewMode, toggleShortView, toggleCollapseView, setTechProfile, type ViewMode, type TechProfileMode
} from './state';
import { renderFullPage } from './render';
import { showLocalToast } from './features/toast';
import { initializeCompliance } from './features/compliance';
import { initializeCoverLetter } from './features/coverletter';
import { initializeHowToApply } from './features/howToApply';
import { initializeExport } from './features/exportUI';
import { initializeSkills } from './features/skillsUI';

let currentLang: Lang = getLang();
let currentViewMode: ViewMode = getViewMode();
let currentTechProfile: TechProfileMode = getTechProfile();

function renderPage(lang: Lang): void {
  const cv = loadContent(lang, currentTechProfile);
  const app = document.querySelector<HTMLDivElement>('#app')!;
  const skillsView = getSkillsView();
  const isShortView = getShortView();
  const isCollapsed = getCollapseView();

  app.innerHTML = renderFullPage(cv, lang, currentViewMode, skillsView, isShortView, isCollapsed, currentTechProfile);

  // --- Feature Initializations ---
  initializeCompliance(app, lang);
  initializeCoverLetter(app, lang);
  initializeHowToApply(app, lang, cv.experience);
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

  // Tech profile toggle (Audio, Vision, etc.)
  app.querySelectorAll<HTMLButtonElement>('.tech-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const newTechProfile = btn.dataset.tech as TechProfileMode;
      if (newTechProfile && newTechProfile !== currentTechProfile) {
        currentTechProfile = newTechProfile;
        setTechProfile(newTechProfile);
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
}

// Global dropdown closer (Outside renderPage to avoid duplicates)
document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement;
  if (!target.closest('.view-toggle') && !target.closest('.export-dropdown')) {
    document.querySelector('.export-menu')?.classList.remove('open');
    document.querySelector('.view-menu')?.classList.remove('open');
  }
});

// Apply URL query params (share links) — overrides localStorage on load
function applyUrlParams(): void {
  const params = new URLSearchParams(window.location.search);
  const urlLang = params.get('lang');
  const urlView = params.get('view');
  const urlTech = params.get('tech');

  if (urlLang === 'en' || urlLang === 'ru') {
    currentLang = urlLang;
    setLang(urlLang);
  }
  if (urlView === 'technical' || urlView === 'product') {
    currentViewMode = urlView;
    setViewMode(urlView);
  }
  const validTech: TechProfileMode[] = ['audio', 'vision', 'multimodal', 'multiagent', 'ios', 'llm'];
  if (urlTech && (validTech as string[]).includes(urlTech)) {
    currentTechProfile = urlTech as TechProfileMode;
    setTechProfile(urlTech as TechProfileMode);
  }
}

// Initial Render
applyUrlParams();
const initialLang = getLang();
setLang(initialLang);
renderPage(initialLang);
