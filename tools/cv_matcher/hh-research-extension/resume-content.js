// Only rendered professional sections are captured. Contacts and page chrome are excluded.
(async () => {
  "use strict";
  const match = location.pathname.match(/^\/resume\/([a-f0-9]{32,64})\/?$/i);
  if (!match || !(location.hostname === "hh.ru" || location.hostname.endsWith(".hh.ru"))) {
    return {error: "Открой указанное резюме на HH.ru."};
  }
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  // These controls only expand rendered resume text; no edit/submit controls are clicked.
  for (let pass = 0; pass < 4; pass++) {
    const expand = [...document.querySelectorAll('button, a, [role="button"]')]
      .filter((el) => visible(el) && /^(развернуть|показать полностью|показать весь опыт)$/i.test(clean(el.innerText)));
    if (!expand.length) break;
    expand.forEach((el) => el.click());
    await new Promise((resolve) => setTimeout(resolve, 350));
  }
  const collapsed = [...document.querySelectorAll('button, a, [role="button"]')]
    .some((el) => visible(el) && /^(развернуть|показать полностью|показать весь опыт)$/i.test(clean(el.innerText)));
  if (collapsed) return {error: "Часть резюме осталась свёрнутой. Разверни её и повтори сохранение."};
  const title = clean([...document.querySelectorAll('[data-qa="resume-block-title-position"], h1')].find(visible)?.innerText);
  const specs = [
    ["experience", /^(опыт работы|work experience)/i],
    ["skills", /^(навыки|key skills|skills)$/i],
    ["education", /^(образование|education)$/i],
    ["about", /^(о себе|about me)$/i],
    ["courses", /^(повышение квалификации|курсы(?:$|,)|professional development|courses$)/i],
    ["languages", /^(языки|languages)$/i]
  ];
  const headings = [...document.querySelectorAll('h2, h3, h4, h5, h6')].filter(visible);
  const sections = [];
  for (let index = 0; index < headings.length; index++) {
    const heading = headings[index], label = clean(heading.innerText);
    const spec = specs.find(([, pattern]) => pattern.test(label));
    if (!spec) continue;
    // A new heading of the same or higher level ends the section, including non-CV headings.
    const level = Number(heading.tagName.slice(1));
    const next = headings.slice(index + 1).find((h) => Number(h.tagName.slice(1)) <= level ||
      /^(подтверждение навыков|курсы от|курсы по профессии|завершённость|рекомендации)/i.test(clean(h.innerText)));
    if (!next) continue; // Never fall back to reading the entire body/footer.
    const range = document.createRange(); range.setStartAfter(heading); range.setEndBefore(next);
    const walker = document.createTreeWalker(range.commonAncestorContainer, NodeFilter.SHOW_TEXT);
    const pieces = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const parent = node.parentElement;
      if (!parent || !range.intersectsNode(node) || !visible(parent) ||
        parent.closest('button, [role="button"], nav, aside, script, style, input, textarea, select')) continue;
      const value = clean(node.textContent);
      if (value && !/^(редактировать|добавить|развернуть|свернуть)$/i.test(value)) pieces.push(value);
    }
    const value = pieces.join("\n");
    if (value) sections.push({key: spec[0], heading: label, text: value});
  }
  if (!title || !sections.some((s) => s.key === "experience" && s.text.length > 100) ||
    !sections.some((s) => s.key === "skills" || s.key === "about")) {
    return {error: "Не удалось прочитать основные разделы резюме. Проверь вход в HH и загрузку полной страницы."};
  }
  return {resume: {id: match[1].toLowerCase(), title, sections, quality: "full",
    captured_at: new Date().toISOString(), source_url: `https://hh.ru/resume/${match[1]}`}};
})();
