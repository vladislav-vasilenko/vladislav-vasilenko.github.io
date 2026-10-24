import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import {webcrypto} from 'node:crypto';
const core=fs.readFileSync(new URL('linkedin-core.js',import.meta.url),'utf8'),content=fs.readFileSync(new URL('linkedin-content.js',import.meta.url),'utf8');
const ctx=vm.createContext({URL,crypto:webcrypto,TextEncoder});vm.runInContext(core,ctx);
test('LinkedIn IDs are stable and URL origins cannot escape',()=>{
 assert.equal(ctx.LinkedInCore.url('https://linkedin.com/jobs/search/?currentJobId=123&trackingId=x','job'),'https://www.linkedin.com/jobs/view/123/');assert.equal(ctx.LinkedInCore.url('https://www.linkedin.com/in/tech/en/','profile'),'https://www.linkedin.com/in/tech/');
 for(const url of ['http://www.linkedin.com/in/a/','https://www.linkedin.com.evil.test/in/a/','https://u:p@www.linkedin.com/in/a/','https://www.linkedin.com/in/%2f/'])assert.throws(()=>ctx.LinkedInCore.url(url,'profile'));
});
function formContext({title='Edit intro',two=false,url='https://www.linkedin.com/in/owner/',headline='Original'}={}){
 const node=(tag,type,label,value)=>({tagName:tag,type,labels:[{innerText:label}],value,checked:false,disabled:false,readOnly:false,maxLength:220,getAttribute:()=>null,getClientRects:()=>[{}]});const nodes=[node('INPUT','text','Headline',headline),node('INPUT','password','Password','SECRET'),node('INPUT','file','File','PRIVATE'),node('INPUT','hidden','Session','TOKEN')];
 const dialog={querySelector:()=>({innerText:title}),querySelectorAll:()=>nodes,getClientRects:()=>[{}]};const document={querySelector:()=>null,querySelectorAll:s=>s==='[role="dialog"],dialog[open]'?(two?[dialog,dialog]:[dialog]):[]};
 const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,document,location:new URL(url),getComputedStyle:()=>({visibility:'visible'})});vm.runInContext(core,c);vm.runInContext(content,c);return c;
}
test('editor excludes secrets and refuses ambiguous and messaging forms',async()=>{
 const p={account:'https://www.linkedin.com/in/owner/'};const state=await formContext().LinkedInSession.handle('profile.form',p);assert.equal(state.fields.length,1);assert.equal(state.fields[0].label,'Headline');assert.ok(!JSON.stringify(state).includes('SECRET'));
 for(const options of [{two:true},{title:'New message'},{url:'https://www.linkedin.com/in/somebody/'}])await assert.rejects(()=>formContext(options).LinkedInSession.handle('profile.form',p));
});
test('changed form stops before input',async()=>{
 await assert.rejects(()=>formContext({headline:'Changed'}).LinkedInSession.handle('profile.fill',{account:'https://www.linkedin.com/in/owner/',snapshot:{form_fingerprint:'old'},values:{f0:'new'}}),/изменилась/);
});
test('worker keeps its identity and receipt outside quota-limited chrome.storage',async()=>{
 const memory=new Map(),calls=[],localWrites=[];let resolveClaim;const claimed=new Promise(r=>resolveClaim=r);
 const db={close(){},transaction(){const t={};t.objectStore=()=>({get(key){const r={};queueMicrotask(()=>{r.result=memory.get(key);r.onsuccess?.();t.oncomplete?.();});return r;},put(value,key){memory.set(key,value);const r={};queueMicrotask(()=>{r.onsuccess?.();t.oncomplete?.();});return r;},delete(key){memory.delete(key);const r={};queueMicrotask(()=>{r.onsuccess?.();t.oncomplete?.();});return r;}});return t;}};
 const indexedDB={open(){const r={result:db};queueMicrotask(()=>r.onsuccess?.());return r;}};
 const chrome={permissions:{contains:async()=>true},alarms:{get:async()=>({name:'linkedin-workspace'}),create(){},onAlarm:{addListener(){}}},runtime:{id:'fixture',getManifest:()=>({version:'0.12.0'}),onMessage:{addListener(){}}},storage:{local:{get:async()=>({linkedin_enabled:true}),set:async()=>{localWrites.push(1);throw Error('Resource::kQuotaBytes quota exceeded');}},session:{get:async()=>({}),set:async()=>{throw Error('Resource::kQuotaBytes quota exceeded');}}}};
 const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,chrome,indexedDB,console,queueMicrotask,setTimeout,clearTimeout,LocalResumeService:{request:async(path,data)=>{calls.push(data);resolveClaim();return {command:null};}}});vm.runInContext(fs.readFileSync(new URL('linkedin-worker.js',import.meta.url),'utf8'),c);await claimed;assert.equal(calls[0].op,'claim');assert.match(calls[0].worker_id,/^linkedin-/);assert.equal(localWrites.length,0);assert.equal(memory.get('worker_id'),calls[0].worker_id);
});

