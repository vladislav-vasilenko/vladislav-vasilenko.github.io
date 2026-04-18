export const maxDuration = 60; // Allow function to run up to 60s

export default async function handler(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') {
        return res.status(200).end();
    }

    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    try {
        const { vacancyText, cvText } = req.body;
        const apiSecret = req.headers.authorization;
        
        // Basic Security Check
        if (process.env.API_SECRET && apiSecret !== `Bearer ${process.env.API_SECRET}`) {
           return res.status(401).json({ error: 'Unauthorized: Invalid API_SECRET' });
        }
        
        if (!vacancyText || !cvText) {
            return res.status(400).json({ error: 'Missing vacancy or cv text' });
        }
        
        const systemPrompt = `You are a FAANG-level ATS Recruiter AI. 
Evaluate the candidate's Resume against the provided Job Description.

1. Determine the match percentage.
2. Identify critical missing keywords.
3. Identify 'matched_keywords': technical skills and competencies from the Resume that are explicitly or strongly implicitly requested in the Job Description.
4. Provide brief reasoning.
5. Categorize the vacancy into one of the following domains ('sphere'): 'GenAI / LLM', 'Computer Vision', 'ML / Data Science', 'Audio / Speech', 'Backend', 'Mobile', 'Product / Management'.
6. Provide 'adapted_bullets': rewrite 2-3 specific bullet points from the candidate's actual experience to perfectly align with the vacancy's specific terminology and missing keywords. Do NOT invent new experience, just re-frame their existing technical achievements using the language of the Job Description. Output these clearly in Russian.

Return ONLY a JSON object with the exact following structure:
{
  "ats_score_percentage": number (0-100),
  "sphere": "string",
  "matched_keywords": string[],
  "missing_keywords": string[],
  "reasoning": "string",
  "adapted_bullets": string[],
  "is_good_match": boolean
}`;

        const response = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
            },
            body: JSON.stringify({
                model: 'gpt-5.4-mini',
                messages: [
                    { role: 'system', content: systemPrompt },
                    { role: 'user', content: `Job Description:\n${vacancyText}\n\nCandidate Resume:\n${cvText}` }
                ],
                response_format: { type: 'json_object' }
            })
        });
        
        const data = await response.json();
        if (data.error) throw new Error(data.error.message || 'OpenAI API Error');
        
        const analysis = JSON.parse(data.choices[0].message.content);
        res.status(200).json(analysis);
    } catch (e) {
        console.error('API Error:', e);
        res.status(500).json({ error: 'Internal Server Error' });
    }
}
