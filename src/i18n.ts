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
  descriptionHtml: string;
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
  contact: {
    phone: string;
    email: string;
    location: string;
    citizenship: string;
    relocation: string;
  };
  labels: {
    about: string;
    experience: string;
    education: string;
    skills: string;
    languages: string;
    employment: string;
  };
  employment: string;
  experience: Omit<Experience, 'descriptionHtml'>[];
  education: Education[];
  languages: string[];
}

export interface CVContent {
  name: string;
  title: string;
  contact: CVJson['contact'];
  labels: CVJson['labels'];
  employment: string;
  experience: Experience[];
  education: Education[];
  languages: string[];
  aboutHtml: string;
  techStack: TechStack;
}

const jsonModules = import.meta.glob<CVJson>('/content/*/cv.json', { eager: true, import: 'default' });
const aboutModules = import.meta.glob<string>('/content/*/about.md', { eager: true, query: '?raw', import: 'default' });
const expModules = import.meta.glob<string>('/content/*/experience/*.md', { eager: true, query: '?raw', import: 'default' });
const techStackModules = import.meta.glob<TechStack>('/content/tech-stack.json', { eager: true, import: 'default' });
const techStack = techStackModules['/content/tech-stack.json'];

export function loadContent(lang: Lang): CVContent {
  const cv = jsonModules[`/content/${lang}/cv.json`];
  const aboutMd = aboutModules[`/content/${lang}/about.md`];
  const aboutHtml = marked.parse(aboutMd, { async: false }) as string;

  const experience: Experience[] = cv.experience.map((exp) => {
    const mdKey = `/content/${lang}/experience/${exp.id}.md`;
    const md = expModules[mdKey] ?? '';
    const descriptionHtml = marked.parse(md, { async: false }) as string;
    return { ...exp, descriptionHtml };
  });

  return {
    name: cv.name,
    title: cv.title,
    contact: cv.contact,
    labels: cv.labels,
    employment: cv.employment,
    experience,
    education: cv.education,
    languages: cv.languages,
    aboutHtml,
    techStack,
  };
}
