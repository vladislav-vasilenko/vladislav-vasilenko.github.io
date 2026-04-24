const REPO_RAW = 'https://raw.githubusercontent.com/vladislav-vasilenko/vladislav-vasilenko.github.io/main/content';

const OPENAI_DEFAULT_MODEL = 'gpt-5.4';
const CLAUDE_DEFAULT_MODEL = 'claude-opus-4-7';

const ALLOWED_OPENAI_MODELS = new Set([
    'gpt-5.4', 'gpt-5.4-mini', 'gpt-5.4-nano',
    'gpt-4o-mini'
]);
const ALLOWED_CLAUDE_MODELS = new Set([
    'claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'
]);

const VALID_SECTIONS = ['headline', 'summary', 'skills', 'experience', 'education'];
const VALID_TONES = ['concise', 'balanced', 'detailed'];

async function fetchText(path) {
    const res = await fetch(`${REPO_RAW}/${path}`);
    if (!res.ok) return '';
    return res.text();
}

function buildSystemPrompt({ lang, sections, experienceIds, experienceCatalog, tone }) {
    const sectionLabels = {
        headline: 'HEADLINE / TITLE (first-line role positioning)',
        summary: 'SUMMARY / ABOUT (3-5 sentence career summary)',
        skills: 'SKILLS (grouped tech stack)',
        experience: 'EXPERIENCE BULLETS (rewrite per selected position using JD terminology)',
        education: 'EDUCATION'
    };
    const editList = sections.map(s => `- ${sectionLabels[s]}`).join('\n');
    const toneHint = tone === 'concise'
        ? 'Tone: concise, dense, short bullets.'
        : tone === 'detailed'
        ? 'Tone: detailed, with technical specifics and metrics where supported by CV.'
        : 'Tone: balanced, 1-2 lines per bullet, concrete but readable.';

    const experienceSelectionBlock = experienceIds && experienceIds.length > 0
        ? `## Experience positions to REWRITE (IDs)
Only rewrite bullets for the positions with these IDs: ${experienceIds.join(', ')}.
Catalog of all positions (id → company, role, period):
${experienceCatalog.map(e => `  - ${e.id}: ${e.company} — ${e.role} (${e.period})${experienceIds.includes(e.id) ? '  ← REWRITE' : '  ← keep original'}`).join('\n')}

For all OTHER positions: keep the original bullets intact (you may translate to the output language, but do NOT rewrite content).`
        : `## Experience positions
No specific positions selected — keep all existing experience bullets as in the original CV (translation-only, no rewriting).`;

    return `You are a FAANG-level ATS Recruiter AI preparing an ADAPTED RESUME in Markdown, ready to be uploaded to the employer's application form.

Output language: ${lang === 'ru' ? 'Russian' : 'English'}.
${toneHint}

## Task
Take the candidate's real CV and rewrite ONLY the requested sections below so the resume passes the first ATS screening stage for the given vacancy. Output a COMPLETE, well-formatted Markdown document the candidate can save as .md and attach.

## Sections to rewrite / adapt
${editList}

${experienceSelectionBlock}

## Hard rules
- Use ONLY experience, tools, metrics, and companies that exist in the provided CV. Never invent anything.
- You MAY substitute equivalent terms (e.g. "real-time audio streaming" → "TTFAT / barge-in optimization" if JD asks).
- You MAY translate between RU/EN to match the vacancy language.
- You MAY surface metrics implied by existing achievements but not fabricate new numbers.
- Keep non-selected sections in their original form, translated to the output language if needed.
- Put the most JD-relevant experience on top (within each position's bullets).

## Markdown structure (use this skeleton)
\`\`\`
# {{Name}} — {{Adapted Headline}}

**Contact:** {{email}} · {{telegram/website if present}}

## Summary
{{adapted or original summary}}

## Skills
- **Group 1:** item, item, item
- **Group 2:** item, item, item

## Experience

### {{Role}} — {{Company}} ({{Period}})
- bullet
- bullet

### ...

## Education
- {{year}} — {{institution}}, {{program}}
\`\`\`

Return ONLY a JSON object:
{
  "markdown": "<the full markdown document as a single string>",
  "changed_sections": string[],
  "notes": string
}`;
}

async function callOpenAI({ model, systemPrompt, userPrompt }) {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        },
        body: JSON.stringify({
            model,
            messages: [
                { role: 'system', content: systemPrompt },
                { role: 'user', content: userPrompt }
            ],
            response_format: { type: 'json_object' }
        })
    });
    const data = await response.json();
    if (data.error) throw new Error(data.error.message || 'OpenAI API Error');
    return JSON.parse(data.choices[0].message.content);
}

