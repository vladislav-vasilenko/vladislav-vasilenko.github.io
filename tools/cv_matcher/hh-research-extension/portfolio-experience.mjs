/* Reuse exactly the same HH experience parser as the local document viewer. */
import fs from 'node:fs';
import '../archive-web/resume-profile-core.js';
const text = fs.readFileSync(0, 'utf8');
if (text.length > 250000) throw Error('Experience input too large');
const parsed = globalThis.ResumeProfileCore.experience(text);
process.stdout.write(JSON.stringify(parsed));
