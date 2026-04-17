const REPO_RAW = 'https://raw.githubusercontent.com/vladislav-vasilenko/vladislav-vasilenko.github.io/main/content';

async function fetchText(path) {
    const res = await fetch(`${REPO_RAW}/${path}`);
    if (!res.ok) return '';
    return res.text();
}

module.exports = async function handler(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { vacancyText, turnstileToken, lang = 'en', model = 'gpt-5.4-mini' } = req.body;

        if (!vacancyText || vacancyText.length < 100) {
            return res.status(400).json({ error: 'Vacancy text is too short or missing.' });
        }

        if (vacancyText.length > 10000) {
            return res.status(400).json({ error: 'Vacancy text is too long.' });
        }

        // Validate model
        const allowedModels = ['gpt-5.4-mini', 'gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'gpt-5.4', 'gpt-5-mini-2025-08-07'];
        const selectedModel = allowedModels.includes(model) ? model : 'gpt-5.4-mini';

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

        // Fetch CV Data for context
        const cvJson = JSON.parse(await fetchText(`${lang}/cv.json`));
        const about = await fetchText(`${lang}/about.md`);
        const experience = await Promise.all(
            cvJson.experience.map(async (exp) => {
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
                model: selectedModel,
                messages: [
                    {
                        role: 'system',
                        content: `You are an expert career advisor helping a candidate write a compelling cover letter.
            You will be provided with the candidate's CV data and a vacancy description.
            Create a professional, personalized cover letter that highlights relevant experience and skills.
            Language to use: ${lang === 'ru' ? 'Russian' : 'English'}.

            The cover letter should:
            - Be concise (300-400 words)
            - Have a strong opening that shows enthusiasm
            - Highlight 2-3 most relevant experiences/achievements
            - Demonstrate clear understanding of the role requirements
            - End with a confident call to action
            - Use professional but engaging tone
            - Be tailored specifically to this position

            Return plain text only, no markdown formatting.`
                    },
                    {
                        role: 'user',
                        content: `Candidate CV: ${JSON.stringify(cvContext)}\n\nVacancy Description: ${vacancyText}`
                    }
                ]
            })
        });

        const data = await response.json();

        if (data.error) {
            console.error('OpenAI Error:', data.error);
            return res.status(500).json({ error: 'AI generation failed.' });
        }

        const coverLetter = data.choices[0].message.content.trim();
        res.status(200).json({ coverLetter });

    } catch (error) {
        console.error('API Error:', error);
        res.status(500).json({ error: 'Internal server error.' });
    }
};
