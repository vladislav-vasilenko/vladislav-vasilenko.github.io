import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import '../vacancy-document.js';

test('vacancy Markdown keeps headings, lists, ordered start, code and paragraphs separate',()=>{
 const p=VacancyDocument.parse('## Команда\n\nОписание проекта.\n\n**Требования:**\n- Python\n- **PyTorch**\n\nУсловия\n3. Первая встреча\n4. Вторая встреча\n\n```\n<script>literal</script>\n```');
 assert.deepEqual(p.blocks.map(b=>b.type),['heading','paragraph','heading','list','heading','list','code']);
 assert.deepEqual(p.blocks[3].items,['Python','**PyTorch**']);assert.equal(p.blocks[5].start,3);assert.equal(p.inferred,false);
});
test('legacy flat capture separates only explicit named sections without inventing bullets or changing words',()=>{
 const text='Мы разрабатываем генеративные модели. Технологический стек Основной стек: Python, PyTorch. Обязанности Разрабатывать модели. Требования Опыт обучения моделей. Условия Гибрид.';
 const p=VacancyDocument.parse(text);assert.equal(p.inferred,true);assert.deepEqual(p.blocks.filter(b=>b.type==='heading').map(b=>b.text),['Технологический стек','Основной стек','Обязанности','Требования','Условия']);assert.ok(!p.blocks.some(b=>b.type==='list'));
 assert.equal(p.blocks.filter(b=>b.type==='paragraph').map(b=>b.text).join(' '),'Мы разрабатываем генеративные модели. Python, PyTorch. Разрабатывать модели. Опыт обучения моделей. Гибрид.');
 assert.deepEqual(VacancyDocument.parse('Обсуждаем требования к проекту и условия работы.').blocks,[{type:'paragraph',text:'Обсуждаем требования к проекту и условия работы.'}]);
});
test('unknown prose, duplicate sections and snippets are retained rather than silently edited',()=>{
 for(const text of ['No recognized structure.','Стек: Python\n\nСтек: Python','Необходимы\nзнания Python']){const p=VacancyDocument.parse(text);assert.equal(p.inferred,false);assert.equal(p.blocks.map(b=>b.text).join('\n\n'),text);}
});

class E{
 constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.textContent='';}
 append(...items){this.children.push(...items);}prepend(...items){this.children.unshift(...items);}setAttribute(k,v){this.attributes[k]=v;}
}
function rendered(description){const context=vm.createContext({URL,document:{createElement:t=>new E(t),createTextNode:text=>({tag:'#text',textContent:text})}});vm.runInContext(fs.readFileSync(new URL('../vacancy-document.js',import.meta.url),'utf8'),context);const root=new E('details'),data={text:'Original\n'+description,payload:{description}};context.VacancyDocument.render(root,data);return {root,data};}
const walk=n=>[n,...(n.children||[]).flatMap(walk)];
test('hostile HTML stays text, only HTTP(S) links activate and the exact source toggles back',()=>{
 const {root,data}=rendered('## Требования\n- **PyTorch** и `CUDA`\n\n<script>alert(1)</script>\n\n[x](javascript:alert) [safe](https://example.org/job)');
 const nodes=walk(root);assert.ok(!nodes.some(n=>n.tag==='script'));assert.equal(nodes.filter(n=>n.tag==='a').length,1);assert.equal(nodes.find(n=>n.tag==='a').rel,'noopener noreferrer');assert.equal(nodes.find(n=>n.tag==='strong').textContent,'PyTorch');
 const raw=nodes.find(n=>n.className==='vacancyRaw'),body=nodes.find(n=>n.tag==='article');assert.equal(raw.textContent,data.text);assert.equal(raw.hidden,true);nodes.find(n=>n.textContent==='Исходный текст').onclick();assert.equal(raw.hidden,false);assert.equal(body.hidden,true);nodes.find(n=>n.textContent==='Читаемый вид').onclick();assert.equal(raw.hidden,true);assert.equal(body.hidden,false);
});
test('empty description is labelled while the source remains accessible',()=>{const {root}=rendered('');assert.ok(walk(root).some(n=>n.textContent==='Описание ещё не сохранено.'));});
