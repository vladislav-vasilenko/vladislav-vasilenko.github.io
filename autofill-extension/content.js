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
    // Find all workExperience section IDs present in the DOM
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

    // Job Title
    const jobTitle = document.getElementById(`${prefix}--jobTitle`);
    if (fillInput(jobTitle, exp.role)) filled++;

    // Company
    const company = document.getElementById(`${prefix}--companyName`);
    if (fillInput(company, exp.company)) filled++;

    // Location
    const location = document.getElementById(`${prefix}--location`);
    if (fillInput(location, exp.location || '')) filled++;

    // Role Description
    const desc = document.getElementById(`${prefix}--roleDescription`);
    if (fillInput(desc, exp.description || '')) filled++;

    // Start Date
    const startMonth = document.getElementById(`${prefix}--startDate-dateSectionMonth-input`);
    const startYear = document.getElementById(`${prefix}--startDate-dateSectionYear-input`);
    if (exp.startMonth && fillInput(startMonth, String(exp.startMonth))) filled++;
    if (exp.startYear && fillInput(startYear, String(exp.startYear))) filled++;

    // End Date
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

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'autofill_experience') {
        const data = request.data;
        const sectionIds = findWorkdaySections();
        let filledSections = 0;

        console.log(`[AutoFill] Found ${sectionIds.length} Workday sections, have ${data.length} experience entries`);

        sectionIds.forEach((sectionId, index) => {
            if (index < data.length) {
                const count = fillSection(sectionId, data[index]);
                console.log(`[AutoFill] Section ${sectionId}: filled ${count} fields with "${data[index].role}" @ ${data[index].company}`);
                if (count > 0) filledSections++;
            }
        });

        sendResponse({ status: 'success', filled: filledSections });
    }
});
