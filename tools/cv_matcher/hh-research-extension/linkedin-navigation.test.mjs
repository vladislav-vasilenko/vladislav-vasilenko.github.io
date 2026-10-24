import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import {webcrypto} from 'node:crypto';
// Two different real DOM contracts: homepage anchors with lazy growth, and
// paginated clickable cards whose job ID exists only after selecting a card.
function fixture(mode){
 let page=0,count=10,current=1000;const pageSize=25,total=83,location=new URL(mode==='infinite'?'https://www.linkedin.com/jobs/':'https://www.linkedin.com/jobs/search-results/?origin=INFINITE_JOBS_LANDING&currentJobId=1000');
 class N{
  constructor(tag,text='',attrs={}){this.tagName=tag.toUpperCase();this.text=text;this.attrs=attrs;this.children=[];this.disabled=false;}
  append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
  get innerText(){return this.text||this.children.map(n=>n.innerText).join('\n');}get textContent(){return this.innerText;}get href(){return this.attrs.href;}
  getAttribute(k){return this.attrs[k]??null;}getClientRects(){return [{}];}compareDocumentPosition(){return 4;}
  querySelectorAll(selector){const match=n=>selector.split(',').some(s=>{s=s.trim();if(s==='button[aria-label]')return n.tagName==='BUTTON'&&n.attrs['aria-label'];if(s==='a[href]')return n.tagName==='A'&&n.href;if(s==='button')return n.tagName==='BUTTON';if(s==='a')return n.tagName==='A';if(s==='[role="button"]')return n.attrs.role==='button';if(/^h[1-3]$/.test(s))return n.tagName===s.toUpperCase();if(s==='[role="heading"]')return n.attrs.role==='heading';return false;});return this.children.flatMap(n=>[...(match(n)?[n]:[]),...n.querySelectorAll(selector)]);}
  querySelector(s){return this.querySelectorAll(s)[0]||null;}
 }
 const body=new N('body'),main=new N('main'),pane=new N('div'),heading=new N('h2','More jobs for you');pane.clientHeight=500;pane.clientWidth=400;pane.scrollTop=0;Object.defineProperty(pane,'scrollHeight',{get:()=>pane.children.length*120});
 const next=new N('button','Next'),one=new N('button','1',{'aria-current':'page'}),two=new N('button','2');
 next.click=()=>{page++;pane.scrollTop=0;location.searchParams.set('start',String(page*pageSize));render();};
 function row(i){const title='Research Engineer '+i,company='Lab '+i,place='London (Hybrid)',text=mode==='infinite'?title+'\n'+company+'\n • \n'+place:title+'\n'+company+'\n'+place+'\nPromoted';
  const card=new N(mode==='infinite'?'a':'div',text,mode==='infinite'?{href:'https://www.linkedin.com/jobs/view/'+i+'/'}:{role:'button','aria-label':(i===current?'Selected, ':'')+title});
  if(mode==='pagination'){const dismiss=new N('button','',{'aria-label':'Dismiss '+title+' job'});card.append(dismiss);card.click=()=>{current=i;for(const n of pane.children)n.attrs['aria-label']=n===card?'Selected, '+title:n.text.split('\n')[0];location.searchParams.set('currentJobId',String(i));};}
  return card;
 }
 function render(){pane.children=[];const start=mode==='infinite'?0:page*pageSize,end=mode==='infinite'?count:Math.min(total,start+pageSize);for(let i=start;i<end;i++)pane.append(row(1000+i));next.disabled=end>=total;}
 function grow(){if(mode==='infinite'&&count<total&&pane.scrollTop+pane.clientHeight>=pane.scrollHeight-8){count=Math.min(total,count+10);render();}}
 pane.scrollBy=(x,y)=>{pane.scrollTop=Math.min(pane.scrollHeight-pane.clientHeight,pane.scrollTop+y);grow();};pane.scrollTo=()=>{pane.scrollTop=pane.scrollHeight-pane.clientHeight;grow();};render();main.append(heading,pane,one,two,next);body.append(main);
 const document={body,scrollingElement:pane,querySelector:s=>s==='main,[role="main"]'?main:null,querySelectorAll:s=>body.querySelectorAll(s)};
 const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,location,document,setTimeout:fn=>{queueMicrotask(fn);return 1;},getComputedStyle:n=>({visibility:'visible',overflowY:n===pane?'auto':'visible'})});
 for(const file of ['linkedin-core.js','linkedin-content.js'])vm.runInContext(fs.readFileSync(new URL(file,import.meta.url),'utf8'),c);
 return {handle:c.LinkedInSession.handle,get page(){return page;}};
}
for(const mode of ['pagination','infinite'])test('70+ unique jobs survive '+mode+' traversal without invented IDs',async()=>{
 const f=fixture(mode),found=new Map(),seen=new Set(),p={collection:'more',listing_mode:mode,limit:80};let turns=0;
 while(found.size<80&&turns++<500){const listing=await f.handle('jobs.list',p);for(const item of listing.items)found.set(item.link,item);if(found.size>=80)break;const selected=await f.handle('jobs.select',{...p,seen_keys:[...seen]});if(selected.item){seen.add(selected.key);found.set(selected.item.link,selected.item);continue;}assert.ok(!selected.loading,'card selection must produce a real job ID');const advance=await f.handle('jobs.advance',p);if(advance.paginated)seen.clear();}
 assert.ok(found.size>=80,'expected at least 80 unique jobs');for(const [url,item]of found){const id=Number(url.match(/\/(\d+)\/$/)[1]);assert.equal(item.title,'Research Engineer '+id);assert.equal(item.company,'Lab '+id);assert.equal(item.location,'London (Hybrid)');assert.ok(item.recommendation_sections.includes('more'));}if(mode==='pagination')assert.ok(f.page>=3,'must cross at least four pages');
});
