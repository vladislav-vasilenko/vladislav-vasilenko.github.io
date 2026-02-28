import type { CVContent } from './i18n';

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function exportPDF(): void {
  window.print();
}

export function exportDOC(cv: CVContent): void {
  const html = `
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><title>${cv.name} — CV</title>
<style>
  body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #1a1a2e; line-height: 1.5; margin: 2cm; }
  h1 { font-size: 20pt; margin-bottom: 2pt; }
  h2 { font-size: 13pt; color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 4pt; margin-top: 16pt; }
  h3 { font-size: 11pt; margin-bottom: 2pt; }
  .subtitle { font-size: 12pt; color: #555; }
  .contact { font-size: 10pt; color: #555; margin-bottom: 12pt; }
  .period { font-size: 10pt; color: #555; float: right; }
  .company { font-size: 10pt; color: #555; }
  .skill { display: inline; background: #e2e8f0; padding: 2pt 6pt; margin: 2pt; font-size: 9pt; }
  ul { margin-top: 4pt; margin-bottom: 8pt; }
  li { font-size: 10pt; color: #555; margin-bottom: 2pt; }
  .exp-block { margin-bottom: 14pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 10pt; }
  .edu-item { margin-bottom: 6pt; }
  .edu-year { font-weight: bold; color: #2563eb; }
</style>
</head><body>
  <h1>${cv.name}</h1>
  <p class="subtitle">${cv.title}</p>
  <p class="contact">${cv.contact.location} &bull; <a href="mailto:${cv.contact.email}">${cv.contact.email}</a> &bull; ${cv.contact.phone} &bull; ${cv.contact.relocation}</p>

  <h2>${cv.labels.about}</h2>
  ${cv.aboutHtml}

  <h2>${cv.labels.employment}</h2>
  <p>${cv.employment}</p>

  <h2>${cv.labels.experience}</h2>
  ${cv.experience.map(exp => `
    <div class="exp-block">
      <span class="period">${exp.period} (${exp.duration})</span>
      <h3>${exp.role}</h3>
      <p class="company">${exp.company}${exp.location ? ` — ${exp.location}` : ''}${exp.industry ? ` (${exp.industry})` : ''}</p>
      ${exp.descriptionHtml}
    </div>
  `).join('')}

  <h2>${cv.labels.education}</h2>
  ${cv.education.map(edu => `
    <div class="edu-item"><span class="edu-year">${edu.year}</span> — <strong>${edu.institution}</strong>: ${edu.program}</div>
  `).join('')}

  <h2>${cv.labels.skills}</h2>
  <p>${cv.techStack.categories.flatMap(c => c.items.map(i => i.name)).map(s => `<span class="skill">${s}</span>`).join(' ')}</p>

  <h2>${cv.labels.languages}</h2>
  <ul>${cv.languages.map(l => `<li>${l}</li>`).join('')}</ul>
</body></html>`;

  const blob = new Blob([html], { type: 'application/msword' });
  downloadBlob(blob, `${cv.name.replace(/\s+/g, '_')}_CV.doc`);
}

export function exportMarkdown(cv: CVContent): void {
  const lines: string[] = [];

  lines.push(`# ${cv.name}`);
  lines.push(`**${cv.title}**\n`);
  lines.push(`${cv.contact.location} | [${cv.contact.email}](mailto:${cv.contact.email}) | ${cv.contact.phone}`);
  lines.push(`${cv.contact.relocation}\n`);

  lines.push(`## ${cv.labels.about}\n`);
  lines.push(cv.aboutMd.trim());
  lines.push('');

  lines.push(`## ${cv.labels.employment}\n`);
  lines.push(cv.employment);
  lines.push('');

  lines.push(`## ${cv.labels.experience}\n`);
  for (const exp of cv.experience) {
    lines.push(`### ${exp.role}`);
    lines.push(`**${exp.company}**${exp.location ? ` — ${exp.location}` : ''}${exp.industry ? ` (${exp.industry})` : ''} | ${exp.period} (${exp.duration})\n`);
    lines.push(exp.descriptionMd.trim());
    lines.push('');
  }

  lines.push(`## ${cv.labels.education}\n`);
  for (const edu of cv.education) {
    lines.push(`- **${edu.year}** — ${edu.institution}: ${edu.program}`);
  }
  lines.push('');

  lines.push(`## ${cv.labels.skills}\n`);
  for (const cat of cv.techStack.categories) {
    const names = cat.items.map(i => i.name).join(', ');
    lines.push(`- **${Object.values(cat.label)[0]}**: ${names}`);
  }
  lines.push('');

  lines.push(`## ${cv.labels.languages}\n`);
  for (const l of cv.languages) {
    lines.push(`- ${l}`);
  }

  const md = lines.join('\n');
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  downloadBlob(blob, `${cv.name.replace(/\s+/g, '_')}_CV.md`);
}

export async function copyAsText(cv: CVContent): Promise<void> {
  const lines: string[] = [];

  lines.push(cv.name);
  lines.push(cv.title);
  lines.push('');
  lines.push(`${cv.contact.location} | ${cv.contact.email} | ${cv.contact.phone}`);
  lines.push(cv.contact.relocation);
  lines.push('');

  lines.push(`--- ${cv.labels.about} ---`);
  lines.push(cv.aboutMd.trim().replace(/\*\*/g, ''));
  lines.push('');

  lines.push(`--- ${cv.labels.experience} ---`);
  for (const exp of cv.experience) {
    lines.push(`${exp.role}`);
    lines.push(`${exp.company}${exp.location ? ` — ${exp.location}` : ''} | ${exp.period} (${exp.duration})`);
    const plainDesc = exp.descriptionMd
      .trim()
      .replace(/\*\*/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/`([^`]+)`/g, '$1');
    lines.push(plainDesc);
    lines.push('');
  }

  lines.push(`--- ${cv.labels.education} ---`);
  for (const edu of cv.education) {
    lines.push(`${edu.year} — ${edu.institution}: ${edu.program}`);
  }
  lines.push('');

  lines.push(`--- ${cv.labels.skills} ---`);
  lines.push(cv.techStack.categories.flatMap(c => c.items.map(i => i.name)).join(', '));
  lines.push('');

  lines.push(`--- ${cv.labels.languages} ---`);
  for (const l of cv.languages) {
    lines.push(l);
  }

  await navigator.clipboard.writeText(lines.join('\n'));
}
