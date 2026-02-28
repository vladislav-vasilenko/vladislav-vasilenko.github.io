const WORKDAY_MAPPINGS = {
    "jobTitle": "workExperience-[INDEX]--jobTitle",
    "company": "workExperience-[INDEX]--companyName",
    "location": "workExperience-[INDEX]--location",
    "description": "workExperience-[INDEX]--roleDescription",
    "currentlyWorkHere": "workExperience-[INDEX]--currentlyWorkHere",
    "startDateMonth": "workExperience-[INDEX]--startDate-dateSectionMonth-input",
    "startDateYear": "workExperience-[INDEX]--startDate-dateSectionYear-input",
    "endDateMonth": "workExperience-[INDEX]--endDate-dateSectionMonth-input",
    "endDateYear": "workExperience-[INDEX]--endDate-dateSectionYear-input"
};

function fillField(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        console.log(`Filled ${id} with ${value}`);
        return true;
    }
    return false;
}

function fillCheckbox(id, checked) {
    const el = document.getElementById(id);
    if (el && el.type === 'checkbox') {
        if (el.checked !== checked) {
            el.click();
        }
        return true;
    }
    return false;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "autofill_experience") {
        const data = request.data;
        let filledCount = 0;

        data.forEach((exp, index) => {
            // Workday usually indexes from 187, 188 etc. or 1, 2, 3 in IDs. 
            // We'll search for elements that match the pattern.
            const prefix = `workExperience-`;
            const inputs = document.querySelectorAll(`input[id^="${prefix}"], textarea[id^="${prefix}"]`);

            // Attempt to find fields by partial ID match for this index
            // (This is a simplified version, real Workday uses dynamic numeric IDs)
            // For the demo/user provided HTML, we'll try to find by specific ID patterns.

            // In the user's HTML: workExperience-187--jobTitle
            // We need a way to map our data index to the DOM index.

            const sections = document.querySelectorAll('.css-1obf64m'); // Experience panels
            if (sections[index]) {
                const jobInput = sections[index].querySelector('input[name="jobTitle"]');
                const companyInput = sections[index].querySelector('input[name="companyName"]');
                const locationInput = sections[index].querySelector('input[name="location"]');
                const descTextarea = sections[index].querySelector('textarea');

                if (jobInput) { jobInput.value = exp.role; jobInput.dispatchEvent(new Event('input', { bubbles: true })); }
                if (companyInput) { companyInput.value = exp.company; companyInput.dispatchEvent(new Event('input', { bubbles: true })); }
                if (locationInput) { locationInput.value = exp.location || ""; locationInput.dispatchEvent(new Event('input', { bubbles: true })); }
                if (descTextarea) { descTextarea.value = exp.description; descTextarea.dispatchEvent(new Event('input', { bubbles: true })); }

                filledCount++;
            }
        });

        sendResponse({ status: "success", filled: filledCount });
    }
});
