export type SkillsView = 'cards' | 'hex' | 'orbit';
export type ViewMode = 'technical' | 'product';

export const SKILLS_VIEW_KEY = 'cv-skills-view';
export const PROFILE_VIEW_KEY = 'cv-profile-view';
export const SHORT_VIEW_KEY = 'cv-short-view';
export const COLLAPSE_VIEW_KEY = 'cv-collapse-view';

export function getSkillsView(): SkillsView {
    const v = localStorage.getItem(SKILLS_VIEW_KEY);
    if (v === 'cards' || v === 'hex' || v === 'orbit') return v;
    return 'cards';
}

export function getViewMode(): ViewMode {
    const v = localStorage.getItem(PROFILE_VIEW_KEY);
    if (v === 'technical' || v === 'product') return v;
    return 'technical';
}

export function getShortView(): boolean {
    return localStorage.getItem(SHORT_VIEW_KEY) === 'true';
}

export function getCollapseView(): boolean {
    return localStorage.getItem(COLLAPSE_VIEW_KEY) === 'true';
}

export function setSkillsView(v: SkillsView) {
    localStorage.setItem(SKILLS_VIEW_KEY, v);
}

export function setViewMode(v: ViewMode) {
    localStorage.setItem(PROFILE_VIEW_KEY, v);
}

export function toggleShortView(): boolean {
    const newVal = !getShortView();
    localStorage.setItem(SHORT_VIEW_KEY, String(newVal));
    return newVal;
}

export function toggleCollapseView(): boolean {
    const newVal = !getCollapseView();
    localStorage.setItem(COLLAPSE_VIEW_KEY, String(newVal));
    return newVal;
}
