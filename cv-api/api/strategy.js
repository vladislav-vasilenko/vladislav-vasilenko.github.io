module.exports = async function handler(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { message, history = [], matches = [] } = req.body;

        if (!message) {
            return res.status(400).json({ error: 'Message is required.' });
        }

        // Format the top matches to feed into the prompt efficiently
        const matchesContext = matches.slice(0, 15).map((m, i) => 
            `[ID: ${m.id}] ${i + 1}. ${m.title} at ${m.company} (Sim: ${(m.similarity * 100).toFixed(1)}%, Track: ${m.track})`
        ).join('\n');

        const systemPrompt = `You are an expert AI Career Strategist named "Clippy" for Vladislav Vasilenko. 
You are embedded on his interactive Vacancy Cluster Map portfolio site.
Your goal is to answer questions about which jobs fit him best, why he fits them, and provide strategic career advice.

Vladislav's profile:
- Strong background in iOS native development (5+ years).
- Deep expertise in Audio AI, ML, GenAI (Voice Cloning, TTS, Flow Matching, PyTorch).
- Product-minded (can take an AI model and build a full product/app).
- Looking for roles like "Forward Deployed Engineer" (Sweet spot), "Audio ML Engineer", or "iOS AI Engineer".

Context of Top Job Matches from his recent scrape:
${matchesContext}

Rules:
1. Be concise, professional yet friendly (use emojis).
2. You can refer to the jobs by their ID or title.
3. If the user asks about a specific job, explain why it fits Vlad's unique "iOS + Audio AI + Product" profile.
4. DO NOT hallucinate jobs. Only recommend from the provided context list.
5. If you want the map to zoom to a specific job, include the exact string "ZOOM_TO[id]" anywhere in your response (e.g. ZOOM_TO[goog_134173918213612230]). The frontend will parse this and hide it from the user.`;

        const messages = [
            { role: 'system', content: systemPrompt },
            ...history.map(h => ({ role: h.role, content: h.content })),
            { role: 'user', content: message }
        ];

        const response = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
            },
            body: JSON.stringify({
                model: 'gpt-5.4-mini',
                messages: messages,
                temperature: 0.7
            })
        });

        const data = await response.json();

        if (data.error) {
            console.error('OpenAI Error:', data.error);
            return res.status(500).json({ error: 'AI generation failed.' });
        }

        const answer = data.choices[0].message.content.trim();
        res.status(200).json({ answer });

    } catch (error) {
        console.error('API Error:', error);
        res.status(500).json({ error: 'Internal server error: ' + error.message });
    }
};
