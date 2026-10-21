(function(root){
 const months='январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья]|January|February|March|April|May|June|July|August|September|October|November|December';
 const duration=/^(?:\d+|год(?:а)?|лет|месяц(?:а|ев)?|year(?:s)?|month(?:s)?|и|and)$/i;
 const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
 function experience(value){
  const original=String(value||'').split('\n'),entries=original.map((text,index)=>({text:text.trim(),index})).filter(e=>e.text&&!/^(добавить|add)$/i.test(e.text)),lines=entries.map(e=>e.text);
  const starts=[];const month=new RegExp('^(?:'+months+')$','i');
  for(let i=1;i+3<lines.length;i++)if(month.test(lines[i])&&/^\d{4}$/.test(lines[i+1])&&/^[—–-]$/.test(lines[i+2])){
   let end=i+3;if(month.test(lines[end])&&/^\d{4}$/.test(lines[end+1]))end+=2;else if(/^(сейчас|настоящее время|now|present)$/i.test(lines[end]))end++;else continue;
   let after=end,dur='';if(lines[after]==='('){const close=lines.indexOf(')',after+1);if(close>=after&&close-after<14){dur=clean(lines.slice(after+1,close).join(' '));after=close+1;}}
   let role=i-1,header=role,j=role-1;while(j>=0&&duration.test(lines[j]))j--;
   let company=null;if(j<role-1&&j>=0){company=lines[j];header=j;}
   starts.push({header,role,start:i,end,after,duration:dur,company,dates:clean(lines.slice(i,end).join(' '))});i=after-1;
  }
  if(!starts.length)return {items:[],unparsed:clean(lines.join('\n'))};
  let lastCompany='';const items=starts.map((s,index)=>{lastCompany=s.company||lastCompany;return {company:lastCompany,role:lines[s.role],dates:s.dates,duration:s.duration,description:lines.slice(s.after,starts[index+1]?.header??lines.length).join('\n'),raw:original.slice(entries[s.header].index,entries[starts[index+1]?.header]?.index??original.length).join('\n')};});
  return {items,unparsed:starts[0].header>0?lines.slice(0,starts[0].header).join('\n'):''};
 }
 root.ResumeProfileCore={experience,clean};
})(globalThis);