test('current profile headline is read from scoped intro without mistaking location or name for headline',()=>{
 const headline='GenAI Research Engineer | Generative Modeling • LLMs • Flow Matching | Product Leader';
 const intro=['Vladislav Vasilenko','He/Him','Verify in 2 minutes',headline,'London Area, United Kingdom','·','Contact info'].join('\n\n');
 assert.equal(ctx.LinkedInCore.introHeadline(intro,'Vladislav Vasilenko'),headline);
 assert.equal(ctx.LinkedInCore.introHeadline('Vladislav Vasilenko\nLondon Area, United Kingdom\nContact info','Vladislav Vasilenko'),'');
 assert.equal(ctx.LinkedInCore.introHeadline(headline+'\nOther Research Engineer','Vladislav Vasilenko'),'');
});

function profileContext({detail=false,noAbout=false,wideSection=true}={}){
 class N{
  constructor(tag,text='',attrs={},children=[]){this.tagName=tag.toUpperCase();this.text=text;this.attrs=attrs;this.children=[];for(const child of children){child.parentElement=this;this.children.push(child);}}
  get innerText(){return [this.text,...this.children.filter(n=>!n.attrs.hidden).map(n=>n.innerText)].filter(Boolean).join('\n');}
  get textContent(){return this.innerText;}get href(){return this.attrs.href;}getAttribute(k){return this.attrs[k]??null;}getClientRects(){return this.attrs.hidden?[]:[{}];}
  contains(n){return this===n||this.children.some(c=>c.contains(n));}
  querySelectorAll(selector){const match=n=>selector.split(',').some(s=>{s=s.trim();if(/^h[1-3]$/.test(s))return n.tagName===s.toUpperCase();if(s==='[role="heading"]')return n.attrs.role==='heading';if(s==='a[href]')return n.tagName==='A'&&!!n.href;if(s==='a[href*="/edit/"]')return n.tagName==='A'&&n.href?.includes('/edit/');if(s==='main'||s==='[role="main"]')return n.tagName==='MAIN';return false;});return this.children.flatMap(n=>[...(match(n)?[n]:[]),...n.querySelectorAll(selector)]);}
  querySelector(s){return this.querySelectorAll(s)[0]||null;}
 }
 const account='https://www.linkedin.com/in/owner/',h=t=>new N('h2',t),a=(text,path)=>new N('a',text,{href:account+path});
 const names={about:'About',experience:'Experience',education:'Education',certifications:'Licenses & certifications',courses:'Courses'};
 const cards=Object.entries(names).filter(([key])=>!detail||key==='experience').filter(([key])=>key!=='about'||!noAbout).map(([key,label])=>new N('div','',{},[new N('div','',{},[h(label),a('Edit '+label,'edit/'+key+'/')]),new N('div',key==='experience'?'Only work experience: Python, training, 2025–2026.':'Only '+key+' content with sufficient text.'),a('Show all '+label,'details/'+key+'/')]));
 const intro=new N('div','',{},[h('Owner Name'),new N('p','Research Engineer | Generative Modeling'),a('Edit profile','edit/intro/')]);
 if(noAbout)intro.children.push(a('Add a summary','edit/forms/summary/new/'));
 // Real regression: one shared <section> contains all cards and footer data.
 const group=new N(wideSection?'section':'div','',{},[...(detail?[]:[intro]),...cards,new N('div','',{},[h('People you may know'),new N('p','UNRELATED CONTACTS AND FOOTER')])]);
 const main=new N('main','',{},[group]),body=new N('body','',{},[main]);
 const document={body,querySelector:s=>body.querySelector(s),querySelectorAll:s=>body.querySelectorAll(s),createElement:tag=>new N(tag)};
 const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,document,location:new URL(account+(detail?'details/experience/':'')),getComputedStyle:()=>({visibility:'visible'})});vm.runInContext(core,c);vm.runInContext(content,c);return {c,account};
}
test('profile sections never capture sibling blocks or shared wrapping section',async()=>{
 const {c,account}=profileContext();const result=await c.LinkedInSession.handle('profile.read',{account});assert.equal(result.extractor_version,3);assert.equal(result.title,'Owner Name');
 for(const [key,s]of Object.entries(result.sections)){assert.ok(s.text.includes(key==='experience'?'Only work experience':'Only '+key));assert.equal(s.coverage,'bounded_section');assert.ok(!s.text.includes('UNRELATED'));for(const other of Object.keys(result.sections).filter(k=>k!==key))assert.ok(!s.text.includes(other==='experience'?'Only work experience':'Only '+other));}
 assert.ok(!result.sections.experience.text.includes('Education'));assert.ok(!result.sections.education.text.includes('certifications'));
});
test('expanded experience is bounded too and rejects an unknown section instead of reading main',async()=>{
 const {c,account}=profileContext({detail:true});const result=await c.LinkedInSession.handle('profile.detail',{account,section:'experience'});assert.equal(result.section,'experience');assert.match(result.text,/Only work experience/);assert.ok(!result.text.includes('UNRELATED'));
 await assert.rejects(()=>c.LinkedInSession.handle('profile.detail',{account,section:'unknown'}),/Неизвестная секция/);
 await assert.rejects(()=>c.LinkedInSession.handle('profile.detail',{account,section:'education'}),/Границы/);
});
test('missing About stays unread and exposes the actual new summary editor URL',async()=>{
 const {c,account}=profileContext({noAbout:true});const result=await c.LinkedInSession.handle('profile.read',{account});assert.equal(result.sections.about.text,'');assert.equal(result.sections.about.coverage,'not_visible');assert.equal(result.about_edit_url,account+'edit/forms/summary/new/');assert.ok(!result.sections.about.text.includes('experience'));
});

