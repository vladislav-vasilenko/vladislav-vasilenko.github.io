export const maxDuration = 60; // Allow function to run up to 60s

const OPENAI_DEFAULT_MODEL = 'gpt-5.4';
const CLAUDE_DEFAULT_MODEL = 'claude-opus-4-7';

const SYSTEM_PROMPT = `You are a FAANG-level ATS Recruiter AI.
Evaluate the candidate's Resume against the provided Job Description and output a strict, calibrated JSON assessment.

## Scoring rubric (MUST follow)
Score on a 0-100 scale using FOUR equal axes (each worth 25 points):
  • Tech stack overlap (25) — languages, frameworks, libraries, ML techniques.
  • Seniority / scope (25) — level, team size, project complexity.
  • Domain fit (25) — industry, product area.
  • Soft signals (25) — language, location/remote, leadership, research/production profile.
Bucket calibration:
  • 90-100 near-perfect; 70-89 strong; 50-69 partial; <50 weak.
Be strict, do not inflate.

## Output fields
  • ats_score_percentage — integer 0-100.
  • sphere — one of: 'GenAI / LLM', 'Computer Vision', 'ML / Data Science', 'Audio / Speech', 'Backend', 'Mobile', 'Product / Management'.
  • matched_keywords — skills that appear in BOTH CV and JD (≤12).
  • missing_keywords — critical JD requirements missing from CV (≤8).
  • reasoning — 1-2 sentences in Russian referencing the rubric axes.
  • adapted_bullets — 2-3 rewritten CV bullets in Russian (see rules).
  • improvement_tips — 3-5 actionable advice items in Russian (see rules).
  • application_message — ready-to-paste application text (see rules).
  • is_good_match — leave false, runtime computes.

## adapted_bullets rules
Rewrite 2-3 of the candidate's EXISTING bullets using JD terminology.
DO NOT invent new experience, tools, metrics, companies.
You MAY: substitute equivalent terms, surface implied metrics, translate language.
Output in Russian.

## improvement_tips rules
Give 3-5 concrete, actionable tips on what to change/add in the resume to pass the FIRST ATS screening stage for THIS specific vacancy.
Focus on:
  • JD keywords the CV lacks — specify where to add (headline / summary / skills / a specific position's bullet);
  • re-phrasings when the candidate has equivalent real experience but names it differently;
  • structural signals (seniority, scope, team, production/research);
  • ordering and prioritization of experience for this JD.
FORBIDDEN: advising to invent experience, tools, metrics. Only regrouping/rewording of REAL experience.
Format of each tip: "Action + place in CV + concrete wording". In Russian.

## application_message rules
Write a 120-220 word message the candidate will paste VERBATIM into the employer's modal application form.
Flow (as one connected prose, no markdown, no headings):
  1. Short greeting (one line).
  2. Why this role — 1-2 concrete signals from JD (product / stack / task).
  3. Three concrete confirmations from real CV experience — dense, comma-separated, with tech stack and role.
  4. Readiness for the next step (call / test task / code samples).
Requirements:
  • language matches JD language (RU JD → RU message, EN JD → EN);
  • no "Dear Hiring Manager" / "Уважаемый работодатель" placeholders;
  • do not invent anything not in the CV;
  • confident, concrete tone, no corporate fluff, no self-praise;
  • end with one short call-to-action sentence.

Return ONLY a single JSON object with this exact shape:
{
  "ats_score_percentage": number,
  "sphere": "string",
  "matched_keywords": string[],
  "missing_keywords": string[],
  "reasoning": "string",
  "adapted_bullets": string[],
  "improvement_tips": string[],
  "application_message": "string",
  "is_good_match": boolean
}`;

async function callOpenAI({ model, vacancyText, cvText }) {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        },
        body: JSON.stringify({
            model,
            messages: [
                { role: 'system', content: SYSTEM_PROMPT },
                { role: 'user', content: `Job Description:\n${vacancyText}\n\nCandidate Resume:\n${cvText}` }
            ],
            response_format: { type: 'json_object' }
        })
    });
    const data = await response.json();
    if (data.error) throw new Error(data.error.message || 'OpenAI API Error');
    return JSON.parse(data.choices[0].message.content);
}

async function callClaude({ model, vacancyText, cvText }) {
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
            system: SYSTEM_PROMPT + '\n\nRespond with ONLY the JSON object, no prose, no code fences.',
            messages: [
                { role: 'user', content: `Job Description:\n${vacancyText}\n\nCandidate Resume:\n${cvText}` }
            ]
        })
    });
    const data = await response.json();
    if (data.error) throw new Error(data.error.message || 'Anthropic API Error');
    const raw = data.content?.[0]?.text?.trim() || '';
    const cleaned = raw.replace(/^```json\s*/i, '').replace(/```$/, '').trim();
    return JSON.parse(cleaned);
}

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const { vacancyText, cvText, provider = 'openai', model } = req.body;
        const apiSecret = req.headers.authorization;

        if (process.env.API_SECRET && apiSecret !== `Bearer ${process.env.API_SECRET}`) {
            return res.status(401).json({ error: 'Unauthorized: Invalid API_SECRET' });
        }
        if (!vacancyText || !cvText) {
            return res.status(400).json({ error: 'Missing vacancy or cv text' });
        }

        const useClaude = provider === 'claude' || provider === 'anthropic';
        const resolvedModel = model || (useClaude ? CLAUDE_DEFAULT_MODEL : OPENAI_DEFAULT_MODEL);

        const analysis = useClaude
            ? await callClaude({ model: resolvedModel, vacancyText, cvText })
            : await callOpenAI({ model: resolvedModel, vacancyText, cvText });

        if (typeof analysis.ats_score_percentage === 'number') {
            analysis.is_good_match = analysis.ats_score_percentage >= 70;
        }

        res.status(200).json({ ...analysis, model: resolvedModel, provider: useClaude ? 'claude' : 'openai' });
    } catch (e) {
        console.error('API Error:', e);
        res.status(500).json({ error: e.message || 'Internal Server Error' });
    }
}
