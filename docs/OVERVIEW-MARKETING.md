# Career Workspace — your private job-search command center

**Find the roles that fit you, understand what they really ask for, and send fewer, better applications — with every decision staying in your hands and every byte of data on your own machine.**

Career Workspace is a personal career-intelligence system. It gathers vacancies from the sites where you actually look for work, keeps them in one private archive, compares them with your résumés and career goals, tells you which skills to prove next, prepares grounded answers and cover letters, and tracks every application until the offer. A Chrome extension does the browsing in your own logged-in session; a local service on your laptop does the thinking; Telegram keeps you in control from your phone. Nothing is sent to an employer without your explicit approval of the exact text.

---

## Why it exists

Job searching in 2026 is fragmented and exhausting:

- Vacancies are scattered across HH.ru, company career sites, LinkedIn and global employers, each with its own filters and half-complete descriptions.
- You keep several CV versions and lose track of which one fits which role.
- It is hard to tell what to learn next, and "similar keywords" is not the same as being qualified.
- Writing a thoughtful application takes an hour; sending fifty careless ones takes the same hour and works worse.
- Recruiter chats, interview stages and follow-ups live in five different inboxes.

Career Workspace turns this into one loop: **collect → understand → choose → prepare → apply → follow up → improve.**

---

## How it helps you find a job

1. **See the whole market you care about.** One archive of vacancies from HH, Russian tech employers, Chinese AI labs, Google, Meta and LinkedIn, with full descriptions, versions and history.
2. **Know where you fit.** Rank vacancies against the CV you choose and the goal you set, and see the matching passages from both texts.
3. **Know what to do next.** A career trajectory with stages and completion criteria tells you which skill or project closes the next gap, and separates "I studied it" from "I have proven it".
4. **Apply with quality, not volume.** Draft answers and cover letters are built only from facts in your CV and your own notes, with sources shown, and you edit or replace every word.
5. **Never lose a thread.** A CRM tracks each application from first contact through three interview rounds to offer or rejection, with reminders from the "Today" screen and Telegram.
6. **Keep your public profile current.** Your reviewed headline and experience flow from your primary HH résumé to your public portfolio site, in English and Russian.

---

## Complete feature list

### 1. Vacancy discovery and collection

1. **HH.ru search builder** for chosen company tiers and research directions, Moscow or remote across Russia, with an optional "last 3 days" mode.
2. **HH search crawling with pagination and full descriptions**, safe batches, stop button, and resumption from a saved cursor.
3. **HH recommendations for a specific CV**: collect the vacancies HH recommends for a selected résumé and compare them with that CV and goal.
4. **Company career sites** via declarative adapters: Yandex, Sber, Avito, Ozon (two layouts), T-Bank, plus Ozon.Tech dual ML/PyTorch search merged by vacancy ID.
5. **T-Bank filter profiles** ("IT development + Machine learning"), verified on the page before collection; unknown filters stop the run instead of silently widening it.
6. **Global and Chinese employers** collected by Python/Playwright in GitHub Actions: Yandex, Google, Meta (unlimited mode, GraphQL v2), and DeepSeek, Moonshot, ByteDance, Alibaba, Kuaishou, MiniMax, Tencent, Z.ai, Shengshu.
7. **Hybrid collection** with four modes (Python first, Chrome first, Python only, Chrome only) and bounded fallback between them.
8. **Separate, resumable backfill of full descriptions**, with per-source progress, attempts, pauses and error reasons; snippets and full texts are tracked with different quality states.
9. **24-hour description cache** with change detection from title, company, snippet and date, plus a forced-refresh option.
10. **Add one vacancy by link** (read through Chrome) or by manual paste.
11. **Scheduled search** at 10:00 and 19:00 Moscow time for up to six sources, with page and description limits; paid embeddings only when you explicitly allow them.
12. **Custom CSS recipes** for trying an unsupported job board, marked "needs review" until checked.
13. **GitHub Actions import**: daily cloud runs are listed, controlled and imported into the local archive in verified batches.

### 2. Private archive and data model

14. **One local SQLite archive** for résumés, vacancies, versions, observations, embeddings, rankings, analyses and applications.
15. **Versioned snapshots**: an analysis always points to the exact CV and vacancy text it used; editing never rewrites history.
16. **Stable identities and de-duplication** shared by the Python collectors and the extension.
17. **Closed and archived vacancy handling**: absence from a partial listing never closes a vacancy by itself.
18. **Company catalog editor** with tiers, regions and multi-select filters across the archive and rankings.
19. **Locations** model and region filters.
20. **Backup and restore guidance**, JSON export of the private archive and merge-restore into the extension.

### 3. Résumés