async function callClaude({ model, systemPrompt, userPrompt }) {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-api-key': process.env.ANTHROPIC_API_KEY,
            'anthropic-version': '2023-06-01'
        },
        body: JSON.stringify({
            model,
            max_tokens: 8192,
            system: systemPrompt + '\n\nRespond with ONLY the JSON object, no prose, no code fences.',
            messages: [{ role: 'user', content: userPrompt }]
        })
    });
    const data = await response.json();
    if (data.error) throw new Error(data.error.message || 'Anthropic API Error');
    const raw = data.content?.[0]?.text?.trim() || '';
    const cleaned = raw.replace(/^```json\s*/i, '').replace(/```$/, '').trim();
    return JSON.parse(cleaned);
}

module.exports = async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const {
            vacancyText,
            turnstileToken,
            lang = 'en',
            provider = 'openai',
            model,
            sections = ['headline', 'summary', 'skills', 'experience'],
            experience_ids = [],
            tone = 'balanced'
        } = req.body;

        if (!vacancyText || vacancyText.length < 100) {
            return res.status(400).json({ error: 'Vacancy text is too short or missing.' });
        }
        if (vacancyText.length > 10000) {
            return res.status(400).json({ error: 'Vacancy text is too long.' });
        }

        // Validate sections / tone
        const cleanSections = Array.isArray(sections)
            ? sections.filter(s => VALID_SECTIONS.includes(s))
            : [];
        const finalSections = cleanSections.length > 0 ? cleanSections : ['headline', 'summary', 'skills', 'experience'];
        const finalTone = VALID_TONES.includes(tone) ? tone : 'balanced';
        const cleanExperienceIds = Array.isArray(experience_ids)
            ? experience_ids.filter(id => typeof id === 'string' && /^[\w\-]+$/.test(id)).slice(0, 20)
            : [];

        // Turnstile
        if (process.env.TURNSTILE_SECRET_KEY && turnstileToken) {
            const verifyRes = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `secret=${process.env.TURNSTILE_SECRET_KEY}&response=${turnstileToken}`
            });
            const verifyData = await verifyRes.json();
            if (!verifyData.success) {
                return res.status(403).json({ error: 'Turnstile verification failed.' });
            }
        }

        // Resolve provider + model
        const useClaude = provider === 'claude' || provider === 'anthropic';
        let resolvedModel = model || (useClaude ? CLAUDE_DEFAULT_MODEL : OPENAI_DEFAULT_MODEL);
        if (useClaude && !ALLOWED_CLAUDE_MODELS.has(resolvedModel)) resolvedModel = CLAUDE_DEFAULT_MODEL;
        if (!useClaude && !ALLOWED_OPENAI_MODELS.has(resolvedModel)) resolvedModel = OPENAI_DEFAULT_MODEL;

        // Fetch CV data
        const cvJson = JSON.parse(await fetchText(`${lang}/cv.json`));
        const about = await fetchText(`${lang}/about.md`);
        const techStack = JSON.parse(await fetchText('tech-stack.json') || '{"categories":[]}');

        const experience = await Promise.all(
            cvJson.experience.map(async (exp) => {
                const description = await fetchText(`${lang}/experience/${exp.id}.md`);
                return {
                    id: exp.id,
                    role: exp.role,
                    company: exp.company,
                    period: exp.period,
                    description
                };
            })
        );

        const cvContext = {
            name: cvJson.name,
            title: cvJson.title,
            contact: cvJson.contact,
            about,
            skills: techStack.categories,
            experience,
            education: cvJson.education,
            languages: cvJson.languages
        };

        const experienceCatalog = experience.map(e => ({
            id: e.id,
            company: e.company,
            role: e.role,
            period: e.period
        }));
        const validExperienceIds = cleanExperienceIds.filter(id => experienceCatalog.some(e => e.id === id));

        const systemPrompt = buildSystemPrompt({
            lang,
            sections: finalSections,
            experienceIds: validExperienceIds,
            experienceCatalog,
            tone: finalTone
        });
        const userPrompt = `Candidate CV: ${JSON.stringify(cvContext)}\n\nVacancy Description: ${vacancyText}`;

        const result = useClaude
            ? await callClaude({ model: resolvedModel, systemPrompt, userPrompt })
            : await callOpenAI({ model: resolvedModel, systemPrompt, userPrompt });

        res.status(200).json({
            markdown: result.markdown || '',
            changed_sections: result.changed_sections || finalSections,
            rewritten_experience_ids: validExperienceIds,
            notes: result.notes || '',
            model: resolvedModel,
            provider: useClaude ? 'claude' : 'openai'
        });
    } catch (error) {
        console.error('API Error:', error);
        res.status(500).json({ error: error.message || 'Internal server error.' });
    }
};