test('job card fields preserve company, location and title instead of a whole link label',()=>{
 const fields=ctx.LinkedInCore.cardFields('Senior LLM Engineer (Verified job)\nLab AI • London Area, United Kingdom (Hybrid) • £130K\nMore options\nPromoted · Easy Apply','Senior LLM Engineer (Verified job)');
 assert.equal(fields.title,'Senior LLM Engineer');assert.equal(fields.company,'Lab AI');assert.equal(fields.location,'London Area, United Kingdom (Hybrid)');assert.equal(fields.locations.length,1);
 const fullLine=ctx.LinkedInCore.cardFields('Senior LLM Engineer Lab AI • London (Hybrid) More options Dismiss role job','Senior LLM Engineer');assert.equal(fullLine.company,'Lab AI');assert.equal(fullLine.location,'London (Hybrid)');
});
test('recommended-search URL keeps criteria and drops tracking without changing a job identity',()=>{
 const url=ctx.LinkedInCore.url('https://www.linkedin.com/jobs/search-results/?keywords=Senior+LLM+Engineer&geoId=90009496&originToLandingJobPostings=123%2C456&lipi=tracking');assert.match(url,/keywords=Senior\+LLM\+Engineer/);assert.match(url,/originToLandingJobPostings=123%2C456/);assert.ok(!url.includes('lipi='));
 assert.equal(ctx.LinkedInCore.url(url+'&currentJobId=123','job'),'https://www.linkedin.com/jobs/view/123/');
});
test('experience navigation groups unique entries and removes repeated empty media and skills links',()=>{
 const base='https://www.linkedin.com/in/owner/';const result=ctx.LinkedInCore.profileLinks([{label:'Research Engineer\n\nAI Lab\n\n2025 – Present',url:base+'edit/forms/position/123/'},{label:'',url:base+'overlay/Position/123/treasury/'},{label:'',url:base+'overlay/Position/123/treasury/'},{label:'PyTorch and +18 skills',url:base+'overlay/123/skill-associations-details/'},{label:'',url:base+'details/experience/'},{label:'Show all',url:base+'details/experience/'},{label:'External',url:'https://evil.example/'},{label:'Another profile',url:'https://www.linkedin.com/in/another/details/experience/'}],base);
 assert.equal(result.entries.length,1);assert.equal(result.entries[0].label,'Research Engineer');assert.equal(result.entries[0].meta,'AI Lab · 2025 – Present');assert.equal(result.sections.length,1);assert.ok(!JSON.stringify(result).includes('treasury'));assert.ok(!JSON.stringify(result).includes('18 skills'));
});

