function fillInput(el, value) {
    if (!el) return false;
    const nativeSetterDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')
        || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
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

async function handleAIFill() {
    const el = document.activeElement;
    if (!el || (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA')) return;

    // 1. Try to find question context
    let context = "";
    let question = "";

    // Priority 1: User selection
    const selection = window.getSelection().toString().trim();
    if (selection) {
        question = selection;
        console.log("[AutoFill AI] Using selected text as question:", question);
    } else {
        // Priority 2: Automatic extraction
        // Look for label or preceding text
        const label = document.querySelector(`label[for="${el.id}"]`);
        if (label) context += label.innerText + " ";

        // Look for aria-labelledby
        const ariaLabelledBy = el.getAttribute('aria-labelledby');
        if (ariaLabelledBy) {
            const labeled = document.getElementById(ariaLabelledBy);
            if (labeled) context += labeled.innerText + " ";
        }

        // Look for nearby parent headings or containers
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

    const originalValue = el.value;
    fillInput(el, "... ✨ Generating answer with AI ...");

    try {
        const response = await fetch('https://vladislav-vasilenko-github-io.vercel.app/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                context: context,
                lang: document.documentElement.lang === 'ru' ? 'ru' : 'en'
            })
        });

        if (!response.ok) throw new Error("API call failed");
        const data = await response.json();

        if (data.answer) {
            fillInput(el, data.answer);
        } else {
            fillInput(el, originalValue);
            alert("AI could not generate an answer.");
        }
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
        }
        return true;
    });
}
