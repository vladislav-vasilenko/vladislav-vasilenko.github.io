import {directionArrow} from './directionArrow';
import {validateVisuals,type PublicVisuals} from './publicVisuals';
import type {CVContent, Experience, Lang} from '../i18n';

export interface HHSnapshot {
  schema_version: 1;
  visuals?: PublicVisuals|null;
  enabled: boolean;
  title?:string;
  source: {label: string; language: Lang; captured_at: string; url?: string; translated_from?:Lang};
  about?: {text:string; language:Lang; origin:'hh'|'reviewed'; translations?:Partial<Record<Lang,string>>};
  experience: {id: string; company: string; role: string; period: string; duration: string; description: string}[];
  experience_basis?:string;
  experience_translations?:Partial<Record<Lang,{basis:string;items:HHSnapshot['experience']}>>;
  confirmed_skills: {id: string; label: string; links: {url: string; label: string}[]}[];
}
export const escapeText = (value: string): string => value.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));

export function validateSnapshot(value: unknown): HHSnapshot | null {
  const s=value as HHSnapshot;
  if(!s||s.schema_version!==1||!s.enabled||!s.source||!['ru','en'].includes(s.source.language)||!Array.isArray(s.experience)||!s.experience.length||s.experience.length>80)return null;
  if(s.title!==undefined&&(typeof s.title!=='string'||!s.title.trim()||s.title.length>1000))return null;
  if(s.source.translated_from!==undefined&&!['ru','en'].includes(s.source.translated_from))return null;
  if(s.source.url && !/^https:\/\/hh\.ru\/resume\/[a-fA-F0-9]{30,64}$/.test(s.source.url))return null;
  if(s.about && (typeof s.about.text!=='string'||s.about.text.length>10000||!['ru','en'].includes(s.about.language)||!['hh','reviewed'].includes(s.about.origin)))return null;
  if(s.about?.translations && Object.entries(s.about.translations).some(([k,v])=>!['ru','en'].includes(k)||typeof v!=='string'||v.length>6000))return null;
  if(s.visuals && !validateVisuals(s.visuals))return null;
  for(const row of s.experience){
    if(!row||!['id','company','role','period','duration','description'].every(k=>typeof row[k as keyof typeof row]==='string'))return null;
    if(row.description.length>100000||[row.id,row.company,row.role,row.period,row.duration].some(v=>v.length>2000))return null;
  }
  if(s.experience_basis!==undefined&&(typeof s.experience_basis!=='string'||!/^[a-f0-9]{64}$/.test(s.experience_basis)))return null;
  if(s.experience_translations!==undefined){
    if(!s.experience_basis||!s.experience_translations||typeof s.experience_translations!=='object'||Array.isArray(s.experience_translations))return null;
    for(const [language,translation] of Object.entries(s.experience_translations)){
      if(!['ru','en'].includes(language)||!translation||typeof translation.basis!=='string'||!/^[a-f0-9]{64}$/.test(translation.basis)||!Array.isArray(translation.items)||translation.items.length>80)return null;
      for(const row of translation.items){
        if(!row||!['id','company','role','period','duration','description'].every(k=>typeof row[k as keyof typeof row]==='string'))return null;
        if(row.description.length>100000||[row.id,row.company,row.role,row.period,row.duration].some(v=>v.length>2000))return null;
      }
    }
  }
  if(!Array.isArray(s.confirmed_skills)||s.confirmed_skills.length>100)return null;
  for(const skill of s.confirmed_skills){
    if(!skill||typeof skill.label!=='string'||skill.label.length>300||!Array.isArray(skill.links)||skill.links.length>100)return null;
    for(const link of skill.links){
      if(typeof link.label!=='string'||link.label.length>300||typeof link.url!=='string'||!/^https:\/\/github\.com\/[\w.-]+\/[\w./%-]+$/.test(link.url))return null;
    }
  }
  return s;
}

/** A translation is usable only for the exact primary work-history revision it was reviewed against. */
export function localizeHHSnapshot(snapshot:HHSnapshot|null, lang:Lang):HHSnapshot|null {
  if(!snapshot||snapshot.source.language===lang)return snapshot;
  const translation=snapshot.experience_translations?.[lang];
  if(!translation||!snapshot.experience_basis||translation.basis!==snapshot.experience_basis)return snapshot;
  const rows=new Map(translation.items.map(row=>[row.id,row]));
  if(rows.size!==snapshot.experience.length||translation.items.length!==rows.size||snapshot.experience.some(row=>!rows.has(row.id)))return snapshot;
  return {...snapshot,source:{...snapshot.source,language:lang,translated_from:snapshot.source.language},
    experience:snapshot.experience.map(row=>({...rows.get(row.id)!}))};
}

export async function loadHHSnapshot(): Promise<HHSnapshot|null> {
  try {
    const response=await fetch('/hh-experience.json',{cache:'no-cache',signal:AbortSignal.timeout(8000)});
    if(!response.ok)return null;
    const text=await response.text();if(text.length>500000)return null;
    return validateSnapshot(JSON.parse(text));
  }catch{return null;}
}

export function applyHHSnapshot(cv: CVContent, snapshot: HHSnapshot|null, lang?:Lang): CVContent {
  if(lang)snapshot=localizeHHSnapshot(snapshot,lang);
  if(!snapshot)return cv;
  const experience: Experience[]=snapshot.experience.map(row=>({
    ...row,location:'',profiles:['technical','product'],descriptionMd:row.description,
    descriptionHtml:'<p>'+escapeText(row.description).replace(/\n/g,'<br>')+'</p>',
    shortDescriptionMd:row.description.split('\n\n')[0]||row.description,
    shortDescriptionHtml:'<p>'+escapeText(row.description.split('\n\n')[0]||row.description).replace(/\n/g,'<br>')+'</p>',
  }));
  const intro=(lang&&snapshot.about?.translations?.[lang])||snapshot.about?.text;
  return {...cv,experience,...(snapshot.title?{title:snapshot.title}:{}),...(intro?{aboutMd:intro,aboutHtml:'<p>'+escapeText(intro).replace(/\n/g,'<br>')+'</p>'}:{})};
}

export function renderHHSource(snapshot:HHSnapshot|null, lang:Lang):string {
  if(!snapshot)return '';
  const language=snapshot.source.language.toUpperCase();
  return `<p class="hh-source">${snapshot.source.url?`<a href="${escapeText(snapshot.source.url)}" target="_blank" rel="noopener noreferrer">${lang==='ru'?'Основное HH-резюме':'Primary HH resume'} ${directionArrow('external')}</a>`:(lang==='ru'?'Основное HH-резюме':'Primary HH resume')} · ${language}${snapshot.source.language!==lang?' · '+(lang==='ru'?'Ожидается перевод':'Translation pending'):''}</p>`;
}

export function renderConfirmedSkills(snapshot:HHSnapshot|null,lang:Lang):string {
  if(!snapshot?.confirmed_skills.length)return '';
  return `<section class="cv-section hh-confirmed"><h2>${lang==='ru'?'Подтверждённые навыки':'Skills backed by projects'}</h2><p class="hh-source">${lang==='ru'?'Подтверждения отмечены владельцем; ссылки на проекты и лабораторные.':'Evidence marked by the owner; links to projects and labs.'}</p><ul>${snapshot.confirmed_skills.map(s=>`<li><strong>${escapeText(s.label)}</strong> — ${s.links.map(l=>`<a href="${escapeText(l.url)}" target="_blank" rel="noopener noreferrer">${escapeText(l.label)}</a>`).join(', ')}</li>`).join('')}</ul></section>`;
}