test('new LinkedIn card separates standalone bullets and visible job signals',()=>{
 const f=ctx.LinkedInCore.cardFields('Lead AI Engineer (Verified job)\nLead AI Engineer\nKi\n • \nLondon (Hybrid)\nActively reviewing applicants\nViewed · Easy Apply · Promoted','Lead AI Engineer');assert.equal(f.company,'Ki');assert.equal(f.location,'London (Hybrid)');
 const s=ctx.LinkedInCore.jobSignals('Viewed · Be an early applicant · Promoted\n18 school alumni work here\nActively reviewing applicants');assert.equal(s.viewed,true);assert.equal(s.school_alumni_count,18);assert.equal(s.actively_reviewing,true);assert.equal(ctx.LinkedInCore.jobSignals('Employer viewed application').viewed,undefined);
});
test('job header keeps relative publication and applicant lower bound without inventing exact date',()=>{
 const s=ctx.LinkedInCore.jobHeader('Senior AI Engineer\nLondon Area, United Kingdom · 1 month ago · Over 100 applicants\n80K GBP/yr - 110K GBP/yr\nHybrid\nFull-time');assert.equal(s.location,'London Area, United Kingdom');assert.equal(s.posted_label,'1 month ago');assert.equal(s.applicants_count,100);assert.equal(s.applicants_lower_bound,true);assert.equal(s.work_format_label,'Hybrid');assert.equal(s.employment_label,'Full-time');assert.ok(!s.pub_date);
});

test('Apply resolves only an observed HTTPS ATS destination, including LinkedIn safety wrapper',()=>{assert.equal(ctx.LinkedInCore.applyTarget('https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.example%2Frole%3Fid%3D123&urlhash=secret'),'https://jobs.example/role?id=123');for(const u of ['javascript:alert(1)','https://user:pass@jobs.example/','https://www.linkedin.com/jobs/view/123/','https://www.linkedin.com/safety/go/?url=http%3A%2F%2Flocalhost%2F'])assert.equal(ctx.LinkedInCore.applyTarget(u),'');});
test('recommendation collection is independent of infinite-scroll or pagination presentation',()=>{assert.equal(ctx.LinkedInCore.recommendationSource('https://www.linkedin.com/jobs/search-results/?origin=INFINITE_JOBS_LANDING'),'more');assert.equal(ctx.LinkedInCore.recommendationSource('https://www.linkedin.com/jobs/search-results/?origin=QUALIFICATION_LANDING'),'profile');assert.equal(ctx.LinkedInCore.recommendationSource('https://www.linkedin.com/jobs/search-results/?origin=JobSearchOrigin_QUALIFICATION_LANDING'),'profile');});

