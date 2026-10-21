#!/usr/bin/env node
// Generates a read-only search plan and clickable HH links, without network calls.
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import "../hh-research-extension/core.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const profile = JSON.parse(fs.readFileSync(path.join(root, "hh-research-extension/search-profile.json"), "utf8"));
const daily = process.argv.includes("--daily");
const helper = globalThis.ResearchSearch;
const plan = [];
for (const company of profile.companies) {
  for (const track of profile.tracks) {
    for (const location of profile.locations) {
      const options = {company: company.id, track: track.id, location: location.id, daily};
      plan.push({company_id: company.id, company: company.label, search_tier: company.tier,
        scope: company.scope, track: track.id, location: location.id,
        query: helper.buildQuery(profile, options), url: helper.buildUrl(profile, options)});
    }
  }
}
const lines = [
  "# Поиск Research Engineer ML",
  "",
  "Профиль: Generative Modelling / DiT / Transformer pre-train и post-train.",
  "",
  "Условия: Москва — любой формат; либо удалённая работа по России. Зарплата и стаж без ограничения. Это два отдельных поиска, результаты которых нужно объединять по ID вакансии.",
  "",
  `Период: ${daily ? "последние 3 дня — ежедневный поиск с перекрытием" : "без ограничения даты — первый полный поиск"}.`,
  "",
  "Основные источники — карьерные сайты и страницы лабораторий. HH используется через открытые браузерные страницы и расширение Chrome; публичный HH API и headhunter-mcp-server не используются.",
  "",
  "## Поиск по уровням и направлениям", ""
];
for (const [tier, label] of Object.entries(profile.tier_labels)) {
  lines.push(`### ${label}`, "", "| Направление | Москва | Удалённо |", "|---|---|---|");
  for (const track of profile.tracks) {
    const links = profile.locations.map((location) => {
      const url = helper.buildUrl(profile, {tier, track: track.id, location: location.id, daily});
      return `[Открыть поиск](${url})`;
    });
    lines.push(`| ${track.label} | ${links.join(" | ")} |`);
  }
  lines.push("");
}
lines.push("## Компании и лаборатории", "", "Общий поиск уровня проверяет имя работодателя. Вакансии партнёрских лабораторий могут публиковаться под другим юридическим лицом; их стоит собирать с карьерных страниц лабораторий отдельно.", "",
  "| Компания / лаборатория | Уровень поиска | Область применения приоритета | Москва | Удалённо |", "|---|---|---|---|---|");
for (const company of profile.companies) {
  const links = profile.locations.map((location) => `[Поиск](${helper.buildUrl(profile,
    {company: company.id, track: "broad", location: location.id, daily})})`);
  lines.push(`| ${company.label} | ${profile.tier_labels[company.tier]} | ${company.scope} | ${links.join(" | ")} |`);
}
lines.push("", "## Правила отбора", "", profile.ranking_policy, "",
  "Классификация компании в поиске — предварительная. Проверять фактического работодателя, исследовательскую команду, полное описание, место работы и ограничения удалённой работы.", "",
  "Высший приоритет роли: DiT, diffusion/flow matching, обучение генеративных image/video/audio моделей, Transformer pre-training, continual pre-training, SFT, DPO/RLHF/GRPO, исследования архитектур.", "",
  "Дополнительный приоритет: исследовательские задачи по distributed training, дистилляции и эффективности моделей. Роли преимущественно по интеграции готовых моделей, RAG или разработке агентов без обучения моделей оцениваются ниже.", "",
  "Не исключать слова RAG, inference и API из полного текста: они могут встречаться в релевантной исследовательской вакансии.", "",
  "Перед сравнением с резюме использовать только полный текст (`description_quality=full`), а не сокращённую карточку выдачи. Исключать архивные вакансии и уже отправленные отклики по собственной истории.", "",
  "## Использование расширения", "",
  "Инструкция: [hh-research-extension/README.md](../hh-research-extension/README.md). Сохранённые вакансии экспортируются локально в JSON, совместимый с viewer CV Matcher.", "",
  "Генерация ссылок не выполняет поиск в сети, сбор вакансий или ежедневное расписание. Текущий список вакансий и работа веб-фильтров требуют проверки в открытой сессии HH.", "",
  "Язык запросов: [официальная справка HH](https://hh.ru/article/1175).", ""
);
const docs = path.join(root, "docs");
const cache = path.join(root, ".cache");
fs.mkdirSync(docs, {recursive: true}); fs.mkdirSync(cache, {recursive: true});
const suffix = daily ? "_daily" : "";
fs.writeFileSync(path.join(docs, `research_search${suffix}.md`), lines.join("\n"));
fs.writeFileSync(path.join(cache, `research_search_plan${suffix}.json`), JSON.stringify({
  schema_version: 1, daily, target: profile.daily_target, filters: profile.locations,
  ranking_policy: profile.ranking_policy, searches: plan
}, null, 2));
console.log(`Сформировано ${plan.length} вариантов поиска для ${profile.companies.length} компаний. Отчёт: docs/research_search${suffix}.md`);
if (!daily) {
  const company=profile.companies.find(c=>c.id==="huawei");
  if(company) {
    const h=["# Huawei R&D Russia — поиск для соискателя", "", "Уровень: Top-Tier. Москва или удалённая работа по России; зарплата без ограничения.", "",
      `[Официальный портал российских R&D-центров](${company.career_url}) — содержит описания направлений; актуальность конкретного набора нужно подтвердить отдельно.`, "",
      "Начать с широкого поиска, затем проверить LLM / мультимодальные модели и обучение. Для текущего резюме также интересны NLP/speech, генеративное аудио и эффективность Transformer.", "",
      "| Направление | Москва | Удалённо |", "|---|---|---|"];
    for(const track of [...profile.tracks].sort((a,b)=>(a.id==="broad"?-1:b.id==="broad"?1:0))) {
      h.push(`| ${track.label} | ${profile.locations.map(location=>`[Открыть](${helper.buildUrl(profile,{company:company.id,track:track.id,location:location.id,daily:false})})`).join(" | ")} |`);
    }
    const aliases=company.aliases.map(a=>`"${a}"`).join(" OR ");
    const params=new URLSearchParams({text:`COMPANY_NAME:(${aliases}) AND (LLM OR Transformer OR NLP OR "Deep Learning" OR diffusion OR "speech synthesis" OR TTS OR ASR)`,area:"1",order_by:"publication_time"});
    h.push("",`[Дополнительный поиск по тексту без ограничения названия должности](https://hh.ru/search/vacancy?${params})`,"",
      "Поисковые ссылки — подготовленные запросы, не подтверждённый список открытых вакансий. Проверять работодателя, команду, географию и фактические задачи. Собирать полные карточки HH через кнопку расширения; портал RRI пока используется для ориентации по направлениям.","",
      "Порядок работы: каталог HH → загрузка основного CV → поиск/сбор полных вакансий → два экспорта → анализ → решение об откликах. Инструкция: [applicant_quickstart.md](applicant_quickstart.md).","");
    fs.writeFileSync(path.join(docs,"huawei_search.md"),h.join("\n"));
  }
}