21. **Load every résumé from your HH catalog** in one action, skipping empty drafts.
22. **Import an HH résumé by direct link**, including one outside your own catalog, when HH allows viewing it.
23. **File import**: DOCX, DOC, PDF, Pages, TXT and Markdown, parsed locally with no macro execution; Google Docs read from the open tab with your existing session.
24. **Review before saving** and choice of a primary CV.
25. **Document comparison** of CV versions as paragraph flows or sections, with an alluvial view.
26. **Portfolio review of 2–7 CV snapshots** plus supporting documents against a target profile, including timeline consistency, via API or a copy-paste prompt with verified JSON import.
27. **Candidate facts and supplementary documents** (dates, responsibilities, project context) with recorded provenance.
28. **Free HH résumé bump**: opt-in, presses only the exact free "raise in search" button, at most every 4 hours, never a paid service.

### 4. Matching and ranking

29. **Semantic ranking** of up to 2000 vacancies against the selected CV, in batches of 200, with a merged, sortable result.
30. **Goal blending**: 80% CV and 20% career goal when a goal is set.
31. **Evidence shown with the score**: the closest vacancy and CV passages are displayed, so you can judge the match yourself.
32. **Selectable embedding model** (small or large) with caching of unchanged chunks; different vector spaces are never mixed.
33. **Detailed skill analysis** of one CV against one vacancy: requirement by requirement, required versus preferred versus mentioned, with exact quotes verified against the source texts.
34. **Two AI modes everywhere**: call the model through the local API, or copy a complete prompt into ChatGPT and import the answer, at zero API cost.
35. **Opportunity map** (`/archive/analytics`): a semantic map of the market and a Sankey view of sample composition.
36. **Shared top-10 ranking** in the web app and in Telegram.

### 5. Career trajectory and skills intelligence

37. **Editable career trajectory**: goal, stages with dependencies, and completion criteria.
38. **Required versus optional criteria**, so specialisations do not block the main route.
39. **Evidence types kept separate**: professional practice, project, research, course, CV mention; a course never closes a practical criterion.
40. **Skill requirements extracted from vacancies** with quotes, strictness and confidence.
41. **Next-action priorities**: learn, practise, validate, document in CV, or publish a project.
42. **Trajectory badges and filters on vacancies**, explaining why a role fits a route, and showing roles at the intersection of several routes.
43. **Adapt a trajectory to a target role** as a reviewable draft that bumps the version on save.
44. **Learning impact view** showing which actions unlock the most vacancies.

### 6. Applications, answers and cover letters

45. **"Apply" from any ranked vacancy**, bound to the exact CV version, vacancy and goal.
46. **Cover letters** of 1 to 50 sentences, from the selected CV plus your personal motivation; numbers, technologies and quotes are checked against the sources, and results are cached.
47. **Recruiter answer drafts** grounded only in your CV, notes and history, with the source of every claim; invented experience is rejected.
48. **HH application flow**: read the form, draft or edit answers, fill them in, then submit only after a one-time approval of that exact text; an uncertain result is never retried blindly.
49. **Company form assistant** for Yandex, Avito, Ozon and T-Bank: read the form, preview the exact values, transfer only approved fields; files, consents and final submission stay manual.
50. **Autofill profile** (name, contacts, city, social links, portfolio) versioned locally and offered only for empty fields.
51. **In-page panels** on employer sites and inline actions on HH: fit analysis and cover letter right next to the vacancy.
52. **Visible marks on HH** for vacancies you already saved, analysed or applied to.
53. **"Copy CV + vacancy for ChatGPT"** package for analysis and follow-up questions, with nothing else from your archive included.
54. **HH rejection cleanup**: find explicit rejections, save them to your CRM history, then delete them on HH only after you confirm the list.

### 7. Application CRM and daily focus

55. **CRM stages**: communication, three interview rounds, rejection, offer, with notes and history.
56. **HH status sync** every 5 minutes after you enable it, reading the negotiations list and recent chats; new messages and status changes are forwarded to Telegram.
57. **Interview planning** with Google Calendar sync.
58. **Manual application records** for channels the system does not read.
59. **"Today" screen** with the single next action per application and the unfinished preparations.
60. **Clipboard vacancy export** with résumé and trajectory context, ready for an external assistant.

### 8. LinkedIn workspace

