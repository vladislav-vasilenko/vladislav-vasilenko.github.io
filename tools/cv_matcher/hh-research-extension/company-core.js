(function(root){
 let groups=[];
 const normalize=value=>String(value||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
 function configure(value){groups=value;}
 function key(value){const clean=normalize(value);const matches=groups.flatMap(g=>g.aliases.filter(alias=>clean.includes(normalize(alias))).map(alias=>({id:g.id,length:normalize(alias).length})));return matches.sort((a,b)=>b.length-a.length)[0]?.id||'other:'+clean;}
 function label(value){return groups.find(g=>g.id===key(value))?.label||String(value||'Компания не указана');}
 root.CompanyFilters={configure,key,label};
})(globalThis);
