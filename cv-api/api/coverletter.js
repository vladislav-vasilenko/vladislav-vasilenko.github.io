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
        const { 
            vacancyText, 
            matchedKeywords = [], 
            sphere = 'General',
            turnstileToken, 
            lang = 'en', 
            model = 'gpt-5.4-mini' 
        } = req.body;

        if (!vacancyText || vacancyText.length < 100) {
            return res.status(400).json({ error: 'Vacancy text is too short or missing.' });
        }
        
        // ... (model validation and Turnstile verify code) ...

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
                        content: `You are an expert career advisor and technical recruiter. 
            Your goal is to write a highly personalized, high-conversion cover letter.
            
            Context:
            - Domain: ${sphere}
            - Key Matched Skills: ${matchedKeywords.join(', ')}
            - Language: ${lang === 'ru' ? 'Russian' : 'English'}

            Guidelines:
            1. Use the matched skills to bridge the candidate's experience with the specific JD.
            2. Mention 2-3 specific technical achievements from the CV that align with the vacancy.
            3. Tone: Professional, confident, but not arrogant. Show genuine interest in the company's product/tech.
            4. Structure: 
               - Hook: Why this role? 
               - Body: Why you? (Evidence-based matching)
               - Closing: Call to action.
            5. Length: 250-350 words.

            Format: Return ONLY the text of the letter. No markdown, no "Dear Hiring Manager" placeholders if you can derive the context.`
                    },
                    {
                        role: 'user',
                        content: `Candidate Record: ${JSON.stringify(cvContext)}\n\nJob description: ${vacancyText}`
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
