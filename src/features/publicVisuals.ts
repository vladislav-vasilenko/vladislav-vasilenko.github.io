import {directionArrow} from './directionArrow';
import type {Lang} from '../i18n';
interface Category{id:string;label:string;total:number;full:number;partial:number}
export interface PublicVisuals{
 schema_version:1;
 trajectory?:{label:string;labs:{url:string;label:string}[];stages:{label:string}[];focus_skills:string[];studying:string[]};
 market?:{employers?:{name:string;counts:[string,string,number,number][]}[];markets?:{id:string;categories:{id:string;total:number;full:number;partial:number}[]}[];examples?:Record<string,MarketExample[]>;data_as_of?:string;sample:'research'|'experience'|'all';observed:number;mapped:number;points:{x:number;y:number;category:string;count:number;market?:string}[];categories:(Category&{color?:number})[];method:string};

}
const text=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const count=(v:unknown)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=10000000;
const label=(v:unknown)=>typeof v==='string'&&v.length<=250;
export interface MarketExample{title:string;company?:string;summary:string;keywords:string[];market?:string}
const MARKET_IDS=['ru','us','south_america','uk','canada','europe','china','japan','au_nz','other'];
// Only short descriptive text may reach the page: no links, addresses or extra fields.
const plainText=(v:unknown,max:number)=>typeof v==='string'&&v.length>0&&v.length<=max&&!/https?:|www\.|@/i.test(v);
function validExamples(m:{examples?:unknown;categories:{id:string}[]}):boolean{
 if(m.examples===undefined)return true;
 const groups=m.examples as Record<string,MarketExample[]>;if(!groups||typeof groups!=='object'||Array.isArray(groups))return false;
 return Object.entries(groups).every(([id,items])=>m.categories.some(c=>c.id===id)&&Array.isArray(items)&&items.length<=250&&items.every(item=>item&&Object.keys(item).every(k=>['title','company','summary','market','keywords'].includes(k))&&(item.company===undefined||plainText(item.company,100))&&(item.market===undefined||MARKET_IDS.includes(item.market))&&plainText(item.title,200)&&plainText(item.summary,220)&&Array.isArray(item.keywords)&&item.keywords.length<=6&&item.keywords.every(k=>plainText(k,60))));
}
export function validateVisuals(value:unknown):PublicVisuals|null{
 const s=value as PublicVisuals;if(!s||s.schema_version!==1||Object.keys(s).some(k=>!['schema_version','trajectory','market'].includes(k)))return null;
 const t=s.trajectory;if(t&&(!label(t.label)||!Array.isArray(t.stages)||t.stages.length>12||t.stages.some(x=>!label(x.label))||!Array.isArray(t.labs)||t.labs.length>4||t.labs.some(l=>!label(l.label)||typeof l.url!=='string'||!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(l.url))||![t.focus_skills,t.studying].every(a=>Array.isArray(a)&&a.length<=12&&a.every(label))))return null;
 const m=s.market;if(m){
  if(m.data_as_of!==undefined&&(typeof m.data_as_of!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(m.data_as_of)||Number.isNaN(Date.parse(m.data_as_of))))return null;
  if(!['research','experience','all'].includes(m.sample)||!count(m.observed)||!count(m.mapped)||m.mapped>m.observed||!Array.isArray(m.categories)||m.categories.length>8||!Array.isArray(m.points)||m.points.length>1200||typeof m.method!=='string')return null;
  if(m.categories.some(c=>!label(c.id)||!label(c.label)||![c.total,c.full,c.partial].every(count)||c.total!==c.full+c.partial))return null;
  if(new Set(m.categories.map(c=>c.id)).size!==m.categories.length||m.categories.reduce((n,c)=>n+c.total,0)!==m.observed)return null;
  if(m.points.some(p=>![p.x,p.y].every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=-1&&v<=1)||!count(p.count)||!m.categories.some(c=>c.id===p.category)))return null;
  if(m.points.reduce((n,p)=>n+p.count,0)!==m.mapped)return null;
  if(!validExamples(m))return null;
  if(m.employers!==undefined&&(!Array.isArray(m.employers)||m.employers.length>400||m.employers.some(x=>!x||!plainText(x.name,100)||!Array.isArray(x.counts)||x.counts.some(c=>!Array.isArray(c)||!MARKET_IDS.includes(c[0])||!m.categories.some(k=>k.id===c[1])||!count(c[2])||!count(c[3])))))return null;
  if(m.points.some(p=>p.market!==undefined&&!MARKET_IDS.includes(p.market)))return null;
  if(m.markets!==undefined){
   if(!Array.isArray(m.markets)||m.markets.some(x=>!x||!MARKET_IDS.includes(x.id)||!Array.isArray(x.categories)||x.categories.some(c=>!m.categories.some(k=>k.id===c.id)||![c.total,c.full,c.partial].every(count)||c.total!==c.full+c.partial)))return null;
   if(m.categories.some(c=>m.markets!.reduce((n,x)=>n+(x.categories.find(k=>k.id===c.id)?.total||0),0)!==c.total))return null;
  }
 }
 return s;
}
const palette=['#6554a4','#37849b','#658355','#b07748','#a55578','#4e77b3','#9b8450','#86918b'];
function scatter(m:NonNullable<PublicVisuals['market']>,lang:Lang):string{
 if(!m.points.length)return `<p>${lang==='ru'?'Нет сохранённых актуальных оценок для карты.':'No current saved scores available for this map.'}</p>`;
 const xs=m.points.map(p=>p.x),ys=m.points.map(p=>p.y);
 const range=(values:number[])=>{const lo=Math.min(...values),hi=Math.max(...values),padding=Math.max(.025,(hi-lo)*.08);return [Math.max(-1,lo-padding),Math.min(1,hi+padding)];};
 const [xmin,xmax]=range(xs),[ymin,ymax]=range(ys);const x=(v:number)=>76+(v-xmin)/(xmax-xmin)*780,y=(v:number)=>334-(v-ymin)/(ymax-ymin)*282;
 const colors=new Map(m.categories.map((c,i)=>[c.id,palette[(c.color??i)%palette.length]]));
 const ticks=Array.from({length:5},(_,i)=>{const xv=xmin+(xmax-xmin)*i/4,yv=ymin+(ymax-ymin)*i/4;return `<path d="M${x(xv)} 52V334M76 ${y(yv)}H856" stroke="#dce3e6"/><text x="${x(xv)}" y="358" text-anchor="middle">${xv.toFixed(2)}</text><text x="62" y="${y(yv)+4}" text-anchor="end">${yv.toFixed(2)}</text>`;}).join('');
 return `<svg class="public-chart" viewBox="0 0 920 410" role="img" aria-label="${lang==='ru'?'Карта вакансий: семантическая близость к резюме и цели':'Vacancy map: semantic similarity to CV and career goal'}"><rect x="76" y="52" width="780" height="282" fill="#f5f8f7"/>${ticks}${m.points.map(p=>`<circle cx="${x(p.x)}" cy="${y(p.y)}" r="${Math.min(8,2+Math.sqrt(p.count))}" fill="${colors.get(p.category)}" opacity=".72" stroke="white"><title>${text(m.categories.find(c=>c.id===p.category)!.label)} · ${p.count} · X ${p.x.toFixed(2)} · Y ${p.y.toFixed(2)}</title></circle>`).join('')}<text x="466" y="394" text-anchor="middle">${lang==='ru'?'Близость к резюме · косинус':'Similarity to CV · cosine'}</text><text x="19" y="193" text-anchor="middle" transform="rotate(-90 19 193)">${lang==='ru'?'Близость к карьерной цели':'Similarity to career goal'}</text></svg><ul class="public-chart-legend">${m.categories.map((c,i)=>`<li><span style="background:${palette[i%palette.length]}"></span>${text(c.label)}</li>`).join('')}</ul>`;
}
function examples(m:NonNullable<PublicVisuals['market']>,lang:Lang):string{
 if(!m.examples)return '';const ru=lang==='ru';
 const blocks=m.categories.map((c,i)=>{const items=m.examples?.[c.id];if(!items?.length)return '';
  return `<details class="public-examples" id="market-category-${i}" data-market-panel><summary>${text(c.label)} · ${ru?'примеры':'examples'}: ${items.length} ${ru?'из':'of'} ${c.total}</summary><ul>${items.map(item=>`<li><strong>${text(item.title)}</strong>${item.company?`<p class="public-example-company">${text(item.company)}</p>`:''}<p>${text(item.summary)}</p>${item.keywords.length?`<p class="public-example-tags">${item.keywords.map(text).join(' · ')}</p>`:''}</li>`).join('')}</ul></details>`;}).join('');
 return blocks?`<p class="minimal-source">${ru?'Нажмите на категорию на диаграмме или в списке, чтобы увидеть самые новые вакансии. Это срез рынка, а не список компаний, куда я откликаюсь.':'Select a category in the chart or the list to see the newest vacancies. This is a market snapshot, not a list of companies I am applying to.'}</p>${blocks}`:'';
}
function funnel(m:NonNullable<PublicVisuals['market']>,lang:Lang):string{
 if(!m.observed)return '';
 const gap=18,scale=240/m.observed;
 const height=Math.max(290,m.categories.reduce((n,c)=>n+Math.max(38,c.total*scale),0)+gap*Math.max(0,m.categories.length-1));
 const full=m.categories.reduce((n,c)=>n+c.full,0),partial=m.observed-full,leftY=36+(height-m.observed*scale)/2;
 const rightY=36+(height-m.observed*scale-gap)/2;
 let cy=36,sy=leftY,fy=rightY,py=rightY+full*scale+gap;
 const ribbon=(x1:number,y1:number,x2:number,y2:number,w:number,color:string)=>`<path d="M${x1} ${y1}C${(x1+x2)/2} ${y1},${(x1+x2)/2} ${y2},${x2} ${y2}L${x2} ${y2+w}C${(x1+x2)/2} ${y2+w},${(x1+x2)/2} ${y1+w},${x1} ${y1+w}Z" fill="${color}" opacity=".23"/>`;
 const rows=m.categories.map((c,i)=>{const color=palette[(c.color??i)%palette.length],h=c.total*scale;let result=ribbon(34,sy,350,cy,h,color)+ribbon(362,cy,768,fy,c.full*scale,color)+ribbon(362,cy+c.full*scale,768,py,c.partial*scale,color);const node=`<rect x="350" y="${cy}" width="12" height="${h}" rx="3" fill="${color}"/><text x="374" y="${cy+h/2-3}" paint-order="stroke" stroke="white" stroke-width="4" stroke-linejoin="round">${text(c.label.length>29?c.label.slice(0,28)+'…':c.label)}</text><text x="374" y="${cy+h/2+13}" class="public-svg-count">${c.total}</text>`;result+=m.examples?.[c.id]?.length?`<a class="public-node" href="#market-category-${i}" data-market-category="market-category-${i}" aria-label="${text(c.label)}"><rect x="340" y="${cy-4}" width="300" height="${Math.max(38,h+8)}" fill="transparent"/>${node}</a>`:node;sy+=h;cy+=Math.max(38,h)+gap;fy+=c.full*scale;py+=c.partial*scale;return result;}).join('');
 return `<svg class="public-chart" viewBox="0 0 920 ${height+72}" role="${m.examples?'group':'img'}" aria-label="${lang==='ru'?'Потоки наблюдаемой выборки по специализации и полноте описания':'Observed sample flows by specialization and description completeness'}">${rows}<rect x="22" y="${leftY}" width="12" height="${m.observed*scale}" rx="3" fill="#47765e"/><rect x="768" y="${rightY}" width="12" height="${full*scale}" rx="3" fill="#47765e"/><rect x="768" y="${rightY+full*scale+gap}" width="12" height="${partial*scale}" rx="3" fill="#9ba7a0"/><text x="22" y="20">${lang==='ru'?'Наблюдаемая выборка':'Observed sample'} · ${m.observed}</text><text x="350" y="20">${lang==='ru'?'Специализация':'Specialization'}</text><text x="790" y="${rightY+full*scale/2-3}">${lang==='ru'?'Полный текст':'Full text'}</text><text x="790" y="${rightY+full*scale/2+14}">${full}</text><text x="790" y="${rightY+full*scale+gap+partial*scale/2-3}">${lang==='ru'?'Нужна проверка':'Needs review'}</text><text x="790" y="${rightY+full*scale+gap+partial*scale/2+14}">${partial}</text></svg>`;
}
/** Narrows the flow chart and cards to one employer inside the chosen market. */
function employerView(m:NonNullable<PublicVisuals['market']>,market:string,employer:string):NonNullable<PublicVisuals['market']>{
 const counts=(m.employers?.find(x=>x.name===employer)?.counts||[]).filter(c=>market==='all'||c[0]===market);
 const categories=m.categories.flatMap(c=>{const rows=counts.filter(r=>r[1]===c.id),full=rows.reduce((n,r)=>n+r[2],0),partial=rows.reduce((n,r)=>n+r[3],0);return full+partial?[{...c,total:full+partial,full,partial}]:[];});
 return {...m,categories,observed:categories.reduce((n,c)=>n+c.total,0),examples:m.examples&&Object.fromEntries(Object.entries(m.examples).map(([k,v])=>[k,v.filter(x=>x.company===employer)]))};
}
function employerOptions(m:NonNullable<PublicVisuals['market']>,market:string,lang:Lang):string{
 const rows=(m.employers||[]).map(x=>({name:x.name,n:x.counts.filter(c=>market==='all'||c[0]===market).reduce((t,c)=>t+c[2]+c[3],0)})).filter(x=>x.n).sort((a,b)=>b.n-a.n||a.name.localeCompare(b.name));
 return `<option value="">${lang==='ru'?'Все работодатели':'All employers'}</option>${rows.map(x=>`<option value="${text(x.name)}">${text(x.name)} · ${x.n}</option>`).join('')}`;
}
function marketBody(m:NonNullable<PublicVisuals['market']>,lang:Lang,flow:NonNullable<PublicVisuals['market']>=m,employer=''):string{
 const ru=lang==='ru';
 return `<h3>Career Opportunity Map</h3>${m.data_as_of?`<p class="minimal-source">${ru?'Данные обновлены: ':'Data updated: '}${new Date(m.data_as_of+'T00:00:00Z').toLocaleDateString(ru?'ru-RU':'en-US',{timeZone:'UTC',year:'numeric',month:'long',day:'numeric'})}</p>`:''}<p class="minimal-source">${m.sample==='experience'?(ru?'Выборка: вакансии по направлениям моего опыта: обучение моделей, генеративные модели, исследования, инфраструктура, LLM-приложения и прикладной AI.':'Sample: vacancies in the areas of my experience: model training, generative models, research, infrastructure, LLM applications and applied AI.'):m.sample==='research'?(ru?'Выборка: обучение моделей, генеративные модели, исследования и инфраструктура.':'Sample: model training, generative models, research and infrastructure.'):(ru?'Выборка: все наблюдаемые направления.':'Sample: all observed domains.')}</p><p class="minimal-source">${ru?'Сохранённые оценки из личного сервиса. Точки сгруппированы с точностью 0,01; размер показывает число записей. Семантическая близость не измеряет владение навыками или вероятность найма.':'Saved scores from the local service, grouped to 0.01; point size represents record count. Semantic similarity does not measure proficiency or hiring probability.'}</p>${scatter(m,lang)}<p class="minimal-source">${ru?'На карте':'Mapped'}: ${m.mapped} / ${m.observed}. ${ru?'Собранная выборка, не весь рынок.':'An observed sample, not the entire market.'}</p><h3>${ru?'Структура собранной выборки':'Observed sample composition'}</h3>${employer?`<p class="minimal-source">${ru?`Диаграмма и примеры: ${text(employer)}. Карта показывает весь выбранный рынок: близость к резюме не публикуется по компаниям.`:`Chart and examples: ${text(employer)}. The map shows the whole selected market: similarity to my CV is not published per company.`}</p>`:''}${funnel(flow,lang)}${examples(flow,lang)}`;
}
const MARKET_LABELS:Record<string,{ru:string;en:string}>={ru:{ru:'Россия',en:'Russia'},us:{ru:'США',en:'US'},south_america:{ru:'Южная Америка',en:'South America'},uk:{ru:'Великобритания',en:'UK'},canada:{ru:'Канада',en:'Canada'},europe:{ru:'Европа',en:'Europe'},china:{ru:'Китай',en:'China'},japan:{ru:'Япония',en:'Japan'},au_nz:{ru:'Австралия / Новая Зеландия',en:'Australia / New Zealand'},other:{ru:'Другие',en:'Other'}};
/** One market's slice. Each category keeps its color, so a filter never recolors the chart. */
function marketView(m:NonNullable<PublicVisuals['market']>,id:string):NonNullable<PublicVisuals['market']>{
 const colored=m.categories.map((c,i)=>({...c,color:i}));
 if(id==='all')return {...m,categories:colored,examples:m.examples&&Object.fromEntries(Object.entries(m.examples).map(([k,v])=>[k,v.slice(0,25)]))};
 const counts=new Map(m.markets?.find(x=>x.id===id)?.categories.map(c=>[c.id,c])),categories=colored.flatMap(c=>{const n=counts.get(c.id);return n?[{...c,total:n.total,full:n.full,partial:n.partial}]:[];});
 const points=m.points.filter(p=>p.market===id);
 return {...m,categories,observed:categories.reduce((n,c)=>n+c.total,0),points,mapped:points.reduce((n,p)=>n+p.count,0),examples:m.examples&&Object.fromEntries(Object.entries(m.examples).map(([k,v])=>[k,v.filter(x=>x.market===id).slice(0,25)]))};
}
function marketFilter(m:NonNullable<PublicVisuals['market']>,lang:Lang):string{
 if(!m.markets?.length)return '';const ru=lang==='ru';
 const button=(id:string,label:string,n:number,active:boolean)=>`<button type="button" data-market-filter="${text(id)}" aria-pressed="${active}">${text(label)} · ${n}</button>`;
 return `<div class="public-market-filter" role="group" aria-label="${ru?'Рынок':'Market'}">${button('all',ru?'Все рынки':'All markets',m.observed,true)}${m.markets.map(x=>button(x.id,MARKET_LABELS[x.id][lang],x.categories.reduce((n,c)=>n+c.total,0),false)).join('')}</div>${m.employers?.length?`<label class="public-employer-filter">${ru?'Работодатель':'Employer'} <select data-market-employer>${employerOptions(m,'all',lang)}</select></label>`:''}<p class="minimal-source">${ru?'Рынок определён по месту в вакансии, а если оно не указано, по стране работодателя. В списке крупнейшие работодатели каждого рынка.':'Market comes from the vacancy location, or from the employer country when it is missing. The list shows the largest employers in each market.'}</p>`;
}
function bindCategories(root:ParentNode):void{
 root.querySelectorAll<SVGAElement>('[data-market-category]').forEach(node=>node.addEventListener('click',event=>{
  const panel=root.querySelector<HTMLDetailsElement>('#'+node.dataset.marketCategory);if(!panel)return;
  event.preventDefault();root.querySelectorAll<HTMLDetailsElement>('[data-market-panel]').forEach(other=>{other.open=other===panel;});
  panel.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
 }));
}
/** Chart clicks open a category list; market buttons redraw the charts. Without JavaScript the page shows all markets. */
export function bindMarketExamples(root:ParentNode,value:PublicVisuals|null|undefined,lang:Lang):void{
 bindCategories(root);const m=value?.market,body=root.querySelector<HTMLElement>('[data-market-body]');if(!m||!body)return;
 const employer=root.querySelector<HTMLSelectElement>('[data-market-employer]');let market='all';
 const draw=()=>{const view=marketView(m,market),name=employer?.value||'';body.innerHTML=marketBody(view,lang,name?employerView(view,market,name):view,name);bindCategories(body);};
 root.querySelectorAll<HTMLButtonElement>('[data-market-filter]').forEach(button=>button.addEventListener('click',()=>{
  root.querySelectorAll<HTMLButtonElement>('[data-market-filter]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));
  market=button.dataset.marketFilter||'all';if(employer)employer.innerHTML=employerOptions(m,market,lang);draw();
 }));
 employer?.addEventListener('change',draw);
}
export function renderPublicVisuals(value:PublicVisuals|null|undefined,lang:Lang):string{
 if(!value)return '';const ru=lang==='ru',t=value.trajectory,m=value.market;
 return `<section class="public-insights"><h2>${ru?'Сейчас исследую':'Current direction'}</h2>${t?`<p>${text(t.label)}</p><p class="public-skill-list">${t.focus_skills.map(s=>`<span>${text(s)}</span>`).join('')}</p>${t.labs.length?`<ul class="public-labs">${t.labs.map(l=>`<li><a href="${text(l.url)}" target="_blank" rel="noopener noreferrer">${text(l.label)} ${directionArrow('external')}</a></li>`).join('')}</ul><p class="minimal-source">${ru?'Лаборатории и материалы исследований. Практические подтверждения учитываются отдельно.':'Research labs and materials. Evidence of completed practice is tracked separately.'}</p>`:''}${t.studying.length?`<p>${ru?'Сейчас изучаю':'Currently studying'}: ${t.studying.map(text).join(', ')}</p>`:''}<details><summary>${ru?'Этапы развития':'Development stages'}</summary><ol>${t.stages.map(s=>`<li>${text(s.label)}</li>`).join('')}</ol><p class="minimal-source">${ru?'Направление и план развития; это не оценка владения навыками.':'Direction and development plan, not a measure of skill proficiency.'}</p></details>`:''}
 ${m?`<details class="public-market"><summary>Career Intelligence · ${ru?'визуализация наблюдаемого рынка':'observed market visualization'}</summary>${marketFilter(m,lang)}<div data-market-body>${marketBody(marketView(m,'all'),lang)}</div></details>`:''}
 <p class="minimal-source">${ru?'Публичная сводка синхронизируется из локального сервиса. SQLite на сайт не передаётся.':'A public summary synced from the local service. SQLite is never transferred to the site.'}</p></section>`;
}
