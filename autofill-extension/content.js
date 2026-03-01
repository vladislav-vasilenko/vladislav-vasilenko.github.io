function fillInput(el, value) {
    if (!el) return false;

    // Determine the correct prototype based on element type to avoid "Illegal invocation"
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const nativeSetterDesc = Object.getOwnPropertyDescriptor(proto, 'value');

    if (nativeSetterDesc && nativeSetterDesc.set) {
        nativeSetterDesc.set.call(el, value);
    } else {
        el.value = value;
    }

    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
    return true;
}

function findWorkdaySections() {
    const allInputs = document.querySelectorAll('[id^="workExperience-"]');
    const sectionIds = new Set();
    allInputs.forEach(el => {
        const match = el.id.match(/^workExperience-(\d+)/);
        if (match) sectionIds.add(match[1]);
    });
    return [...sectionIds].sort((a, b) => parseInt(a) - parseInt(b));
}

function fillSection(sectionId, exp) {
    const prefix = `workExperience-${sectionId}`;
    let filled = 0;
    const jobTitle = document.getElementById(`${prefix}--jobTitle`);
    if (fillInput(jobTitle, exp.role)) filled++;
    const company = document.getElementById(`${prefix}--companyName`);
    if (fillInput(company, exp.company)) filled++;
    const location = document.getElementById(`${prefix}--location`);
    if (fillInput(location, exp.location || '')) filled++;
    const desc = document.getElementById(`${prefix}--roleDescription`);
    if (fillInput(desc, exp.description || '')) filled++;
    const startMonth = document.getElementById(`${prefix}--startDate-dateSectionMonth-input`);
    const startYear = document.getElementById(`${prefix}--startDate-dateSectionYear-input`);
    if (exp.startMonth && fillInput(startMonth, String(exp.startMonth))) filled++;
    if (exp.startYear && fillInput(startYear, String(exp.startYear))) filled++;
    if (exp.currentlyWorkHere) {
        const checkbox = document.querySelector(`[data-fkit-id="${prefix}--currentlyWorkHere"] input[type="checkbox"]`)
            || document.getElementById(`${prefix}--currentlyWorkHere`);
        if (checkbox && !checkbox.checked) {
            checkbox.click();
            filled++;
        }
    } else {
        const endMonth = document.getElementById(`${prefix}--endDate-dateSectionMonth-input`);
        const endYear = document.getElementById(`${prefix}--endDate-dateSectionYear-input`);
        if (exp.endMonth && fillInput(endMonth, String(exp.endMonth))) filled++;
        if (exp.endYear && fillInput(endYear, String(exp.endYear))) filled++;
    }
    return filled;
}

function getGlobalContext() {
    let globalInfo = "";

    // 1. Page Title
    if (document.title) globalInfo += `Page Title: ${document.title}. `;

    // 2. Main Heading (often the job title)
    const h1 = document.querySelector('h1');
    if (h1) globalInfo += `Main Heading: ${h1.innerText}. `;

    // 3. Specific selectors for job sites (Yandex, Workday)
    // Yandex Jobs specific
    const yandexJob = document.querySelector('.JobHeader-Title, .vacancy-title');
    if (yandexJob) globalInfo += `Vacancy: ${yandexJob.innerText}. `;

    // Workday specific
    const workdayJob = document.querySelector('[data-automation-id="jobPostingHeader"]');
    if (workdayJob) globalInfo += `Position: ${workdayJob.innerText}. `;

    return globalInfo.trim();
}

async function handleAIFill(manualQuestion = null) {
    const el = document.activeElement;
    if (!el || (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA')) {
        console.warn("[AutoFill AI] No active input/textarea found.");
        return;
    }

    // 1. Find question context
    let context = "";
    let question = "";

    if (manualQuestion) {
        question = manualQuestion;
        console.log("[AutoFill AI] Using manual question:", question);
    } else {
        // Priority 1: User selection
        const selection = window.getSelection().toString().trim();
        if (selection) {
            question = selection;
            console.log("[AutoFill AI] Using selected text as question:", question);
        } else {
            // Priority 2: Automatic extraction
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) context += label.innerText + " ";

            const ariaLabelledBy = el.getAttribute('aria-labelledby');
            if (ariaLabelledBy) {
                const labeled = document.getElementById(ariaLabelledBy);
                if (labeled) context += labeled.innerText + " ";
            }

            let parent = el.parentElement;
            for (let i = 0; i < 5 && parent; i++) {
                const labels = parent.querySelectorAll('h1, h2, h3, h4, label, .QuestionLabel');
                labels.forEach(l => {
                    if (l !== label && !context.includes(l.innerText)) context += l.innerText + " ";
                });
                parent = parent.parentElement;
            }

            const placeholder = el.placeholder || "";
            question = context.trim() || placeholder || "Tell about yourself";
            console.log("[AutoFill AI] Automatic context found:", question);
        }
    }

    const originalValue = el.value;
    fillInput(el, "... ✨ Generating answer with AI ...");

    try {
        chrome.runtime.sendMessage({
            action: 'generate_ai_answer',
            data: {
                question: question,
                context: context,
                globalContext: getGlobalContext(),
                lang: document.documentElement.lang === 'ru' ? 'ru' : 'en'
            }
        }, (response) => {
            if (response && response.success && response.data.answer) {
                fillInput(el, response.data.answer);
            } else {
                fillInput(el, originalValue);
                const error = response ? (response.error || "AI could not generate an answer.") : "No response from background.";
                alert("Smart Fill error: " + error);
            }
        });
    } catch (err) {
        console.error("[AutoFill AI] Error:", err);
        fillInput(el, originalValue);
        alert("Smart Fill error: " + err.message);
    }
}

if (!window.__autofillRegistered) {
    window.__autofillRegistered = true;
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === 'autofill_experience') {
            const data = request.data;
            const sectionIds = findWorkdaySections();
            let filledSections = 0;
            sectionIds.forEach((sectionId, index) => {
                if (index < data.length) {
                    const count = fillSection(sectionId, data[index]);
                    if (count > 0) filledSections++;
                }
            });
            sendResponse({ status: 'success', filled: filledSections });
        } else if (request.action === 'trigger_ai_fill') {
            handleAIFill();
        } else if (request.action === 'trigger_custom_ai_fill') {
            handleAIFill(request.question);
        }
        return true;
    });
}
