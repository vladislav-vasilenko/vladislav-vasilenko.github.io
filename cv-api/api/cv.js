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

  const experience = await Promise.all(
    cvJson.experience.map(async (exp) => {
      const description = await fetchText(`${lang}/experience/${exp.id}.md`);
      return { ...exp, description };
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
