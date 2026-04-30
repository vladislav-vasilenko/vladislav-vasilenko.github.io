// OpenAI embeddings proxy.
// POST { texts: string[], model?: string } → { embeddings: number[][], model, usage, dim }
// Auth: Authorization: Bearer ${API_SECRET}
//
// Used by tools/cv_matcher/scripts/index_meta_to_chroma.py and build_cluster_map.py
// so the OPENAI_API_KEY stays on Vercel and never leaves the server.

export const maxDuration = 60;

const DEFAULT_MODEL = 'text-embedding-3-small';
const ALLOWED_MODELS = new Set([
    'text-embedding-3-small',
    'text-embedding-3-large',
    'text-embedding-ada-002',
]);
const MAX_BATCH = 256;          // OpenAI limit is 2048; we cap conservatively for Vercel timeouts
const MAX_TOTAL_CHARS = 4_000_000; // ~1M tokens safety net per call

async function callOpenAIEmbeddings({ model, input }) {
    const r = await fetch('https://api.openai.com/v1/embeddings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
        },
        body: JSON.stringify({ model, input }),
    });
    const data = await r.json();
    if (data.error) throw new Error(data.error.message || 'OpenAI Embeddings error');
    return data; // { data: [{ embedding, index }], model, usage }
}

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const apiSecret = req.headers.authorization;
        if (process.env.API_SECRET && apiSecret !== `Bearer ${process.env.API_SECRET}`) {
            return res.status(401).json({ error: 'Unauthorized: Invalid API_SECRET' });
        }

        const { texts, model = DEFAULT_MODEL } = req.body || {};

        if (!Array.isArray(texts) || texts.length === 0) {
            return res.status(400).json({ error: 'texts must be a non-empty array of strings' });
        }
        if (texts.length > MAX_BATCH) {
            return res.status(400).json({ error: `max ${MAX_BATCH} texts per call (got ${texts.length})` });
        }
        if (!ALLOWED_MODELS.has(model)) {
            return res.status(400).json({
                error: `model must be one of: ${[...ALLOWED_MODELS].join(', ')}`,
            });
        }
        const totalChars = texts.reduce((n, t) => n + (typeof t === 'string' ? t.length : 0), 0);
        if (totalChars > MAX_TOTAL_CHARS) {
            return res.status(400).json({ error: `combined input too large (${totalChars} chars)` });
        }
        if (texts.some(t => typeof t !== 'string' || t.length === 0)) {
            return res.status(400).json({ error: 'each text must be a non-empty string' });
        }

        const result = await callOpenAIEmbeddings({ model, input: texts });

        // OpenAI returns embeddings out of order; restore by index field.
        const embeddings = result.data
            .slice()
            .sort((a, b) => a.index - b.index)
            .map(d => d.embedding);

        return res.status(200).json({
            embeddings,
            model: result.model,
            usage: result.usage,
            dim: embeddings[0]?.length || 0,
            count: embeddings.length,
        });
    } catch (e) {
        console.error('Embeddings API Error:', e);
        return res.status(500).json({ error: e.message || 'Internal Server Error' });
    }
}
