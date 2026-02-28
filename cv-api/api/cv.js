const REPO_RAW = 'https://raw.githubusercontent.com/vladislav-vasilenko/vladislav-vasilenko.github.io/main/content';

async function fetchText(path) {
  const res = await fetch(`${REPO_RAW}/${path}`);
  if (!res.ok) return '';
  return res.text();
}

module.exports = async function handler(req, res) {
  const lang = req.query.lang === 'ru' ? 'ru' : 'en';

  const cvJson = JSON.parse(await fetchText(`${lang}/cv.json`));
  const about = await fetchText(`${lang}/about.md`);
  const productAbout = await fetchText(`${lang}/product-about.md`);

  const MONTHS = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 };

  function parsePeriod(period) {
    const parts = period.split('—').map(s => s.trim());
    const [startMonth, startYear] = parts[0].split(' ');
    const result = { startMonth: MONTHS[startMonth] || 0, startYear: parseInt(startYear) || 0 };
    if (parts[1] === 'Present') {
      result.endMonth = 0;
      result.endYear = 0;
      result.currentlyWorkHere = true;
    } else {
      const [endMonth, endYear] = parts[1].split(' ');
      result.endMonth = MONTHS[endMonth] || 0;
      result.endYear = parseInt(endYear) || 0;
      result.currentlyWorkHere = false;
    }
    return result;
  }

  const experience = await Promise.all(
    cvJson.experience.map(async (exp) => {
      const description = await fetchText(`${lang}/experience/${exp.id}.md`);
      const dates = parsePeriod(exp.period);
      return { ...exp, description, ...dates };
    })
  );

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=60');

  res.json({
    name: cvJson.name,
    title: cvJson.title,
    productTitle: cvJson.productTitle,
    contact: cvJson.contact,
    employment: cvJson.employment,
    about,
    productAbout,
    experience,
    education: cvJson.education,
    languages: cvJson.languages,
  });
}
