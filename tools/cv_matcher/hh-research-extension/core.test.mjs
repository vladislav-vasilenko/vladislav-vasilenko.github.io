import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import "./core.js";

const profile = JSON.parse(fs.readFileSync(new URL("./search-profile.json", import.meta.url), "utf8"));
const {buildUrl, buildQuery, mergeVacancies} = globalThis.ResearchSearch;

test("Moscow and remote are independent searches, with no salary or experience restriction", () => {
  for (const location of profile.locations) {
    const url = new URL(buildUrl(profile, {tier: "top", track: "diffusion", location: location.id}));
    assert.equal(url.searchParams.get("area"), location.params.area);
    assert.equal(url.searchParams.get("work_format"), location.params.work_format || null);
    assert.equal(url.searchParams.get("salary"), null);
    assert.equal(url.searchParams.get("experience"), null);
    assert.equal(url.searchParams.get("search_period"), null);
    assert.equal(url.hostname, "hh.ru");
  }
});

test("all company / topic combinations produce scoped, unique queries", () => {
  const ids = profile.companies.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length);
  const urls = new Set();
  for (const company of profile.companies) {
    assert.ok(profile.tier_labels[company.tier]);
    for (const track of profile.tracks) for (const location of profile.locations) {
      const options = {company: company.id, track: track.id, location: location.id};
      assert.ok(buildQuery(profile, options).includes(`"${company.aliases[0]}"`));
      const url = buildUrl(profile, options);
      assert.ok(!urls.has(url)); urls.add(url);
    }
  }
  assert.equal(urls.size, profile.companies.length * profile.tracks.length * profile.locations.length);
  assert.throws(() => buildUrl(profile, {company: "unknown", track: "diffusion", location: "moscow"}));
});

test("daily overlap is explicit and broad first search does not exclude research descriptions", () => {
  const options = {tier: "top", track: "broad", location: "remote", daily: true};
  assert.equal(new URL(buildUrl(profile, options)).searchParams.get("search_period"), "3");
  assert.ok(buildQuery(profile, options).includes('NAME:'));
  for (const track of profile.tracks) assert.ok(!/NOT\s+(RAG|API|inference)/i.test(track.query));
  assert.equal(profile.sources.hh_public_api, false);
});

test("complete JD replaces snippet, later snippet preserves complete JD, duplicate ID stays single", () => {
  const snippet = {id: "hh_123", link: "https://hh.ru/vacancy/123", description: "short", description_quality: "snippet", collected_at: "2026-10-14T08:00:00Z"};
  const full = {...snippet, description: "full requirements", description_quality: "full", collected_at: "2026-10-14T09:00:00Z"};
  let rows = mergeVacancies([], [snippet]);
  rows = mergeVacancies(rows, [full]);
  rows = mergeVacancies(rows, [{...snippet, collected_at: "2026-10-14T10:00:00Z"}]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].description, "full requirements");
  assert.equal(rows[0].first_seen, snippet.collected_at);
  assert.equal(rows[0].last_seen_at, "2026-10-14T10:00:00Z");
  assert.equal(mergeVacancies(rows, [{id: "bad-id"}]).length, 1);
});
test('HH recommendations retain resume membership when a full JD is reused or shared by two CVs',()=>{
 const a='a'.repeat(38),b='b'.repeat(38),url=ResearchSearch.recommendationUrl(a);
 assert.equal(new URL(url).searchParams.get('resume'),a);
 for(const invalid of ['file_'+'a'.repeat(64),'google_doc_123','a'.repeat(37),'a'.repeat(38)+'&text=Java'])assert.throws(()=>ResearchSearch.recommendationUrl(invalid));
 const full={id:'hh_123',link:'https://hh.ru/vacancy/123',description:'full text',description_quality:'full',collected_at:new Date().toISOString()};
 let rows=ResearchSearch.mergeVacancies([full],ResearchSearch.markSearchSource([{...full,description:'snippet',description_quality:'snippet'}],url));
 rows=ResearchSearch.mergeVacancies(rows,ResearchSearch.markSearchSource([{...full,description:'other snippet',description_quality:'snippet'}],ResearchSearch.recommendationUrl(b)));
 assert.equal(rows[0].description,'full text');assert.deepEqual(rows[0].recommended_for,[a,b]);
 assert.equal(ResearchSearch.recommendationResume('https://evil.test/search/vacancy?resume='+a),null);
});

