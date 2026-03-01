const CV_API_URL = 'https://vladislav-vasilenko-github-io.vercel.app/api/cv?lang=en';

let cvData = null;

function parsePeriod(periodStr) {
    if (!periodStr) return {};
    // Example: "Dec 2025 — Present" or "Sep 2025 — Dec 2025"
    const months = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    };

    const parts = periodStr.split('—').map(s => s.trim());
    const startExpr = parts[0].split(' ');

    const result = {
        startMonth: months[startExpr[0]] || null,
        startYear: startExpr[1] || null,
        currentlyWorkHere: parts[1] === 'Present' || parts[1] === 'настоящее время'
    };

    if (!result.currentlyWorkHere && parts[1]) {
        const endExpr = parts[1].split(' ');
        result.endMonth = months[endExpr[0]] || null;
        result.endYear = endExpr[1] || null;
    }

    return result;
}

async function loadCV() {
    const statusEl = document.getElementById('status');
    statusEl.textContent = 'Loading CV data...';
    statusEl.style.color = 'var(--accent)';

    try {
        const res = await fetch(CV_API_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        cvData = await res.json();

        // Enrich with parsed dates
        cvData.experience = cvData.experience.map(exp => ({
            ...exp,
            ...parsePeriod(exp.period)
        }));

        statusEl.textContent = `Loaded ${cvData.experience.length} positions`;
        statusEl.style.color = '#10b981';
        document.getElementById('autofill-btn').disabled = false;
    } catch (err) {
        statusEl.textContent = `Failed to load CV: ${err.message}`;
        statusEl.style.color = '#ef4444';
    }
}

document.getElementById('autofill-btn').disabled = true;
loadCV();

document.getElementById('autofill-btn').addEventListener('click', async () => {
    if (!cvData) return;

    const statusEl = document.getElementById('status');
    statusEl.textContent = 'Injecting...';
    statusEl.style.color = 'var(--accent)';

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab) throw new Error("No active tab found");

        console.log("Starting injection into tab:", tab.id);

        const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            args: [cvData.experience, cvData.education],
            func: async (experienceData, educationData) => {
                const sleep = (ms) => new Promise(res => setTimeout(res, ms));
                console.log("[AutoFill] Injected script started", { exp: experienceData.length, edu: educationData.length });

                function fillInput(el, value, label = "") {
                    if (!el) {
                        if (label) console.warn(`[AutoFill] Element NOT FOUND: ${label}`);
                        return false;
                    }
                    try {
                        const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
                        if (desc && desc.set) desc.set.call(el, value);
                        else el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                        console.log(`[AutoFill] Filled ${label} (${el.tagName}): "${String(value).substring(0, 30)}..."`);
                        return true;
                    } catch (e) {
                        console.error(`[AutoFill] Error filling ${label}:`, e);
                        return false;
                    }
                }

                function getIds(prefix) {
                    const selector = prefix === 'workExperience'
                        ? 'input[id*="workExperience-"][id$="--jobTitle"]'
                        : 'input[id*="education-"][id$="--schoolName"]';
                    return Array.from(document.querySelectorAll(selector))
                        .map(el => {
                            const m = el.id.match(new RegExp(`${prefix}-(\\d+)`));
                            return m ? m[1] : null;
                        })
                        .filter(v => v !== null);
                }

                async function prepareSections(headingText, targetCount, prefix) {
                    let ids = getIds(prefix);
                    console.log(`[AutoFill] ${headingText} sections: found ${ids.length}, target ${targetCount}`);

                    if (ids.length >= targetCount) {
                        console.log(`[AutoFill] ${headingText} target already met (${ids.length}/${targetCount}). Skipping "Add".`);
                        return ids;
                    }

                    for (let attempt = 0; attempt < 15 && ids.length < targetCount; attempt++) {
                        const addBtn = Array.from(document.querySelectorAll('button[data-automation-id="add-button"]'))
                            .find(btn => {
                                const txt = (btn.innerText + " " + (btn.getAttribute('aria-label') || "")).toLowerCase();
                                return txt.includes('add') && (txt.includes('another') || txt.includes(headingText.toLowerCase().split(' ')[0]));
                            });

                        if (addBtn) {
                            console.log(`[AutoFill] Clicking "Add" for ${headingText} (Current: ${ids.length}, Target: ${targetCount})`);
                            addBtn.click();
                            await sleep(2000); // Wait for React to render new section
                            ids = getIds(prefix);
                        } else {
                            console.warn(`[AutoFill] Add button for ${headingText} not found`);
                            break;
                        }
                    }
                    return ids;
                }

                // 1. Fill Experience
                const expIds = await prepareSections("Work Experience", experienceData.length, "workExperience");
                let expFilled = 0;
                for (let i = 0; i < expIds.length; i++) {
                    if (i >= experienceData.length) break;
                    const sid = expIds[i];
                    const exp = experienceData[i];
                    const p = `workExperience-${sid}`;
                    console.log(`[AutoFill] ---> Filling Experience Block ${i + 1} (SID: ${sid})`);

                    let f = 0;
                    if (fillInput(document.getElementById(`${p}--jobTitle`), exp.role, `${p}--jobTitle`)) f++;
                    if (fillInput(document.getElementById(`${p}--companyName`), exp.company, `${p}--companyName`)) f++;
                    if (fillInput(document.getElementById(`${p}--location`), exp.location || '', `${p}--location`)) f++;
                    const description = exp.description || exp.desc || '';
                    if (fillInput(document.getElementById(`${p}--roleDescription`), description, `${p}--roleDescription`)) f++;

                    if (exp.startMonth) fillInput(document.getElementById(`${p}--startDate-dateSectionMonth-input`), String(exp.startMonth), 'startMonth');
                    if (exp.startYear) fillInput(document.getElementById(`${p}--startDate-dateSectionYear-input`), String(exp.startYear), 'startYear');

                    if (!exp.currentlyWorkHere) {
                        if (exp.endMonth) fillInput(document.getElementById(`${p}--endDate-dateSectionMonth-input`), String(exp.endMonth), 'endMonth');
                        if (exp.endYear) fillInput(document.getElementById(`${p}--endDate-dateSectionYear-input`), String(exp.endYear), 'endYear');
                    } else {
                        const cb = document.getElementById(`${p}--currentlyWorkHere`);
                        if (cb && !cb.checked) {
                            console.log(`[AutoFill] Checking "Currently Work Here" for ${sid}`);
                            cb.click();
                        }
                    }
                    if (f > 0) expFilled++;
                    await sleep(400); // Breathe
                }

                // 2. Fill Education
                const eduIds = await prepareSections("Education", educationData.length, "education");
                let eduFilled = 0;
                for (let i = 0; i < eduIds.length; i++) {
                    if (i >= educationData.length) break;
                    const sid = eduIds[i];
                    const edu = educationData[i];
                    const p = `education-${sid}`;
                    console.log(`[AutoFill] ---> Filling Education Block ${i + 1} (SID: ${sid})`);

                    let f = 0;
                    if (fillInput(document.getElementById(`${p}--schoolName`), edu.institution, `${p}--schoolName`)) f++;
                    if (fillInput(document.getElementById(`${p}--fieldOfStudy`), edu.program, `${p}--fieldOfStudy`)) f++;
                    if (f > 0) eduFilled++;
                    await sleep(400);
                }

                return { expFilled, expTotal: expIds.length, eduFilled, eduTotal: eduIds.length };
            }
        });

        const injectionResult = results[0]?.result;
        if (injectionResult) {
            statusEl.textContent = `Done! Exp: ${injectionResult.expFilled}/${injectionResult.expTotal}, Edu: ${injectionResult.eduFilled}/${injectionResult.eduTotal}`;
            statusEl.style.color = '#10b981';
        } else {
            statusEl.textContent = "Injection completed with no result";
        }
    } catch (err) {
        console.error("Injection error:", err);
        statusEl.textContent = 'Error: ' + err.message;
        statusEl.style.color = '#ef4444';
    }
});
