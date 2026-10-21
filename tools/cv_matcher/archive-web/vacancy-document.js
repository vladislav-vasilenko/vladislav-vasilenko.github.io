/* Display-only formatting. The archived source and analysis inputs stay unchanged. */
(function(root){
 'use strict';
 const headings=['Технологический стек','Основной стек','Модели и методы','Основные задачи','Ваши задачи','Наши ожидания','Что предстоит делать','Что нужно делать','Чем предстоит заниматься','Чем вы будете заниматься','Что мы ожидаем','Что мы предлагаем','Что предлагаем','Мы предлагаем','Мы ожидаем','Мы ждем от вас','Мы ждём от вас','Мы ждем','Мы ждём','Будет преимуществом','Будет плюсом','Обязанности','Требования','Условия','Ключевые навыки','О компании','О команде','О проекте','Responsibilities','Requirements','Qualifications','Nice to have','What we offer','Benefits'];
 const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const named=new RegExp('^(?:'+headings.map(escape).join('|')+'):?$','i');
 const flatHeading=new RegExp('(^|\\s)('+headings.map(escape).join('|')+')(?:\\s*:\\s*|(?=\\s+\\S))','g');
 function parse(value){
  let text=String(value||'').replace(/\r\n?/g,'\n'),inferred=false;
  // Legacy captures flattened all newlines. Recognize a bounded vocabulary,
  // never turn arbitrary sentences or technologies into requirements/bullets.
  if(!text.includes('\n')&&!/^\s*#{1,6}\s/.test(text))text=text.replace(flatHeading,(all,space,label)=>{inferred=true;return '\n\n'+label+'\n\n';});
  const lines=text.split('\n'),blocks=[];let paragraph=[],list=null,code=null;
  const flush=()=>{if(paragraph.length){blocks.push({type:'paragraph',text:paragraph.join('\n')});paragraph=[];}list=null;};
  for(let i=0;i<lines.length;i++){
   const line=lines[i].trim();
   if(/^```/.test(line)){flush();if(code){blocks.push({type:'code',text:code.join('\n')});code=null;}else code=[];continue;}
   if(code){code.push(lines[i]);continue;}
   if(!line){flush();continue;}
   const markdown=line.match(/^#{1,6}\s+(.+?)\s*#*$/),bold=line.match(/^(?:\*\*|__)(.+?)(?:\*\*|__):?$/);
   const heading=markdown?.[1]||(named.test(line)?line:null)||(bold&&named.test(bold[1])?bold[1]:null);
   if(heading){flush();blocks.push({type:'heading',text:heading.replace(/:$/,'')});continue;}
   if(i+1<lines.length&&/^(?:={3,}|-{3,})$/.test(lines[i+1].trim())){flush();blocks.push({type:'heading',text:line});i++;continue;}
   const item=line.match(/^(?:([-*+•‣▪])\s+|(\d+)[.)]\s+)(.+)$/);
   if(item){paragraph.length&&flush();const ordered=!!item[2],start=ordered?Number(item[2]):undefined;if(!list||list.ordered!==ordered){list={type:'list',ordered,start,items:[]};blocks.push(list);}list.items.push(item[3]);continue;}
   const quote=line.match(/^>\s?(.*)$/);if(quote){flush();blocks.push({type:'quote',text:quote[1]});continue;}
   if(/^([-*_])(?:\s*\1){2,}$/.test(line)){flush();blocks.push({type:'separator'});continue;}
   // Unmarked lines remain prose: lost list boundaries cannot be recovered reliably.
   if(list){list=null;}paragraph.push(line);
  }
  flush();if(code)blocks.push({type:'code',text:code.join('\n')});
  return {blocks,inferred};
 }
 function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
 function inline(parent,text){
  // No innerHTML, images, embeds or arbitrary Markdown attributes.
  const re=/(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g;let at=0;
  for(const match of text.matchAll(re)){
   parent.append(document.createTextNode(text.slice(at,match.index)));const value=match[0];let e;
   if(value[0]==='`')e=node('code','',value.slice(1,-1));
   else if(value.startsWith('**')||value.startsWith('__'))e=node('strong','',value.slice(2,-2));
   else if(value[0]==='*')e=node('em','',value.slice(1,-1));
   else {const link=value.match(/^\[([^\]]+)\]\((.+)\)$/);try{const url=new URL(link[2]);if(['https:','http:'].includes(url.protocol)){e=node('a','',link[1]);e.href=url.href;e.target='_blank';e.rel='noopener noreferrer';}}catch{}if(!e)e=node('span','',value);}
   parent.append(e);at=match.index+value.length;
  }
  parent.append(document.createTextNode(text.slice(at)));
 }
 function render(target,data){
  const parsed=parse(data.payload.description||''),toolbar=node('div','vacancyTextToolbar'),formatted=node('button','secondary','Читаемый вид'),source=node('button','secondary','Исходный текст'),body=node('article','vacancyDocument'),raw=node('pre','vacancyRaw',data.text);
  body.setAttribute('aria-label','Структурированное описание вакансии');raw.setAttribute('aria-label','Исходный сохранённый текст');
  for(const block of parsed.blocks){
   if(block.type==='list'){const list=node(block.ordered?'ol':'ul');if(block.ordered&&block.start!==1)list.start=block.start;for(const value of block.items){const item=node('li');inline(item,value);list.append(item);}body.append(list);}
   else {const e=node(({heading:'h3',paragraph:'p',code:'pre',quote:'blockquote',separator:'hr'})[block.type]);if(block.type==='code')e.textContent=block.text;else if(block.text)inline(e,block.text);body.append(e);}
  }
  if(!parsed.blocks.length)body.append(node('p','muted','Описание ещё не сохранено.'));
  const note=node('p','meta vacancyFormatNote',parsed.inferred?'Заголовки выделены по тексту: исходная разметка не сохранилась. Списки и формулировки не додумываются.':'Оформление по сохранённым абзацам, заголовкам и Markdown.');
  const help=node('details','vacancyReadingHelp');help.append(node('summary','','О тексте и подсветке'),note);
  if(data.term_mentions?.length){
   const label=node('label','vacancyHighlightToggle'),check=node('input');check.type='checkbox';check.checked=true;label.append(check,document.createTextNode('Подсветка по CV'));toolbar.append(label);
   const legend=node('p','meta vacancyTermLegend');legend.append(node('mark','termInCV','Есть упоминание в CV'),document.createTextNode(' · '),node('mark','termMissingCV','Не найдено в CV'),document.createTextNode(' · '+(data.term_resume?.title||'Выбранное CV')+'. Это поиск упоминаний, а не подтверждение навыка. Наведите на термин для цитаты.'));help.append(legend);
   const terms=data.term_mentions.flatMap(item=>item.terms.map(term=>({...item,term}))).sort((a,b)=>b.term.length-a.term.length),byTerm=new Map(terms.map(t=>[t.term.toLowerCase(),t])),pattern=new RegExp(terms.map(t=>escape(t.term)).join('|'),'gi');
   function highlight(){
    for(const mark of body.querySelectorAll('mark'))mark.replaceWith(document.createTextNode(mark.textContent));if(!check.checked)return;
    const texts=[];const visit=e=>{for(const child of e.childNodes){if(child.nodeType===3)texts.push(child);else visit(child);}};visit(body);
    for(const text of texts){const value=text.textContent,fragment=document.createDocumentFragment();let at=0;for(const match of value.matchAll(pattern)){const before=value[match.index-1]||'',after=value[match.index+match[0].length]||'';if(/[\p{L}\p{N}_]/u.test(before)||/[\p{L}\p{N}_]/u.test(after))continue;fragment.append(document.createTextNode(value.slice(at,match.index)));const term=byTerm.get(match[0].toLowerCase()),mark=node('mark',term.in_cv?'termInCV':'termMissingCV',match[0]);mark.title=term.in_cv?'Есть упоминание в выбранном CV: «'+term.quote+'». Упоминание может относиться к обучению, отрицанию или планам; это не подтверждение опыта.':'Термин «'+term.label+'» не найден в выбранном CV. Навык может быть у вас, но не описан этим термином.';fragment.append(mark);at=match.index+match[0].length;}if(at){fragment.append(document.createTextNode(value.slice(at)));text.replaceWith(fragment);}}
   }
   check.onchange=highlight;highlight();
  }
  function select(rawMode){body.hidden=rawMode;note.hidden=rawMode;raw.hidden=!rawMode;formatted.setAttribute('aria-pressed',String(!rawMode));source.setAttribute('aria-pressed',String(rawMode));}
  formatted.type=source.type='button';formatted.onclick=()=>select(false);source.onclick=()=>select(true);const switcher=node('div','vacancyViewSwitch');switcher.setAttribute('role','group');switcher.setAttribute('aria-label','Представление текста');switcher.append(formatted,source);toolbar.prepend(switcher);toolbar.append(help);target.append(toolbar,body,raw);select(false);
 }
 root.VacancyDocument={parse,render,inline};
})(globalThis);
