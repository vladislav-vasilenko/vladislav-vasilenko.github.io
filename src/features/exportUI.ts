import { type CVContent, getLang } from '../i18n';
import { type ViewMode, getShortView, getCollapseView, getTechProfile } from '../state';
import { copyAsText, exportPDF, exportDOC, exportMarkdown } from '../export';
import { showToast } from './toast';

function buildShareUrl(viewMode: ViewMode): string {
    const url = new URL(window.location.origin + window.location.pathname);
    url.searchParams.set('lang', getLang());
    url.searchParams.set('view', viewMode);
    if (viewMode === 'technical') {
        url.searchParams.set('tech', getTechProfile());
    }
    return url.toString();
}

export function initializeExport(app: HTMLElement, cv: CVContent, currentViewMode: ViewMode) {
    const exportBtn = app.querySelector<HTMLButtonElement>('.export-btn');
    const exportMenu = app.querySelector<HTMLDivElement>('.export-menu');

    if (!exportBtn || !exportMenu) return;

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
