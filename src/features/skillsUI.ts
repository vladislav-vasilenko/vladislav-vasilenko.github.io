import { type CVContent } from '../i18n';
import { type SkillsView, setSkillsView } from '../state';

export function initializeSkills(app: HTMLElement, cv: CVContent) {
    const viewToggleBtn = app.querySelector<HTMLButtonElement>('.view-toggle-btn');
    const viewMenu = app.querySelector<HTMLDivElement>('.view-menu');

    if (!viewToggleBtn || !viewMenu) return { bindOrbitFilters };

    viewToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        viewMenu.classList.toggle('open');
        const exportMenu = app.querySelector('.export-menu');
        if (exportMenu) exportMenu.classList.remove('open');
    });

    app.querySelectorAll<HTMLButtonElement>('.view-option').forEach((btn) => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view as SkillsView;
            setSkillsView(view);
            viewMenu.classList.remove('open');
            const section = app.querySelector('.cv-section--stack')!;
            section.className = `cv-section cv-section--stack stack-view--${view}`;
            app.querySelector('.view-toggle-label')!.textContent =
                view === 'cards' ? cv.labels.viewCards :
                    view === 'hex' ? cv.labels.viewHex :
                        cv.labels.viewOrbit;
            app.querySelectorAll('.view-option').forEach((o) => o.classList.remove('active'));
            btn.classList.add('active');

            if (view === 'orbit') {
                bindOrbitFilters(app);
            }
        });
    });

    // Export for initial load
    return { bindOrbitFilters };
}

export function bindOrbitFilters(app: HTMLElement) {
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
