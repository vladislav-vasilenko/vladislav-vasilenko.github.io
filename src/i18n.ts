import { marked } from 'marked';

export type Lang = 'en' | 'ru';

const STORAGE_KEY = 'cv-lang';

export function getLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'en' || stored === 'ru') return stored;
  return 'en';
}

export function setLang(lang: Lang): void {
  localStorage.setItem(STORAGE_KEY, lang);
  document.documentElement.lang = lang;
}

export interface Experience {
  id: string;
  period: string;
  duration: string;
  company: string;
  location: string;
  url?: string;
  industry?: string;
  role: string;
  profiles: string[];
  descriptionHtml: string;
  descriptionMd: string;
  shortDescriptionHtml: string;
  shortDescriptionMd: string;
  logo?: string;
  logoWidth?: string;
}

export interface Education {
  year: string;
  institution: string;
  program: string;
}

export interface TechItem {
  name: string;
  icon: string | null;
  url: string;
  color: string;
}

export interface TechCategory {
  id: string;
  label: Record<Lang, string>;
  ring: number;
  items: TechItem[];
}

export interface TechStack {
  categories: TechCategory[];
}

interface CVJson {
  name: string;
  title: string;
  productTitle: string;
  contact: {
    phone: string;
    email: string;
    location: string;
    citizenship: string;
    relocation: string;
    calendly?: string;
  };
  labels: {
    about: string;
    experience: string;
    education: string;
    skills: string;
    languages: string;
    employment: string;
    export: string;
    copyText: string;
    exportPdf: string;
    exportDoc: string;
    exportMd: string;
    copied: string;
    viewCards: string;
    viewHex: string;
    viewOrbit: string;
    profileTechnical: string;
    profileProduct: string;
    profileShort: string;
    profileCollapse: string;
    scheduleCall: string;
    checkCompliance: string;
  };
  employment: string;
  experience: (Omit<Experience, 'descriptionHtml' | 'descriptionMd'>)[];
  education: Education[];
  languages: string[];
}

export interface CVContent {
  name: string;
  title: string;
  productTitle: string;
  contact: CVJson['contact'];
  labels: CVJson['labels'];
  employment: string;
  experience: Experience[];
  education: Education[];
  languages: string[];
  aboutHtml: string;
  aboutMd: string;
  productAboutHtml: string;
  productAboutMd: string;
  techStack: TechStack;
}

const jsonModules = import.meta.glob<CVJson>('/content/*/cv.json', { eager: true, import: 'default' });
const aboutModules = import.meta.glob<string>('/content/*/about.md', { eager: true, query: '?raw', import: 'default' });
const productAboutModules = import.meta.glob<string>('/content/*/product-about.md', { eager: true, query: '?raw', import: 'default' });
const expModules = import.meta.glob<string>('/content/*/experience/*.md', { eager: true, query: '?raw', import: 'default' });
const techStackModules = import.meta.glob<TechStack>('/content/tech-stack.json', { eager: true, import: 'default' });
const techStack = techStackModules['/content/tech-stack.json'];

export function loadContent(lang: Lang): CVContent {
  const cv = jsonModules[`/content/${lang}/cv.json`];
  const aboutMd = aboutModules[`/content/${lang}/about.md`];
  const aboutHtml = marked.parse(aboutMd, { async: false }) as string;

  const experience: Experience[] = cv.experience.map((exp) => {
    const mdKey = `/content/${lang}/experience/${exp.id}.md`;
    const shortMdKey = `/content/${lang}/experience/${exp.id}-short.md`;

    const md = expModules[mdKey] ?? '';
    const shortMd = expModules[shortMdKey] ?? md; // Fallback to full if short doesn't exist

    const descriptionHtml = marked.parse(md, { async: false }) as string;
    const shortDescriptionHtml = marked.parse(shortMd, { async: false }) as string;

    return {
      ...exp,
      descriptionHtml,
      descriptionMd: md,
      shortDescriptionHtml,
      shortDescriptionMd: shortMd
    };
  });

  return {
    name: cv.name,
    title: cv.title,
    productTitle: cv.productTitle,
    contact: cv.contact,
    labels: cv.labels,
    employment: cv.employment,
    experience,
    education: cv.education,
    languages: cv.languages,
    aboutHtml,
    aboutMd,
    productAboutHtml: marked.parse(productAboutModules[`/content/${lang}/product-about.md`] || '', { async: false }) as string,
    productAboutMd: productAboutModules[`/content/${lang}/product-about.md`] || '',
    techStack,
  };
}
