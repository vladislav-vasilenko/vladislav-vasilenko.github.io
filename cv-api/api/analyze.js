const REPO_RAW = 'https://raw.githubusercontent.com/vladislav-vasilenko/vladislav-vasilenko.github.io/main/content';

const OPENAI_DEFAULT_MODEL = 'gpt-5.4';
const CLAUDE_DEFAULT_MODEL = 'claude-opus-4-7';

const ALLOWED_OPENAI_MODELS = new Set([
    'gpt-5.4', 'gpt-5.4-mini', 'gpt-5-mini-2025-08-07',
    'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'
]);
const ALLOWED_CLAUDE_MODELS = new Set([
    'claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'
]);

async function fetchText(path) {
    const res = await fetch(`${REPO_RAW}/${path}`);
    if (!res.ok) return '';
    return res.text();
}

function buildSystemPrompt(lang) {
    return `You are a FAANG-level ATS Recruiter AI helping a candidate both analyze fit AND prepare to apply.
You will receive the candidate's CV data and a vacancy description.
Output language: ${lang === 'ru' ? 'Russian' : 'English'}.

Return ONLY a JSON object with this exact shape:
{
  "score": number (0-100),
  "summary": string,
  "pros": string[],
  "cons": string[],
  "strengths": string[],
  "weaknesses": string[],
  "improvement_tips": string[],
  "adapted_bullets": string[],
  "application_message": string
}

## improvement_tips (3-5 items)
Concrete, actionable changes to the CV to pass the FIRST ATS screening stage for THIS vacancy.
Each tip: "Action + place in CV (headline / summary / skills / specific position bullet) + concrete wording".
Focus on: missing JD keywords, re-phrasings of equivalent real experience, seniority/scope signals, ordering.
FORBIDDEN: advising to invent experience, tools, or metrics.

## adapted_bullets (2-3 items)
Rewrite 2-3 of the candidate's EXISTING bullets using the JD's terminology. This is the "fixed resume" block the candidate can paste.
DO NOT invent new experience, tools, metrics, or companies.
You MAY: substitute equivalent terms, surface metrics already implied, translate.

## application_message (120-220 words, single paragraph)
Ready-to-paste message for the employer's modal application form.
Flow: short greeting → why this role (1-2 JD signals) → 3 concrete confirmations from the real CV (dense, comma-separated, with tech/role) → readiness for next step.
No markdown, no "Dear Hiring Manager" placeholders, no fabrications, no corporate fluff.
Match the language to the vacancy language (RU JD → RU, EN JD → EN).`;
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
            max_tokens: 4096,
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
    // CORS
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
            model
        } = req.body;

        if (!vacancyText || vacancyText.length < 100) {
            return res.status(400).json({ error: 'Vacancy text is too short or missing.' });
        }
        if (vacancyText.length > 10000) {
            return res.status(400).json({ error: 'Vacancy text is too long.' });
        }

        // Verify Turnstile
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

        // Resolve provider + model (whitelisted)
        const useClaude = provider === 'claude' || provider === 'anthropic';
        let resolvedModel = model || (useClaude ? CLAUDE_DEFAULT_MODEL : OPENAI_DEFAULT_MODEL);
        if (useClaude && !ALLOWED_CLAUDE_MODELS.has(resolvedModel)) resolvedModel = CLAUDE_DEFAULT_MODEL;
        if (!useClaude && !ALLOWED_OPENAI_MODELS.has(resolvedModel)) resolvedModel = OPENAI_DEFAULT_MODEL;

        // Fetch CV Data for context
        const cvJson = JSON.parse(await fetchText(`${lang}/cv.json`));
        const about = await fetchText(`${lang}/about.md`);
        const experience = await Promise.all(
            cvJson.experience.map(async (exp) => {
                const description = await fetchText(`${lang}/experience/${exp.id}.md`);
                return { role: exp.role, company: exp.company, description };
            })
        );

        const cvContext = { name: cvJson.name, title: cvJson.title, about, experience };

        const systemPrompt = buildSystemPrompt(lang);
        const userPrompt = `Candidate CV: ${JSON.stringify(cvContext)}\n\nVacancy Description: ${vacancyText}`;

        const analysis = useClaude
            ? await callClaude({ model: resolvedModel, systemPrompt, userPrompt })
            : await callOpenAI({ model: resolvedModel, systemPrompt, userPrompt });

        res.status(200).json({ ...analysis, model: resolvedModel, provider: useClaude ? 'claude' : 'openai' });
    } catch (error) {
        console.error('API Error:', error);
        res.status(500).json({ error: error.message || 'Internal server error.' });
    }
};