const captureSource = fs.readFileSync(new URL("./content.js", import.meta.url), "utf8");
function capture({url, title = "", description = "", company = "", hidden = false, archived = false, archiveHidden = false, rejectDescriptionRead = false}) {
  const element = (innerText,isHidden=hidden) => ({innerText, hidden:isHidden, getBoundingClientRect: () => ({width: 100, height: 20})});
  const document = {querySelector: () => null, querySelectorAll: (selector) => {
    if (selector.includes("vacancy-archive-message")) return archived ? [element("Вакансия в архиве",archiveHidden)] : [];
    if (selector.includes("vacancy-description")) {if(rejectDescriptionRead)throw Error("Closed JD must not be read");return description ? [element(description)] : [];}
    if (selector.includes("vacancy-title")) return title ? [element(title)] : [];
    if (selector.includes("vacancy-company-name")) return company ? [element(company)] : [];
    return [];
  }};
  return vm.runInNewContext(captureSource, {document, location: new URL(url), URL, Date,
    getComputedStyle: (el) => ({display: el.hidden ? "none" : "block", visibility: "visible"})});
}

test("full page capture preserves long JD, normalizes URL, and labels missing descriptions", () => {
  const full = capture({url: "https://hh.ru/vacancy/123?hhtmFrom=search", title: "Research Engineer", company: "Яндекс", description: "x".repeat(9000)});
  assert.equal(full.vacancies[0].description.length, 9000);
  assert.equal(full.vacancies[0].link, "https://hh.ru/vacancy/123");
  assert.equal(full.vacancies[0].description_quality, "full");
  const missing = capture({url: "https://hh.ru/vacancy/123", title: "Research Engineer"});
  assert.equal(missing.vacancies[0].description_quality, "missing");
  assert.ok(missing.warning);
});

test("capture ignores unrelated pages, third-party vacancy URLs, and hidden content", () => {
  for (const url of ["https://hh.ru/resume/123", "https://example.com/vacancy/123"]) {
    assert.equal(capture({url, title: "Private content", description: "private"}).vacancies.length, 0);
  }
  assert.equal(capture({url: "https://hh.ru/vacancy/123", title: "Hidden", hidden: true}).vacancies.length, 0);
  const manifest = JSON.parse(fs.readFileSync(new URL("./manifest.json", import.meta.url), "utf8"));
  assert.deepEqual(manifest.permissions, ["activeTab", "scripting", "storage", "alarms"]);
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.background.service_worker, "background.js");
});

test('HH full descriptions preserve paragraph boundaries for the archive reading view',()=>{
 const full=capture({url:'https://hh.ru/vacancy/123',title:'ML Engineer',description:'О команде\n\nМы обучаем модели.\n\nТребования\nPython\nPyTorch'});
 assert.equal(full.vacancies[0].description,'О команде\n\nМы обучаем модели.\n\nТребования\nPython\nPyTorch');
});
test('HH description DOM preserves heading and bullet boundaries and excludes hidden or form text',()=>{
 const text=textContent=>({nodeType:3,textContent});
 const el=(tagName,childNodes,hidden=false)=>({nodeType:1,tagName,childNodes,hidden,innerText:'rendered',getBoundingClientRect:()=>({width:100,height:50})});
 const description=el('DIV',[el('H2',[text('Требования')]),el('UL',[el('LI',[text('Python')]),el('LI',[text('PyTorch')])]),el('P',[text('Полное описание.')]),el('P',[text('Hidden')],true),el('FORM',[text('Private answers')])]);
 const document={querySelector:()=>null,querySelectorAll:selector=>selector.includes('vacancy-description')?[description]:selector.includes('vacancy-title')?[{innerText:'Role',getBoundingClientRect:()=>({width:100,height:50})}]:[]};
 const result=vm.runInNewContext(captureSource,{document,location:new URL('https://hh.ru/vacancy/123'),URL,Date,getComputedStyle:el=>({display:el.hidden?'none':'block',visibility:'visible'})});
 assert.equal(result.vacancies[0].description,'## Требования\n\n- Python\n- PyTorch\n\nПолное описание.');
});


