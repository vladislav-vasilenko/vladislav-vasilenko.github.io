import type {Lang} from '../i18n';
interface Category{id:string;label:string;total:number;full:number;partial:number}
export interface PublicVisuals{
 schema_version:1;
 trajectory?:{label:string;labs:{url:string;label:string}[];stages:{label:string}[];focus_skills:string[];studying:string[]};
 market?:{sample:'research'|'all';observed:number;mapped:number;points:{x:number;y:number;category:string;count:number}[];categories:Category[];method:string};

}
const text=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=10000000;
const label=(v:unknown)=>typeof v==='string'&&v.length<=250;
export function validateVisuals(value:unknown):PublicVisuals|null{
 const s=value as PublicVisuals;if(!s||s.schema_version!==1||Object.keys(s).some(k=>!['schema_version','trajectory','market'].includes(k)))return null;
 const t=s.trajectory;if(t&&(!label(t.label)||!Array.isArray(t.stages)||t.stages.length>12||t.stages.some(x=>!label(x.label))||!Array.isArray(t.labs)||t.labs.length>4||t.labs.some(l=>!label(l.label)||typeof l.url!=='string'||!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(l.url))||![t.focus_skills,t.studying].every(a=>Array.isArray(a)&&a.length<=12&&a.every(label))))return null;
 const m=s.market;if(m){
  if(!['research','all'].includes(m.sample)||!count(m.observed)||!count(m.mapped)||m.mapped>m.observed||!Array.isArray(m.categories)||m.categories.length>8||!Array.isArray(m.points)||m.points.length>1200||typeof m.method!=='string')return null;
  if(m.categories.some(c=>!label(c.id)||!label(c.label)||![c.total,c.full,c.partial].every(count)||c.total!==c.full+c.partial))return null;
  if(new Set(m.categories.map(c=>c.id)).size!==m.categories.length||m.categories.reduce((n,c)=>n+c.total,0)!==m.observed)return null;
  if(m.points.some(p=>![p.x,p.y].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=-1&&v<=1)||!count(p.count)||!m.categories.some(c=>c.id===p.category)))return null;
  if(m.points.reduce((n,p)=>n+p.count,0)!==m.mapped)return null;
 }
 return s;
}
const palette=['#6554a4','#37849b','#658355','#b07748','#a55578','#4e77b3','#9b8450','#86918b'];
function scatter(m:NonNullable<PublicVisuals['market']>,lang:Lang):string{
 if(!m.points.length)return `<p>${lang==='ru'?'Нет сохранённых актуальных оценок для карты.':'No current saved scores available for this map.'}</p>`;
 const xs=m.points.map(p=>p.x),ys=m.points.map(p=>p.y);
 const range=(values:number[])=>{const lo=Math.min(...values),hi=Math.max(...values),padding=Math.max(.025,(hi-lo)*.08);return [Math.max(-1,lo-padding),Math.min(1,hi+padding)];};
 const [xmin,xmax]=range(xs),[ymin,ymax]=range(ys);const x=(v:number)=>76+(v-xmin)/(xmax-xmin)*780,y=(v:number)=>334-(v-ymin)/(ymax-ymin)*282;
 const colors=new Map(m.categories.map((c,i)=>[c.id,palette[i%palette.length]]));
 const ticks=Array.from({length:5},(_,i)=>{const xv=xmin+(xmax-xmin)*i/4,yv=ymin+(ymax-ymin)*i/4;return `<path d="M${x(xv)} 52V334M76 ${y(yv)}H856" stroke="#dce3e6"/><text x="${x(xv)}" y="358" text-anchor="middle">${xv.toFixed(2)}</text><text x="62" y="${y(yv)+4}" text-anchor="end">${yv.toFixed(2)}</text>`;}).join('');
 return `<svg class="public-chart" viewBox="0 0 920 410" role="img" aria-label="${lang==='ru'?'Карта вакансий: семантическая близость к резюме и цели':'Vacancy map: semantic similarity to CV and career goal'}"><rect x="76" y="52" width="780" height="282" fill="#f5f8f7"/>${ticks}${m.points.map(p=>`<circle cx="${x(p.x)}" cy="${y(p.y)}" r="${Math.min(8,2+Math.sqrt(p.count))}" fill="${colors.get(p.category)}" opacity=".72" stroke="white"><title>${text(m.categories.find(c=>c.id===p.category)!.label)} · ${p.count} · X ${p.x.toFixed(2)} · Y ${p.y.toFixed(2)}</title></circle>`).join('')}<text x="466" y="394" text-anchor="middle">${lang==='ru'?'Близость к резюме · косинус':'Similarity to CV · cosine'}</text><text x="19" y="193" text-anchor="middle" transform="rotate(-90 19 193)">${lang==='ru'?'Близость к карьерной цели':'Similarity to career goal'}</text></svg><ul class="public-chart-legend">${m.categories.map((c,i)=>`<li><span style="background:${palette[i%palette.length]}"></span>${text(c.label)}</li>`).join('')}</ul>`;
}
function funnel(m:NonNullable<PublicVisuals['market']>,lang:Lang):string{
 if(!m.observed)return '';
 const gap=18,scale=240/m.observed;
 const height=Math.max(290,m.categories.reduce((n,c)=>n+Math.max(38,c.total*scale),0)+gap*Math.max(0,m.categories.length-1));
 const full=m.categories.reduce((n,c)=>n+c.full,0),partial=m.observed-full,leftY=36+(height-m.observed*scale)/2;
 const rightY=36+(height-m.observed*scale-gap)/2;
 let cy=36,sy=leftY,fy=rightY,py=rightY+full*scale+gap;
 const ribbon=(x1:number,y1:number,x2:number,y2:number,w:number,color:string)=>`<path d="M${x1} ${y1}C${(x1+x2)/2} ${y1},${(x1+x2)/2} ${y2},${x2} ${y2}L${x2} ${y2+w}C${(x1+x2)/2} ${y2+w},${(x1+x2)/2} ${y1+w},${x1} ${y1+w}Z" fill="${color}" opacity=".23"/>`;
 const rows=m.categories.map((c,i)=>{const color=palette[i%palette.length],h=c.total*scale;let result=ribbon(34,sy,350,cy,h,color)+ribbon(362,cy,768,fy,c.full*scale,color)+ribbon(362,cy+c.full*scale,768,py,c.partial*scale,color);result+=`<rect x="350" y="${cy}" width="12" height="${h}" rx="3" fill="${color}"/><text x="374" y="${cy+h/2-3}" paint-order="stroke" stroke="white" stroke-width="4" stroke-linejoin="round">${text(c.label.length>29?c.label.slice(0,28)+'…':c.label)}</text><text x="374" y="${cy+h/2+13}" class="public-svg-count">${c.total}</text>`;sy+=h;cy+=Math.max(38,h)+gap;fy+=c.full*scale;py+=c.partial*scale;return result;}).join('');
 return `<svg class="public-chart" viewBox="0 0 920 ${height+72}" role="img" aria-label="${lang==='ru'?'Потоки наблюдаемой выборки по специализации и полноте описания':'Observed sample flows by specialization and description completeness'}">${rows}<rect x="22" y="${leftY}" width="12" height="${m.observed*scale}" rx="3" fill="#47765e"/><rect x="768" y="${rightY}" width="12" height="${full*scale}" rx="3" fill="#47765e"/><rect x="768" y="${rightY+full*scale+gap}" width="12" height="${partial*scale}" rx="3" fill="#9ba7a0"/><text x="22" y="20">${lang==='ru'?'Наблюдаемая выборка':'Observed sample'} · ${m.observed}</text><text x="350" y="20">${lang==='ru'?'Специализация':'Specialization'}</text><text x="790" y="${rightY+full*scale/2-3}">${lang==='ru'?'Полный текст':'Full text'}</text><text x="790" y="${rightY+full*scale/2+14}">${full}</text><text x="790" y="${rightY+full*scale+gap+partial*scale/2-3}">${lang==='ru'?'Нужна проверка':'Needs review'}</text><text x="790" y="${rightY+full*scale+gap+partial*scale/2+14}">${partial}</text></svg>`;
}
export function renderPublicVisuals(value:PublicVisuals|null|undefined,lang:Lang):string{
 if(!value)return '';const ru=lang==='ru',t=value.trajectory,m=value.market;
 return `<section class="public-insights"><h2>${ru?'Сейчас исследую':'Current direction'}</h2>${t?`<p>${text(t.label)}</p><p class="public-skill-list">${t.focus_skills.map(s=>`<span>${text(s)}</span>`).join('')}</p>${t.labs.length?`<ul class="public-labs">${t.labs.map(l=>`<li><a href="${text(l.url)}" target="_blank" rel="noopener noreferrer">${text(l.label)} ↗</a></li>`).join('')}</ul><p class="minimal-source">${ru?'Лаборатории и материалы исследований. Практические подтверждения учитываются отдельно.':'Research labs and materials. Evidence of completed practice is tracked separately.'}</p>`:''}${t.studying.length?`<p>${ru?'Сейчас изучаю':'Currently studying'}: ${t.studying.map(text).join(', ')}</p>`:''}<details><summary>${ru?'Этапы развития':'Development stages'}</summary><ol>${t.stages.map(s=>`<li>${text(s.label)}</li>`).join('')}</ol><p class="minimal-source">${ru?'Направление и план развития; это не оценка владения навыками.':'Direction and development plan, not a measure of skill proficiency.'}</p></details>`:''}
 ${m?`<details class="public-market"><summary>Career Intelligence · ${ru?'визуализация наблюдаемого рынка':'observed market visualization'}</summary><h3>Career Opportunity Map</h3><p class="minimal-source">${m.sample==='research'?(ru?'Выборка: обучение моделей, генеративные модели, исследования и инфраструктура.':'Sample: model training, generative models, research and infrastructure.'):(ru?'Выборка: все наблюдаемые направления.':'Sample: all observed domains.')}</p><p class="minimal-source">${ru?'Сохранённые оценки из личного сервиса. Точки сгруппированы с точностью 0,01; размер показывает число записей. Семантическая близость не измеряет владение навыками или вероятность найма.':'Saved scores from the local service, grouped to 0.01; point size represents record count. Semantic similarity does not measure proficiency or hiring probability.'}</p>${scatter(m,lang)}<p class="minimal-source">${ru?'На карте':'Mapped'}: ${m.mapped} / ${m.observed}. ${ru?'Собранная выборка, не весь рынок; без идентификаторов вакансий и работодателей.':'An observed sample, not the entire market; without vacancy or employer identifiers.'}</p><h3>${ru?'Структура собранной выборки':'Observed sample composition'}</h3>${funnel(m,lang)}</details>`:''}
 <p class="minimal-source">${ru?'Публичная сводка синхронизируется из локального сервиса. SQLite на сайт не передаётся.':'A public summary synced from the local service. SQLite is never transferred to the site.'}</p></section>`;
}
