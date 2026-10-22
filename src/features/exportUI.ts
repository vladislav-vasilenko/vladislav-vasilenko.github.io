import { type CVContent, getLang } from '../i18n';
import { type ViewMode, getShortView, getCollapseView, getTechProfile } from '../state';
import { copyAsText, exportPDF, exportDOC, exportMarkdown } from '../export';
import { showToast } from './toast';
import workspace from '../../workspace.projects.json';

function buildShareUrl(viewMode: ViewMode): string {
    const url = new URL(window.location.origin + window.location.pathname);
    url.searchParams.set('lang', getLang());
    url.searchParams.set('view', viewMode);
    url.searchParams.set('layout', 'full');
    if (viewMode === 'technical') {
        url.searchParams.set('tech', getTechProfile());
    }
    return url.toString();
}

export function initializeExport(app: HTMLElement, cv: CVContent, currentViewMode: ViewMode) {
    const exportBtn = app.querySelector<HTMLButtonElement>('.export-btn');
    const exportMenu = app.querySelector<HTMLDivElement>('.export-menu');

    if (!exportBtn || !exportMenu) return;

    if (import.meta.env.DEV) {
        const career = document.createElement('button');
        career.className = 'export-option';
        career.dataset.action = 'career';
        career.textContent = getLang() === 'ru' ? 'В подготовку откликов · Markdown' : 'To Career Workspace · Markdown';
        career.title = 'Скачать текущую версию CV и открыть импорт в локальном сервисе. Файл нужно выбрать в разделе Резюме.';
        exportMenu.append(career);
    }

    exportBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportMenu.classList.toggle('open');
        const viewMenu = app.querySelector('.view-menu');
        if (viewMenu) viewMenu.classList.remove('open');
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
                case 'career': {
                    const target = new URL(workspace.projects.career.local_url);
                    target.searchParams.set('view', 'resume');
                    window.open(target.href, '_blank', 'noopener,noreferrer');
                    exportMarkdown(filteredCv);
                    showToast(getLang() === 'ru' ? 'CV скачано. В локальном сервисе откройте Резюме и импортируйте Markdown-файл.' : 'CV downloaded. Import the Markdown file in Career Workspace → Resumes.');
                    break;
                }
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
                case 'share':
                    try {
                        await navigator.clipboard.writeText(buildShareUrl(currentViewMode));
                        showToast(cv.labels.linkCopied);
                    } catch {
                        showToast(cv.labels.linkCopied);
                    }
                    break;
            }
        });
    });
}