test('pagination supports Next and numbered fallback without clicking disabled controls',async()=>{
 const make=(label,attrs={})=>({tagName:'BUTTON',disabled:false,clicked:0,innerText:label,getAttribute:k=>attrs[k]||null,getClientRects:()=>[{}],click(){this.clicked++;}}),one=make('1',{'aria-current':'page'}),two=make('2'),next=make('Next');
 const scrolling={scrollTop:0,clientHeight:600,scrollHeight:600,tagName:'HTML',scrollTo(){}};const main={querySelectorAll:s=>s==='button,a,[role="button"]'?[one,two,next]:[]};
 const document={body:{},scrollingElement:scrolling,querySelector:s=>s==='main,[role="main"]'?main:null,querySelectorAll:()=>[]};const c=vm.createContext({URL,crypto:webcrypto,TextEncoder,document,location:new URL('https://www.linkedin.com/jobs/search-results/'),getComputedStyle:()=>({visibility:'visible'})});vm.runInContext(core,c);vm.runInContext(content,c);
 let r=await c.LinkedInSession.handle('jobs.advance',{});assert.equal(r.paginated,true);assert.equal(next.clicked,1);next.disabled=true;r=await c.LinkedInSession.handle('jobs.advance',{});assert.equal(r.page,2);assert.equal(two.clicked,1);
});
test('real Base64 conversation IDs with padding are accepted without accepting path escapes',()=>{for(const u of ['https://www.linkedin.com/messaging/thread/2-example==/','https://www.linkedin.com/messaging/thread/2-example%3D%3D/'])assert.equal(ctx.LinkedInCore.url(u,'thread'),'https://www.linkedin.com/messaging/thread/2-example==/');for(const u of ['https://www.linkedin.com/messaging/thread/a%2Fb/','https://www.linkedin.com/messaging/thread/a===/'])assert.throws(()=>ctx.LinkedInCore.url(u,'thread'));});

test('session gate ignores hidden sign-in fields and tiny captcha badges, stops on a visible challenge',async()=>{
 const main={querySelectorAll:()=>[]},hidden={getClientRects:()=>[],clientWidth:300,clientHeight:200},badge={getClientRects:()=>[{}],clientWidth:70,clientHeight:70},challenge={getClientRects:()=>[{}],clientWidth:320,clientHeight:220};let blockers=[hidden,badge];
 const document={body:{},querySelector:s=>s==='main,[role="main"]'?main:null,querySelectorAll:s=>s==='input[type="password"]'?[blockers[0]]:s==='iframe[src*="captcha"]'?[blockers[1]]:[]};const c=vm.createContext({URL,document,location:new URL('https://www.linkedin.com/messaging/'),getComputedStyle:()=>({visibility:'visible'})});vm.runInContext(core,c);vm.runInContext(content,c);
 const result=await c.LinkedInSession.handle('network.list',{limit:10});assert.equal(result.items.length,0);blockers=[hidden,challenge];await assert.rejects(c.LinkedInSession.handle('network.list',{limit:10}),/ручную проверку/);
});

test('Unicode profile URLs keep canonical UTF-8 while encoded slashes and traversal are rejected',()=>{
 for(const name of ['иван-петров','研究-engineer','élise-dupont']){const url='https://www.linkedin.com/in/'+encodeURIComponent(name)+'/';assert.equal(ctx.LinkedInCore.url(url,'profile'),url);}
 for(const slug of ['%2e%2e','ivan%2fadmin','ivan%5cadmin','%252fadmin'])assert.throws(()=>ctx.LinkedInCore.url('https://www.linkedin.com/in/'+slug+'/','profile'));
});