61. **Own profile reading**: headline, About, experience, education and certificates, with language selection and coverage reported section by section.
62. **Guided profile editing**: open the editor, transfer verified values, save as a separate step, and re-read to confirm; version history kept locally.
63. **LinkedIn jobs**: recommended, "more" and profile-based listings in infinite-scroll or paginated mode, with full descriptions, logos, locations, applicant counts, badges and real Apply/ATS links; explicit import into the main archive.
64. **Contacts**: connections and incoming or sent invitations, full "collect all" walks with resume of new profiles only, search across the whole local base, notes, tags, follow-ups and links to vacancies.
65. **Contact review plan**: headline-based relevance and a local keep / unfollow / disconnect plan that changes nothing on LinkedIn by itself.
66. **Chats**: every conversation and its message history, merged by message ID, with previews kept separate from history.
67. **Chat advice**: résumé, goal and selected conversations analysed via API (after confirmation, one paid attempt per context) or via clipboard prompt; quotes are verified, no invented offer probabilities, and nothing is ever sent to the other person.
68. **Human-paced reading**: random batches of 8–12, 3–8 second intervals and one-minute breaks; any login or verification screen pauses the queue.

### 9. Teams and network

69. **Vacancy teams**: hiring team read from LinkedIn and public members of a Hugging Face organisation, attached to the vacancy card.
70. **Research streams** annotated only with evidence; organisation membership is never treated as proof of a role.
71. **Network map** linking teams, streams, people and vacancies from recorded sources only.

### 10. Control from anywhere

72. **Local web app** on `127.0.0.1:8788`: Today, Vacancies, Analytics, Résumés, Trajectories, Applications, LinkedIn and Settings.
73. **Telegram control bot**: `/today`, `/hh`, `/sync_hh`, `/status`, skills and learning, applications and résumé-bump settings; live progress of running searches in a single updating message.
74. **Scheduled Telegram reminders** about unfinished applications and checks, from the same queue as the Today screen.
75. **Optional Telethon userbot** for recruiter bots that talk to you on Telegram, with Luna/Terra/Sol drafts you edit, replace or send explicitly.
76. **MCP server** for AI assistants, with a thin tool set and no arbitrary SQL, code or submit access.
77. **Shared task control**: pause, cancel and resume any collection from web, Telegram or MCP, keeping partial results.
78. **Diagnostics page** in the extension showing connections, domain permissions, task states and cache counters, without texts, contacts or tokens.

### 11. Public portfolio

79. **Bilingual portfolio site** (EN `/`, RU `/ru/`) prerendered for search engines and readers without JavaScript, with eight presentation styles.
80. **Automatic publication of reviewed data**: title and work history from your primary HH résumé, and a reviewed RU/EN introduction.
81. **Opt-in public visuals**: current direction, focus topics, public labs and anonymised market charts.
82. **Markdown CV export** from the site, importable back into the workspace as a versioned résumé.
83. **SEO and sharing**: canonicals, hreflang, sitemap, social previews and structured profile data.
84. **Installable PWA** with offline reading of the public pages.

---

## Built on trust

- **Your approval is the only send button.** Every irreversible action (HH submission, rejection deletion, résumé bump, LinkedIn profile save or contact action) needs your explicit, single-use approval and stops on any doubt instead of retrying.
- **Local first.** The archive, chats, contacts, notes, analyses and API keys stay on your laptop. The extension never sees your OpenAI key; the public site receives only an allow-listed JSON projection.
- **Honest numbers.** Semantic similarity, requirement coverage and career value are shown as different signals. None of them is presented as your chance of an interview.
- **Cost under control.** Browsing, comparing, planning and copying prompts never call a paid model; every paid call is a separate, visible action, and results are cached.
- **No credential harvesting.** Passwords and cookies are never exported; the extension works inside the session you already have open.

---

## What it is not

- Not a mass-apply bot. It is designed to make each application better, not to send more of them.
- Not a guarantee of coverage: sites change their pages, and each adapter's support is tracked capability by capability.
- Not a 24/7 cloud service: the personal workspace runs while your computer is on; cloud runs collect only public vacancies.
- Not a hiring predictor: it explains fit and gaps, it does not promise outcomes.

---

## Under the hood

| Part | Technology |
|---|---|
| Local service | Python, FastAPI, SQLite, on `127.0.0.1:8788` |
| Browser executor | Chrome Manifest V3 extension with declarative site adapters |
| Web app | Plain JavaScript, served by the local service |
| Cloud collection | GitHub Actions with Python and Playwright |
| Messaging | Telegram Bot API, optional Telethon userbot, MCP stdio server |
| Models | OpenAI embeddings and chat models through the local service, or any assistant via copy-paste prompts |
| Public site | TypeScript, Vite, static prerender, GitHub Pages, PWA |

Getting started: [Career Workspace quickstart](../tools/cv_matcher/docs/applicant_quickstart.md) · [Documentation index](../tools/cv_matcher/docs/README.md) · [Security and secrets](../tools/cv_matcher/docs/security.md)
