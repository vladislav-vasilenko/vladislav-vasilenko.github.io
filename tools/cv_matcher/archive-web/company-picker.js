/* No generation: changing companies only filters stored data. null=all, []=none. */
(function(root){
 function create({container,list,search,summary,selected,onChange}){
  let options=[],value=null;
  try{const saved=JSON.parse(localStorage.getItem('cvMatcher.companySelection.v1')||'null');if(saved===null||Array.isArray(saved)&&saved.every(v=>typeof v==='string'))value=saved;}catch{}
  function changed(){try{localStorage.setItem('cvMatcher.companySelection.v1',JSON.stringify(value));}catch{}render();onChange();}
  function render(){
   const chosen=value===null?options:options.filter(c=>value.includes(c.id));summary.textContent=value===null?'Все компании':chosen.length?`Компании · ${chosen.length}`:'Компании не выбраны';
   selected.textContent=value===null?'Все уровни и компании':chosen.length?chosen.slice(0,4).map(c=>c.label).join(' · ')+(chosen.length>4?' · ещё '+(chosen.length-4):''):'Отметьте компании или выберите уровень.';
   list.replaceChildren();const query=search.value.trim().toLocaleLowerCase('ru-RU');
   for(const c of options.filter(c=>!query||(c.label+' '+c.id).toLocaleLowerCase('ru-RU').includes(query))){const label=document.createElement('label'),box=document.createElement('input'),name=document.createElement('span'),count=document.createElement('small');label.className='companyChoice';box.type='checkbox';box.checked=value===null||value.includes(c.id);box.setAttribute('aria-label',c.label);name.textContent=c.label;count.textContent=c.count;box.onchange=()=>{const ids=new Set(value===null?options.map(o=>o.id):value);box.checked?ids.add(c.id):ids.delete(c.id);value=[...ids];changed();};label.append(box,name,count);list.append(label);}
   if(!list.children.length){const p=document.createElement('p');p.textContent='Компании не найдены. Выбор сохранён.';list.append(p);}
   for(const button of container.querySelectorAll('[data-tier]'))button.setAttribute('aria-pressed',String(value!==null&&JSON.stringify([...value].sort())===JSON.stringify(options.filter(c=>c.tier===button.dataset.tier).map(c=>c.id).sort())));
  }
  search.oninput=render;
  container.querySelector('[data-companies="all"]').onclick=()=>{value=null;changed();};
  container.querySelector('[data-companies="reset"]').onclick=()=>{value=[];changed();};
  for(const b of container.querySelectorAll('[data-tier]'))b.onclick=()=>{value=options.filter(c=>c.tier===b.dataset.tier).map(c=>c.id);changed();};
  return {get value(){return value===null?null:[...value];},setOptions(rows){options=[...rows].sort((a,b)=>(a.id.startsWith('other:')-b.id.startsWith('other:'))||a.label.localeCompare(b.label,'ru'));render();}};
 }
 root.CompanyPicker={create};
})(globalThis);
