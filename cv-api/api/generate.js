const REPO_RAW = 'https://raw.githubusercontent.com/vladislav-vasilenko/vladislav-vasilenko.github.io/main/content';

async function fetchText(path) {
    const url = `${REPO_RAW}/${path}`;
    const res = await fetch(url, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Vercel Serverless Function)'
        }
    });
    if (!res.ok) {
        console.error(`Fetch failed for ${url}: ${res.status} ${res.statusText}`);
        return '';
    }
    return res.text();
}

module.exports = async function handler(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    try {
        let question, context, lang, globalContext;
        if (req.method === 'POST') {
            ({ question, context, lang = 'ru', globalContext } = req.body || {});
        } else if (req.method === 'GET') {
            ({ question, context, lang = 'ru', globalContext } = req.query || {});
        } else {
            return res.status(405).json({ error: 'Method not allowed' });
        }

        if (!question) {
            return res.status(400).json({ error: 'Question is missing.' });
        }

        // Fetch CV Data for context
        const cvJson = JSON.parse(await fetchText(`${lang}/cv.json`));
        const about = await fetchText(`${lang}/about.md`);

        // Detailed experience for better answers
        const experience = await Promise.all(
            cvJson.experience.slice(0, 5).map(async (exp) => {
                const description = await fetchText(`${lang}/experience/${exp.id}.md`);
                return { role: exp.role, company: exp.company, description };
            })
        );

        const cvContext = {
            name: cvJson.name,
            title: cvJson.title,
            about,
            experience
        };

        // Call OpenAI
        const response = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
            },
            body: JSON.stringify({
                model: 'gpt-4o-mini',
                messages: [
                    {
                        role: 'system',
                        content: `You are an expert AI Assistant helping a candidate fill out a job application form.
            Your task is to answer the provided QUESTION based on the CANDIDATE'S CV and page CONTEXT.
            Keep the answer professional, concise, and focused on relevant experience.
            If GLOBAL CONTEXT (like job title or company) is provided, tailor your answer toward that position.
            Language: ${lang === 'ru' ? 'Russian' : 'English'}.
            Output should be the answer text ONLY, no markdown, no quotes, no extra meta-text.`
                    },
                    {
                        role: 'user',
                        content: `Candidate CV: ${JSON.stringify(cvContext)}\n\nPage Local Context (labels near field): ${context || 'None'}\n\nGLOBAL context (Page title/Position): ${globalContext || 'None'}\n\nQUESTION: ${question}`
                    }
                ]
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
