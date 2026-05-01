export const maxDuration = 60;

const OPENAI_DEFAULT_MODEL = 'gpt-5-mini';

export default async function handler(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    try {
        const { messages, model = OPENAI_DEFAULT_MODEL, response_format } = req.body;
        const authHeader = req.headers.authorization;

        // Security check
        if (process.env.API_SECRET && authHeader !== `Bearer ${process.env.API_SECRET}`) {
            return res.status(401).json({ error: 'Unauthorized: Invalid API_SECRET' });
        }

        if (!messages || !Array.isArray(messages)) {
            return res.status(400).json({ error: 'Missing or invalid messages array' });
        }

        // Call OpenAI
        const response = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
            },
            body: JSON.stringify({
                model,
                messages,
                response_format,
                temperature: 0
            })
        });

        const data = await response.json();
        
        if (data.error) {
            console.error('OpenAI Error:', data.error);
            return res.status(500).json({ error: data.error.message || 'OpenAI API Error' });
        }

        res.status(200).json(data);

    } catch (error) {
        console.error('Proxy Error:', error);
        res.status(500).json({ error: 'Internal server error: ' + error.message });
    }
}
