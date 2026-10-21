/* Company drafts use the shared queue, independently of the managed HH tab.
   Only an explicitly captured, still-open activeTab can receive approved text. */
let careerWorkflowBusy = false;
async function careerInspect(tabId, config) {
    if (config)
        await chrome.scripting.executeScript({ target: { tabId }, func: c => { globalThis.__careerFieldAction = c; }, args: [config] });
    const snapshot = await wfScript(tabId, ['board-core.js', 'board-adapters.js', 'board-widget-core.js', 'career-form-core.js', 'career-form-content.js']);
    if (snapshot?.error)
        throw Object.assign(Error(snapshot.error), { code: snapshot.code, retryable: snapshot.retryable === true });
    if (!snapshot?.state)
        throw Error('Не удалось прочитать анкету компании. Откройте её и передайте заново.');
    return snapshot;
}
// The SQLite receipt is idempotent. A full optional browser cache must not
// prevent delivery of the outcome of an already-approved transfer.
async function careerReceipt(command, worker, result) {
    const key = 'career_receipt_' + command.id, record = { [key]: { command_id: command.id, worker_id: worker, result } };
    let journal;
    try {
        await chrome.storage.local.set(record);
        journal = chrome.storage.local;
    }
    catch {
        try {
            await chrome.storage.session.set(record);
            journal = chrome.storage.session;
        }
        catch { }
    }
    await workflowCall({ op: 'career_fill_result', command_id: command.id, worker_id: worker, result });
    if (journal)
        await journal.remove(key);
}
// One capture path for the website queue and the in-page widget. Full vacancy
// text is committed directly to SQLite, not duplicated into a full Chrome cache.
async function careerCaptureForm(tab, ctx, { appId, prepare = false } = {}) {
    const profile = prepare ? await workflowCall({ op: 'candidate_profile' }) : null;
    const snapshot = await careerInspect(tab.id, prepare ? { action: 'prepare_profile', resume: /^https?:\/\//i.test(ctx.resume_url || ''), portfolio: !!profile?.values?.portfolio_url } : undefined);
    if (snapshot.vacancy_id !== ctx.vacancy.id)
        throw Error('Открылась анкета другой вакансии.');
    if ((await chrome.tabs.get(tab.id)).url !== tab.url || snapshot.source_url !== tab.url)
        throw Error('Страница изменилась во время чтения формы.');
    const detail = await wfScript(tab.id, ['board-core.js', 'board-adapters.js', 'board-content.js']);
    if (detail?.blocked)
        throw Error(detail.warning || 'Источник ограничил доступ. Проверьте страницу в Chrome.');
    const fresh = detail?.page_kind === 'detail' && detail.vacancies?.find(v => v.id === snapshot.vacancy_id && v.description_quality === 'full' && !v.archived);
    if (!fresh)
        throw Error('Анкета найдена, но полное описание вакансии не подтверждено. Обновите страницу и сохраните полное описание.');
    if ((await chrome.tabs.get(tab.id)).url !== tab.url)
        throw Error('Страница изменилась при проверке вакансии.');
    fresh.archived = false;
    fresh.availability_checked_at = new Date().toISOString();
    const synced = await workflowCallSync(tab.id, fresh);
    if (synced.rejected?.length)
        throw Error('Свежая версия вакансии не сохранена: ' + (synced.rejected[0].error || 'проверьте сервис.'));
    const result = await workflowCall(appId ? { op: 'career_form_for_application', app_id: appId, snapshot } : { op: 'career_form', resume_id: ctx.resume_id, resume_hash: ctx.resume_hash, vacancy_id: snapshot.vacancy_id, goal: ctx.goal || '', snapshot });
    const id = appId || result.id;
    const { career_form_bindings = {} } = await chrome.storage.session.get('career_form_bindings');
    career_form_bindings[id] = { tab_id: tab.id, source_url: tab.url, resume_id: ctx.resume_id, resume_hash: ctx.resume_hash };
    await chrome.storage.session.set({ career_form_bindings });
    return { result, snapshot, app_id: id };
}
async function workflowCallSync(tabId, fresh) {
    return LocalResumeService.request('/archive/sync', { client_id: 'career-form-' + tabId, records: [await ArchiveSyncCore.record('vacancy', fresh.id, fresh)] });
}
async function careerOpenForm(command) {
    const ctx = command.application.context, url = command.payload.url, target = JobBoards.identity(url);
    if (ctx.channel !== 'career' || !target || target.id !== ctx.vacancy.id)
        throw Error('Не совпала вакансия для открытия формы.');
    const origin = new URL(url).origin + '/*';
    if (!await chrome.permissions.contains({ origins: [origin] }))
        throw Error('Разрешите чтение этого карьерного сайта в параметрах расширения. Затем повторите открытие формы.');
    const tabs = await chrome.tabs.query({}), found = tabs.find(t => JobBoards.identity(t.url)?.id === ctx.vacancy.id && JobBoardAdapters.sameSource(t.url, url)), tab = found || await chrome.tabs.create({ url: 'about:blank', active: true });
    if (activeJobs.has(tab.id))
        throw Error('Вкладка этой вакансии занята сбором. Дождитесь окончания чтения и повторите.');
    activeJobs.add(tab.id);
    try {
        if (!found)
            await navigate(tab.id, url);
        else
            await chrome.tabs.update(tab.id, { active: true });
        let lastError;
        for (let n = 0; n < 8; n++) {
            try {
                const current = await chrome.tabs.get(tab.id);
                await careerCaptureForm(current, ctx, { appId: command.app_id, prepare: true });
                return { state: 'complete', note: 'Форма открыта и прочитана. Проверьте ответы и разрешите перенос полей. Отклик не отправлен.' };
            }
            catch (error) {
                lastError = error;
                if (!error.retryable)
                    throw error;
            }
            if (n < 7)
                await new Promise(r => setTimeout(r, 300));
        }
        throw lastError;
    }
    finally {
        activeJobs.delete(tab.id);
    }
}
async function careerWorkflowPulse() {
    if (careerWorkflowBusy)
        return;
    careerWorkflowBusy = true;
    let command, worker, tabId, finished = false;
    try {
        for (const storage of [chrome.storage.local, chrome.storage.session]) {
            const saved = await storage.get(null);
            for (const [key, receipt] of Object.entries(saved))
                if (key.startsWith('career_receipt_')) {
                    await workflowCall({ op: 'career_fill_result', ...receipt });
                    await storage.remove(key);
                }
        }
        const session = await chrome.storage.session.get(['career_form_bindings', 'career_worker_id']);
        const bindings = session.career_form_bindings || {};
        worker = session.career_worker_id || crypto.randomUUID();
        await chrome.storage.session.set({ career_worker_id: worker });
        const opening = (await workflowCall({ op: 'next', worker_id: worker, kinds: ['career_open'] })).command;
        if (opening) {
            let result;
            try {
                result = await careerOpenForm(opening);
            }
            catch (error) {
                result = { state: 'needs_input', note: error.message };
            }
            await workflowCall({ op: 'result', command_id: opening.id, worker_id: worker, result });
            return;
        }
        if (!Object.keys(bindings).length)
            return;
        // Do not take tasks whose original authorized tab was closed or navigated.
        const live = {};
        for (const [id, b] of Object.entries(bindings))
            try {
                const tab = await chrome.tabs.get(b.tab_id);
                if (tab.url === b.source_url && !activeJobs.has(b.tab_id))
                    live[id] = b;
            }
            catch { }
        if (!Object.keys(live).length)
            return;
        command = (await workflowCall({ op: 'next', worker_id: worker, kinds: ['career_fill'], app_ids: Object.keys(live) })).command;
        if (!command)
            return;
        const binding = live[command.app_id];
        if (!binding)
            throw Error('Исходная вкладка компании закрыта или перешла на другую страницу. Откройте анкету и передайте её заново.');
        tabId = binding.tab_id;
        activeJobs.add(tabId);
        const ctx = command.application.context;
        if (ctx.channel !== 'career' || ctx.resume_id !== binding.resume_id || ctx.resume_hash !== binding.resume_hash)
            throw Error('Привязка CV изменилась. Прочитайте анкету заново.');
        const before = await careerInspect(tabId);
        const { resume_bundle } = await chrome.storage.local.get('resume_bundle');
        const localCV = resume_bundle?.resumes?.find(r => r.id === ctx.resume_id);
        if (localCV && localCV.content_hash !== ctx.resume_hash)
            throw Error('CV в расширении изменилось. Перенос остановлен.');
        if ((await chrome.tabs.get(tabId)).url !== before.source_url)
            throw Error('Страница изменилась. Прочитайте анкету заново.');
        const intent = await workflowCall({ op: 'career_fill_claim', command_id: command.id, worker_id: worker, fingerprint: before.fingerprint });
        const result = await careerInspect(tabId, { action: 'fill', vacancy_id: ctx.vacancy.id, source_url: intent.source_url, fingerprint: intent.form_fingerprint, answers: intent.answers });
        finished = true;
        await careerReceipt(command, worker, result);
    }
    catch (error) {
        if (command && !finished)
            try {
                await careerReceipt(command, worker, { state: 'failed', note: error.message });
            }
            catch { }
    }
    finally {
        if (tabId !== undefined)
            activeJobs.delete(tabId);
        careerWorkflowBusy = false;
    }
}
if (chrome.alarms?.create) {
    (async () => { if (!chrome.alarms.get || !await chrome.alarms.get('career-workflow'))
        await chrome.alarms.create('career-workflow', { periodInMinutes: 1 }); })().catch(() => { });
    chrome.alarms.onAlarm.addListener(a => { if (a.name === 'career-workflow')
        careerWorkflowPulse(); });
    careerWorkflowPulse();
}
