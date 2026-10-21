# Resume document comparison and workspace reading

Updated: 2026-10-20. These views use saved local data. They do not invoke paid models or send applications.

## Resume comparison

Entry: `?view=resume&compare=chunks`. In **Резюме → Сравнить резюме**, choose 2–7 saved snapshots, including different historical snapshots of the same CV. The explicit **Аллювиальная диаграмма · чанки** button opens the document view; **Сравнить опыт и разделы** retains block matching.

Implementation:

- [`resume-compare-core.js`](../../archive-web/resume-compare-core.js): block extraction, paragraph/bullet chunking, conservative unique matching, lexical similarity, stable section palette, word diff.
- [`resume-compare.js`](../../archive-web/resume-compare.js): snapshot selectors, document preview, compact graph, alluvial ribbons anchored to actual paragraph geometry, focus, inspector, zoom/fullscreen and deep link.
- [`resume-profile-core.js`](../../archive-web/resume-profile-core.js): existing employment parsing with raw source fragments.
- [`archive_store.py`](../../src/archive_store.py): `resume_snapshot`; [`archive_routes.py`](../../src/archive_routes.py): historical entity snapshot lookup scoped to both resume and version.

The default chunk presentation is **Документы + потоки текста**: full paragraph text in original order, section/company/role/date context, Markdown headings/lists/inline formatting. The compact scheme is an additional presentation. A ribbon connects paragraphs, with endpoint heights reflecting their rendered text extent; its size is not employment duration or importance. The palette can encode individual fragment chains, sections/roles, or comparison status. Colors remain consistent along each chain across snapshots. An alternate palette encodes comparison status. Hover/click isolates a chain; the inspector compares relative to a selected base, with additions in the target and deletions in a separate disclosure.

Exact matches use normalized text. Optional approximate matches require at least eight distinct words on each side, six shared words, and Jaccard similarity ≥0.62. Matching must be unique on both sides. No translation, semantic identity or employment equivalence is inferred. Different employment dates remain visible. Unlinked text means correspondence was not established, not necessarily that the underlying experience is absent. Contact sections are excluded. User supplements outside snapshots are not silently merged into source text.

Document mode supports up to 1,000 chunks per snapshot; compact mode initially shows 140 matching chunks. A truncation notice is explicit. Search in document mode dims unmatched paragraphs while retaining context; compact search filters before the cap. Zoom preserves the geometry of ribbons, and native two-finger scrolling moves the canvas. Historical snapshots are immutable; comparison does not edit resumes or profile selection.

## Vacancy reading and skill priorities

[`archive.js`](../../archive-web/archive.js) organizes vacancy detail into **Описание**, **Соответствие CV**, and **Источники и версии**. Reading is the initial tab. Source provenance and duplicate preparation controls no longer precede the description. The vacancy list and global navigation can be hidden independently; preferences are local UI state only.

[`vacancy-document.js`](../../archive-web/vacancy-document.js) renders safe DOM from captured structure or Markdown, retaining raw source access. Highlighting uses [`vacancy_terms.py`](../../src/vacancy_terms.py) and the selected CV: a mention is not proof of competence.

The description includes **Навыки для этой вакансии**. It calls `skills_vacancy` through [`agent_routes.py`](../../src/agent_routes.py) → `CareerApplication.skills_vacancy` → [`career_skills.vacancy_plan`](../../src/career_skills.py). The shared priority engine reuses local requirement extraction, cached Luna and candidate evidence. It works without an embedding ranking for an explicitly selected complete vacancy, returns API count zero, and does not overwrite the saved multi-vacancy map selection. Unsupported requirements remain visible for manual checking. Actions distinguish validation, learning, practice, CV documentation and publication. Resource prerequisites remain explicit.

The link to **Навыки и обучение** carries `skills_vacancy` and `resume_id` into the analytics adapter, where that explicit vacancy can be analyzed with the same engine.

## Document sources and application preparation

[`resume_documents.py`](../../src/resume_documents.py) and [`resume-sources.js`](../../archive-web/resume-sources.js) support reviewed import from Google Docs or TXT/MD/DOC/DOCX/PDF. Extraction produces an expiring preview; an explicit review saves a snapshot. The primary CV is not switched automatically. Google Docs uses the existing extension permission and command queue, requires an accessible export and extension version 0.11.19 or later. Scanned PDFs may require OCR; legacy DOC conversion depends on the platform converter. Private Google Docs import was not exercised in the live QA session.

[`application_readiness.py`](../../src/application_readiness.py) reports stale context/activity without weakening final transfer checks. [`workflow.js`](../../archive-web/workflow.js) exposes source → fit → letter → form → approval steps. Read-only `career_open` opens/inspects a company form; it is separate from one-use approved filling. An installed extension must be reloaded to consume new commands. Real personal-data filling and submission were not exercised during this QA session.

## Validation

- Isolated backend suite: 385 tests passed, including explicit-vacancy priorities without ranking and preservation of map selection.
- Extension/web suite: 344 tests passed. It includes chunk reorder matching, conservative similarity, visible limits, complete document chunks, immutable snapshots and stable palettes.
- Live local-browser checks: full document text and measured ribbon paths, selected vacancy term highlights, per-vacancy skill priorities, independent list/menu hiding, and detail tabs. No paid requests or actual applications.

## Offline discussion export

The diagram toolbar has **Скопировать связи для LLM · без API**. The user chooses the focused chain or all visible nodes/links. The export includes source resume IDs/titles, immutable snapshot IDs and capture dates, node-to-source ownership, employment context, match kinds, date differences and exact quoted text. Identical text is deduplicated by `text_ref`, without merging node provenance. Current-source/local-view links are explicitly distinguished from historical snapshot references. Local URLs are documented as unavailable to an external LLM.

`ResumeCompareCore.prompt` generates this packet without API access. The UI exposes a read-only preview and character count, copies through the clipboard, and falls back to manual copy. Packets over 240,000 characters are rejected with narrowing instructions; they are not silently truncated. Embedded resume content is delimited as data, with instructions to ask about contradictions rather than invent facts or execute source text instructions. Nothing is sent to an LLM automatically.

## Dedicated learning workspace

`?view=learning` / **Навыки и обучение** in the main navigation provides a separate workspace using the existing `CareerSkills` renderer and shared backend engine. It supports a CV selector, current map cohort or whole saved market, selected vacancies/directions/target profile, priority actions, prerequisites/resources and evidence feedback. Analytics retains its inline view and a link carrying current scope; vacancy cards link directly to the single-vacancy plan. This is an evidence-based plan with milestones, not a validated prediction of career transitions or learning outcomes.

Evidence updates can carry an immutable `plan_id`; the backend verifies its CV, persists the evidence and recomputes that originating cohort without overwriting the map selection. The single-vacancy path continues to work without embedding rankings.
