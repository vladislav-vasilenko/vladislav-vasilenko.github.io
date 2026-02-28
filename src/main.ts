import './style.css';
import { getLang, setLang, loadContent, type Lang } from './i18n';

function renderPage(lang: Lang): void {
  const cv = loadContent(lang);
  const app = document.querySelector<HTMLDivElement>('#app')!;

  app.innerHTML = `
    <div class="cv">
      <header class="cv-header">
        <div class="lang-toggle">
          <button class="lang-btn ${lang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
          <button class="lang-btn ${lang === 'ru' ? 'active' : ''}" data-lang="ru">RU</button>
        </div>
        <h1>${cv.name}</h1>
        <p class="cv-title">${cv.title}</p>
        <div class="cv-contact">
          <span>${cv.contact.location}</span>
          <span><a href="mailto:${cv.contact.email}">${cv.contact.email}</a></span>
          <span><a href="tel:${cv.contact.phone.replace(/[\s()-]/g, '')}">${cv.contact.phone}</a></span>
          <span>${cv.contact.relocation}</span>
        </div>
      </header>

      <section class="cv-section">
        <h2>${cv.labels.about}</h2>
        <div class="about-text">${cv.aboutHtml}</div>
      </section>

      <section class="cv-section">
        <h2>${cv.labels.employment}</h2>
        <p>${cv.employment}</p>
      </section>

      <section class="cv-section">
        <h2>${cv.labels.experience}</h2>
        <div class="timeline">
          ${cv.experience
            .map(
              (exp) => `
            <div class="timeline-item">
              <div class="timeline-header">
                <div class="timeline-left">
                  <h3>${exp.role}</h3>
                  <p class="company">${
                    exp.url
                      ? `<a href="${exp.url}" target="_blank" rel="noopener">${exp.company}</a>`
                      : exp.company
                  }${exp.location ? ` — ${exp.location}` : ''}${
                    exp.industry ? ` <span class="industry">(${exp.industry})</span>` : ''
                  }</p>
                </div>
                <div class="timeline-right">
                  <span class="period">${exp.period}</span>
                  <span class="duration">${exp.duration}</span>
                </div>
              </div>
              <div class="exp-description">${exp.descriptionHtml}</div>
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

      <section class="cv-section cv-section--stack">
        <h2>${cv.labels.skills}</h2>
        <div class="orbit-container">
          <div class="orbit-center">AI / ML</div>
          ${cv.techStack.categories.map((cat) => `
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
        <!-- Mobile fallback -->
        <div class="stack-mobile">
          ${cv.techStack.categories.map((cat) => `
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
          `).join('')}
        </div>
      </section>

      <section class="cv-section">
        <h2>${cv.labels.languages}</h2>
        <ul class="languages">
          ${cv.languages.map((l) => `<li>${l}</li>`).join('')}
        </ul>
      </section>
    </div>
  `;

  app.querySelectorAll<HTMLButtonElement>('.lang-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const newLang = btn.dataset.lang as Lang;
      setLang(newLang);
      renderPage(newLang);
    });
  });
}

const initialLang = getLang();
setLang(initialLang);
renderPage(initialLang);