test('a visible archive notice stops description extraction; hidden archive placeholders do not close a vacancy',()=>{
 const closed=capture({url:'https://hh.ru/vacancy/123',title:'ML role',archived:true,description:'Obsolete full description',rejectDescriptionRead:true});
 assert.equal(closed.vacancies[0].archived,true);assert.equal(closed.vacancies[0].description,'');assert.equal(closed.vacancies[0].description_quality,'missing');assert.match(closed.warning,/архиве/);
 const active=capture({url:'https://hh.ru/vacancy/123',title:'ML role',archived:true,archiveHidden:true,description:'Current complete description'});
 assert.equal(active.vacancies[0].archived,false);assert.equal(active.vacancies[0].description_quality,'full');
});


test('detail cache expires at 24 hours, never accepts empty, closed, future or dirty full records',()=>{
 const now=Date.parse('2026-10-19T12:00:00Z'),row={description_quality:'full',description:'Saved full description',collected_at:new Date(now-23*3600000).toISOString()};
 assert.equal(ResearchSearch.detailFresh(row,{now}),true);
 for(const patch of [{collected_at:new Date(now-24*3600000).toISOString()},{collected_at:new Date(now+1000).toISOString()},{collected_at:'invalid'},{description:''},{description_quality:'needs_review'},{archived:true},{availability:'closed'},{description_dirty:true}])assert.equal(ResearchSearch.detailFresh({...row,...patch},{now}),false);
 assert.equal(ResearchSearch.detailFresh(row,{now,force:true}),false);
});
test('listing updates preserve full-text age and invalidate on changed listing signals',()=>{
 const full={id:'hh_1',link:'https://hh.ru/vacancy/1',title:'ML Engineer',company:'Company',description:'Full text',description_quality:'full',collected_at:'2026-10-18T10:00:00Z'};
 const listing={...full,description:'Short original snippet',description_quality:'snippet',collected_at:'2026-10-19T11:00:00Z'};
 const [seen]=ResearchSearch.mergeVacancies([full],[listing]);assert.equal(seen.description_fetched_at,full.collected_at);assert.equal(seen.collected_at,full.collected_at);assert.equal(seen.last_seen_at,listing.collected_at);assert.equal(seen.description,'Full text');
 const [changed]=ResearchSearch.mergeVacancies([seen],[{...listing,description:'New requirements'}]);assert.equal(changed.description_dirty,true);assert.equal(ResearchSearch.detailFresh(changed),false);
 const [updated]=ResearchSearch.mergeVacancies([changed],[{...full,description:'Updated full text',collected_at:listing.collected_at,listing_snapshot:ResearchSearch.listingStamp(listing)}]);assert.equal(updated.description_dirty,false);assert.equal(updated.description_fetched_at,listing.collected_at);
});

test('a public HH login button is not a blocked vacancy and hidden challenge placeholders are ignored',()=>{
 const element={innerText:'Войти',hidden:false,getBoundingClientRect:()=>({width:30,height:20})};
 const doc={querySelector:selector=>selector.includes('account-login')?element:null,querySelectorAll:selector=>selector.includes('vacancy-title')?[{...element,innerText:'Research'}]:selector.includes('vacancy-description')?[{...element,innerText:'Complete research description'}]:[]};
 const result=vm.runInNewContext(captureSource,{document:doc,location:new URL('https://hh.ru/vacancy/123'),URL,Date,getComputedStyle:()=>({display:'block',visibility:'visible'})});
 assert.equal(result.blocked,undefined);assert.equal(result.vacancies[0].description_quality,'full');
});
test('unknown HH markup is distinct from a verified empty search and includes adapter diagnostics',()=>{
 const result=vm.runInNewContext(captureSource,{document:{querySelector:()=>null,querySelectorAll:()=>[]},location:new URL('https://hh.ru/search/vacancy?text=ML'),URL,Date,Map,getComputedStyle:()=>({display:'block',visibility:'visible'})});
 assert.equal(result.empty,false);assert.equal(result.layout_unknown,true);assert.equal(result.diagnostics.adapter_version,'hh-dom-v2');
});
