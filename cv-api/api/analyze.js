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
        const { vacancyText, turnstileToken, lang = 'en' } = req.body;

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
                model: 'gpt-4o-mini',
                messages: [
                    {
                        role: 'system',
                        content: `You are an expert IT Recruiter helping a candidate analyze how well they fit a specific vacancy. 
            You will be provided with the candidate's CV data and a vacancy description.
            Analyze the compliance and provide a detailed report in JSON format.
            Languages to use for output: ${lang === 'ru' ? 'Russian' : 'English'}.
            
            Return ONLY a JSON object with the following structure:
            {
              "score": number (0-100),
              "pros": string[],
              "cons": string[],
              "strengths": string[],
              "weaknesses": string[],
              "summary": string
            }`
                    },
                    {
                        role: 'user',
                        content: `Candidate CV: ${JSON.stringify(cvContext)}\n\nVacancy Description: ${vacancyText}`
                    }
                ],
                response_format: { type: 'json_object' }
            })
        });

        const data = await response.json();

        if (data.error) {
            console.error('OpenAI Error:', data.error);
            return res.status(500).json({ error: 'AI analysis failed.' });
        }

        const analysis = JSON.parse(data.choices[0].message.content);
        res.status(200).json(analysis);

    } catch (error) {
        console.error('API Error:', error);
        res.status(500).json({ error: 'Internal server error.' });
    }
};
