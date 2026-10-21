'use strict';
const Flow = (() => {
    let current = null, chosen = null, timer = null, epoch = 0;
    const letterPreferences = new Map();
    let stages = {}, workStatuses = {}, listMode = 'active';
    function fillFilter(id, values) { const select = $(id), old = select.value; if ([...select.options].slice(1).map(o => o.value).join('|') === Object.keys(values).join('|'))
        return; select.replaceChildren(select.options[0]); for (const [key, label] of Object.entries(values)) {
        const o = make('option', '', label);
        o.value = key;
        select.append(o);
    } select.value = old; }
    const labels = { fill_approved: 'Перенос разрешён', filling: 'Заполняется форма', fields_filled: 'Поля заполнены · отклик не отправлен', superseded: 'Предыдущий контекст', queued: 'Подготовка', submitted: 'Отправлен', viewed: 'Просмотрен', invited: 'Приглашение', rejected: 'Отказ', withdrawn: 'Отозван', draft: 'Черновик', approved: 'Разрешён', needs_approval: 'Нужно разрешение', needs_input: 'Нужны ваши данные', sending: 'Отправляется', uncertain: 'Нужна сверка с HH' };
    const call = (op, data = {}) => api('workflow', { op, ...data }, 150000);
    const button = (text, fn, cls = 'secondary') => { const b = make('button', cls, text); b.onclick = async () => { b.disabled = true; try {
        await fn();
    }
    catch (e) {
        notice(e.message);
    }
    finally {
        b.disabled = false;
    } }; return b; };
    const text = (name, value, rows = 4) => { const l = make('label', 'flowLabel', name), t = make('textarea'); t.rows = rows; t.value = value || ''; l.append(t); return [l, t]; };
    function section(title) { const s = make('section', 'flowSection'); s.append(make('h3', '', title)); return s; }
    async function list() {
        const data = await api('workflow');
        stages = data.crm_stages;
        workStatuses = data.work_statuses;
        fillFilter('flowStageFilter', stages);
        fillFilter('flowWorkFilter', workStatuses);
        $('flowList').replaceChildren();
        const q = ($('flowSearch')?.value || '').toLowerCase();
        const hh = data.items.filter(a => (listMode !== 'active' || !['rejected', 'withdrawn', 'completed', 'superseded'].includes(a.status)) && (listMode !== 'attention' || ['needs_input', 'needs_approval', 'uncertain'].includes(a.workflow_state || a.status)) && (!q || (a.title + ' ' + a.company).toLowerCase().includes(q)) && (!$('flowStageFilter').value || a.crm_stage === $('flowStageFilter').value) && (!$('flowWorkFilter').value || a.crm.work_status === $('flowWorkFilter').value));
        $('flowCount').textContent = hh.length + ' из ' + data.items.length + ' откликов';
        $('flowCount').title = 'HH обновлён: ' + date(data.hh.last_sync) + ' · Chrome: ' + (data.browser?.connected ? 'на связи' : 'ожидает подключения');
        const views = $('flowViews');
        if (views) {
            views.replaceChildren();
            for (const [key, label] of [['active', 'В работе'], ['attention', 'На проверку'], ['all', 'Все']]) {
                const b = button(label, async () => { listMode = key; await list(); });
                b.setAttribute('aria-pressed', String(listMode === key));
                views.append(b);
            }
        }
        for (const a of hh) {
            const b = button(a.title, () => open(a.id), 'record' + (chosen === a.id ? ' selected' : ''));
            b.append(make('p', 'company', a.company), make('span', 'tag version', stages[a.crm_stage]), make('p', 'meta', workStatuses[a.crm.work_status] + (a.crm.next_action ? ' · ' + a.crm.next_action : '') + (a.crm.follow_up_at ? ' · ' + CRMPlanning.when(a.crm.follow_up_at) : '')), make('span', 'tag', ({ hh: 'HH: ', telegram: 'Telegram: ', career: 'Сайт компании: ' }[a.channel] || '') + (a.channel === 'hh' && data.hh.items.find(o => o.vacancy_id === a.vacancy_id && o.status === a.status)?.payload.status_text || labels[a.status] || a.status)));
            $('flowList').append(b);
        }
        if (!hh.length)
            $('flowList').append(make('p', 'muted', 'Откройте вакансию → «Обсудить и подготовить отклик».'));
        const inbox = $('flowInbox');
        inbox.replaceChildren();
        if (data.manual_marks?.length) {
            const d = make('details');
            d.open = false;
            d.append(make('summary', '', 'Отклики, отмеченные вами · ' + data.manual_marks.length));
            for (const a of data.manual_marks) {
                const p = make('article', 'flowMessage');
                p.append(external(a.url, a.title + ' · ' + a.company), make('p', 'muted', 'Отмечено вами ' + date(a.marked_at) + '; подтверждение площадки не проверялось.'), manualApplicationButton({ id: a.vacancy_id, manual_application: a }, () => list()));
                d.append(p);
            }
            inbox.append(d);
        }
        const pending = data.deliveries || [];
        if (pending.length) {
            const d = make('details');
            d.open = pending.some(x => x.state === 'uncertain');
            d.append(make('summary', '', 'Доставка в Telegram · ' + pending.length));
            for (const item of pending) {
                const card = make('article', 'flowMessage');
                card.append(make('strong', '', item.state === 'uncertain' ? 'Нужно сверить доставку' : item.state === 'sending' ? 'Отправляется' : 'В очереди доставки'), make('p', 'flowText', item.payload?.text || 'Старое уведомление: текст восстановится из события.'), make('p', 'meta', item.last_error || 'Отправится, когда Telegram-бот работает.'));
                if (item.state === 'uncertain')
                    for (const [resolution, label] of [['sent', 'Проверил чат: сообщение есть'], ['retry', 'Проверил чат: сообщения нет — повторить']])
                        card.append(button(label, async () => { if (!confirm(resolution === 'retry' ? 'Вы проверили чат и разрешаете повторную доставку этого уведомления?' : 'Вы проверили, что получили это сообщение?'))
                            return; await call('delivery_resolve', { key: item.key, revision: item.revision, resolution, confirmed: true }); await list(); }));
                d.append(card);
            }
            inbox.append(d);
        }
        if (data.hh.items.length) {
            const d = make('details');
            d.append(make('summary', '', 'Наблюдения HH · ' + data.hh.items.length));
            for (const a of data.hh.items) {
                const p = make('p');
                p.append(external(a.source_url, (a.payload.title || a.vacancy_id) + ' · ' + (labels[a.status] || a.status)), make('span', 'muted', ' · ' + date(a.observed_at)));
                d.append(p);
            }
            inbox.append(d);
        }
        for (const t of data.hh.unbound_threads) {
            const d = make('details');
            d.append(make('summary', '', 'Чат без привязки к вакансии'), external(t.source_url, 'Открыть чат HH ↗'), make('p', 'muted', 'Выберите отклик слева и свяжите чат только после проверки вакансии.'), button('Связать с выбранным откликом', async () => { if (!chosen)
                throw Error('Выберите отклик.'); if (!confirm('Вы проверили: этот чат относится к выбранной вакансии?'))
                return; await call('bind', { thread_id: t.id, app_id: chosen, confirmed: true }); await list(); await open(chosen); }));
            inbox.append(d);
        }
    }
    async function enter(id) { clearInterval(timer); epoch++; await list(); if (id)
        await open(id); timer = setInterval(() => { if (tab === 'applications')
        list().catch(() => { });
    else
        clearInterval(timer); }, 15000); }
    async function open(id) {
        chosen = id;
        const url = new URL(location.href);
        url.searchParams.set('application', id);
        history.replaceState(null, '', url.pathname + url.search);
        const version = ++epoch;
        const a = await api('workflow?app_id=' + encodeURIComponent(id));
        if (version !== epoch || tab !== 'applications')
            return;
        current = a;
        const readiness = await call('application_readiness', { app_id: id });
        if (version !== epoch || tab !== 'applications')
            return;
        const p = $('flowDetail'), c = a.context, w = a.workflow;
        p.className = 'detail flowDetail';
        p.replaceChildren();
        p.append(make('p', 'eyebrow', c.vacancy.company), make('h2', '', c.vacancy.title));
        const focus = make('section', 'flowNext'), { uncertain, sent, target, title } = WorkflowCore.nextStep(a, readiness);
        focus.append(make('p', 'eyebrow', 'СЛЕДУЮЩИЙ ШАГ'), make('h3', '', title), button(uncertain ? 'Открыть проверку' : sent ? 'Открыть переписку' : 'Перейти к действию', () => { const section = p.querySelector('[data-flow-step="' + target + '"]'); if (!section)
            return; for (let el = section; el && el !== p; el = el.parentElement)
            if (el.tagName === 'DETAILS')
                el.open = true; section.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, ''));
        p.append(focus);
        const hhKnown = a.hh_observations.find(o => o.status !== 'unknown'), hhStatusLabel = hhKnown?.payload.status_text || labels[a.status] || a.status;
        const badges = make('div', 'tags');
        badges.append(make('span', 'tag', ({ hh: 'HH: ', telegram: 'Telegram: ', career: 'Сайт компании: ' }[c.channel] || '') + (c.channel === 'hh' ? hhStatusLabel : labels[a.status] || a.status)), make('span', 'tag version', labels[w.state] || w.state));
        p.append(badges);
        if (hhKnown)
            p.append(make('p', 'meta', 'На HH: ' + hhStatusLabel + ' · проверено ' + date(hhKnown.observed_at) + (hhKnown.payload.resume_id ? '' : ' · резюме в карточке HH не указано')));
        p.append(make('p', 'meta', 'CV: ' + c.resume_title + '\nЦель: ' + (c.goal || 'не задана')), external(c.vacancy.link, 'Открыть вакансию ↗'));
        const context = make('details');
        context.append(make('summary', '', 'Точные версии CV и вакансии'), make('h4', '', 'CV · ' + c.resume_hash.slice(0, 12)), make('pre', 'flowText', c.resume_text), make('h4', '', 'Вакансия'), make('pre', 'flowText', c.vacancy.description));
        p.append(context);
        if (a.status === 'queued' && a.crm.stage === 'preparing')
            context.append(button('Обновить контекст из архива', async () => { if (!confirm('Создать подготовку с выбранным над списком CV и последней вакансией из архива? Текущее обсуждение и письмо останутся в истории прежнего контекста.'))
                return; const renewed = await call('renew', { app_id: id, resume_id: $('analysisCV').value || c.resume_id, goal: summaryData.goal || c.goal }); await list(); await open(renewed.id); }));
        const steps = make('div', 'flowSteps flowStepButtons');
        steps.setAttribute('aria-label', 'Этапы подготовки отклика');
        for (const [key, label] of [['sources', '1. Источники'], ['fit', '2. Соответствие'], ['letter', '3. Письмо'], ['form', '4. Анкета'], [c.channel === 'career' ? 'transfer' : 'review', '5. Проверка и разрешение']])
            steps.append(button(label, () => reveal(p, key)));
        p.append(steps);
        const sources = make('details', 'flowStagePanel');
        sources.dataset.flowStep = 'sources';
        sources.open = target === 'sources';
        sources.append(make('summary', '', '1. Проверка CV и вакансии' + (readiness.issues.length ? ' · нужно обновление' : '')), make('p', 'muted', 'Подготовка использует сохранённые версии. Перед переносом текстов и отправкой активность вакансии проверяется заново. Открытие формы и заполнение — разные действия.'));
        for (const issue of readiness.issues)
            sources.append(make('p', 'flowSourceIssue', issue.message));
        if (!readiness.issues.length)
            sources.append(make('p', '', 'CV и текст совпадают с контекстом. Вакансия проверена ' + date(readiness.checked_at) + '.'));
        const sourceStatus = make('p', 'muted');
        sourceStatus.setAttribute('role', 'status');
        sources.append(button('Обновить вакансию через Chrome', async () => { const task = await call('collect_one', { url: c.vacancy.link }); sourceStatus.textContent = 'Чтение в очереди Chrome. Данные письма не отправляются. Можно продолжать подготовку, пока Chrome недоступен.'; for (let i = 0; i < 30; i++) {
            const result = await call('collection_status', { command_id: task.command_id });
            if (!['queued', 'running'].includes(result.state)) {
                sourceStatus.textContent = result.result?.note || 'Чтение завершено. Обновите проверку.';
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 2000));
        } sourceStatus.textContent = 'Задача сохранена и ждёт Chrome. Проверьте результат позже.'; }));
        if (!readiness.can_prepare && c.resume_id && !c.resume_id.startsWith('file_'))
            sources.append(button('Обновить CV через Chrome', async () => { if (c.resume_id.startsWith('gdoc_'))
                throw Error('Обновите Google Docs в разделе «Резюме», проверьте текст и сохраните снимок.'); await call('refresh', { ids: [], resume_id: c.resume_id }); sourceStatus.textContent = 'Обновление CV поставлено в очередь Chrome.'; }));
        if (!readiness.can_prepare)
            sources.append(button('Обновить контекст подготовки', async () => { const renewed = await call('renew', { app_id: id, resume_id: c.resume_id, goal: c.goal || '' }); await list(); await open(renewed.id); notice('Подготовка обновлена. Прежние письмо, ответы и обсуждение остались в истории старого контекста.'); }));
        sources.append(button('Проверить состояние заново', () => open(id)), sourceStatus);
        p.append(sources);
        const fit = make('details', 'flowStagePanel');
        fit.dataset.flowStep = 'fit';
        fit.open = target === 'fit';
        fit.append(make('summary', '', '2. Соответствие, подтверждения и пробелы'), make('p', 'muted', 'Проверьте, какие требования подтверждаются CV. Если опыта недостаточно, уточните факты или запланируйте обучение. Отсутствие подтверждения не означает отсутствие навыка. Разбор можно выполнить без API; платный Luna запускается только кнопкой.'));
        if (readiness.can_prepare)
            SkillAnalysis.attach(fit, { api, context: { resume_id: c.resume_id, vacancy_id: c.vacancy.id, goal: c.goal || '' }, isCurrent: () => version === epoch && tab === 'applications', onHistory: () => setTab('reviews') });
        else
            fit.append(make('p', 'flowSourceIssue', 'Сначала обновите CV/вакансию и контекст подготовки в шаге 1. Это исключит смешение разбора новых документов со старым письмом.'));
        fit.append(button('Перейти к письму', () => reveal(p, 'letter')));
        p.append(fit);
        const planning = make('details');
        planning.dataset.flowStep = 'planning';
        planning.append(make('summary', '', 'План, этапы и встречи'));
        CRMPlanning.render(planning, a, { call, button, reload: async () => { await open(id); await list(); } });
        p.append(planning);
        const giga = a.channels?.find(x => x.channel === 'telegram');
        if (c.channel === 'hh' && ['submitted', 'viewed', 'invited'].includes(a.status)) {
            const screening = section('AI-интервью Giga · тот же отклик');
            if (a.giga_invitation) {
                screening.append(make('p', '', 'Приглашение из HH сохранено · ' + (a.giga_invitation.start_state === 'sent' ? 'интервью запущено' : a.giga_invitation.start_state === 'uncertain' ? 'результат запуска требует проверки' : 'готово к запуску в Telegram')), external(a.giga_invitation.source_url, 'Источник приглашения ↗'), make('p', 'muted', 'В @baniartbot: /applications → эта вакансия → /start_recruiter. Проверьте CV и подтвердите запуск. Вопрос → черновик с API или без API → ваша редакция → подтверждение отправки.'));
            }
            const chatRead = make('details'), chatURL = make('input');
            chatURL.type = 'url';
            chatURL.placeholder = 'https://hh.ru/chat/…';
            chatURL.setAttribute('aria-label', 'Ссылка на чат HH');
            chatRead.append(make('summary', '', 'Прочитать чат HH и найти приглашение'), chatURL, button('Синхронизировать этот чат', async () => { await call('sync', { source_url: chatURL.value.trim() }); notice('Чтение чата поставлено в очередь Chrome. Никакие сообщения не отправляются.'); }));
            screening.append(chatRead);
            if (giga) {
                screening.append(make('p', '', 'Диалог связан с этим CV и вакансией. Этап и план CRM общие.'), external('https://t.me/baniartbot', 'Продолжить в Telegram ↗'), button('Проверить завершение AI-интервью', async () => { const v = await call('screening_preview', { app_id: giga.id }); if (!confirm('AI-интервью действительно завершено?\n' + v.title + '\nПоследнее сообщение:\n' + v.last_message + '\nCRM: AI-интервью → ждём приглашения. Более поздний этап сохранится.'))
                    return; await call('complete_screening', { app_id: giga.id, token: v.token, confirmed: true }); await open(id); await list(); }));
            }
            else
                screening.append(make('p', 'muted', 'Если эта вакансия направила вас в Giga, подтвердите связь. Будет использована точная версия CV, цели и вакансии; сообщения не отправляются.'), button('Связать эту вакансию с Giga', async () => { if (!confirm('Вы проверили, что диалог Giga относится к этой вакансии? Связать тот же CV и контекст?'))
                    return; await call('start_screening', { app_id: id, confirmed: true }); await open(id); notice('Связано. В @baniartbot выберите диалог через /applications, затем /question.'); }));
            p.append(screening);
        }
        const locked = ['sending', 'filling', 'submitted', 'uncertain', 'superseded'].includes(w.state);
        const { lt, ct, model } = WorkflowLetter.render({ a, w, c, p, id, locked, hhKnown, sent, letterPreferences, isCurrent: () => version === epoch && chosen === id, call, open, button, section, text });
        if (a.field_suggestions?.length) {
            const drafts = make('details');
            drafts.append(make('summary', '', 'Предложения ИИ для анкеты · ' + a.field_suggestions.length));
            for (const v of a.field_suggestions)
                drafts.append(make('p', 'meta', v.question + ' · ' + (v.result.model || 'модель')), make('p', 'flowText', v.result.answer));
            p.append(drafts);
        }
        if (c.channel === 'career') {
            WorkflowCareer.render({ a, w, c, p, id, locked, lt, ct, model, isCurrent: () => version === epoch && chosen === id, call, open, reveal, button, section, copyOffline, labels, readiness });
            finishLayout(p, target);
            return;
        }
        if (c.channel !== 'hh') {
            const telegram = section('Продолжить диалог в Telegram');
            telegram.dataset.flowStep = 'telegram';
            telegram.append(external('https://t.me/baniartbot', 'Открыть @baniartbot ↗'), make('p', 'muted', 'Выберите этот отклик командой /applications. Управление Giga доступно после входа Telethon.'));
            p.append(telegram);
            finishLayout(p, target);
            return;
        }
        const form = section(hhKnown ? 'Статус отклика подтверждён на HH' : '2. Подготовить форму HH');
        form.dataset.flowStep = 'form';
        if (hhKnown)
            form.append(make('p', '', 'На HH: ' + hhStatusLabel + '. Повторная подготовка и отправка не нужны.'), button('Синхронизировать HH', async () => { await call('sync'); notice('Проверка статусов и доступных чатов поставлена в очередь Chrome.'); }));
        else
            form.append(make('p', 'muted', 'Подключите HH один раз в расширении. Служебная вкладка откроется автоматически, прочитает форму и перенесёт письмо. Затем здесь появится проверка ответов и разрешение отправки.'), button('Подключить HH', () => Journey.connect()), button('Подготовить форму HH', async () => { await call('prepare', { app_id: id }); notice('В очереди Chrome. Через минуту нажмите «Обновить отклик».'); }), button('Обновить отклик', () => open(id)));
        for (const cmd of a.commands.slice(0, 2)) {
            let note = '';
            try {
                note = JSON.parse(cmd.result || '{}').note || '';
            }
            catch { }
            form.append(make('p', 'meta', cmd.kind + ' · ' + (labels[cmd.state] || cmd.state) + (note ? ' · ' + note : '')));
        }
        if (w.form) {
            const folded = make('details');
            folded.append(make('summary', '', 'Chrome и история подготовки'), form);
            p.append(folded);
        }
        else
            p.append(form);
        if (w.state === 'uncertain') {
            const recovery = section('Результат отправки неизвестен');
            recovery.dataset.flowStep = 'recovery';
            recovery.append(make('p', '', 'Проверьте раздел «Отклики» на HH и выполните синхронизацию. Повтор автоматически не выполняется.'), button('Я проверил HH: отклик не отправлен', async () => { if (!confirm('Вы лично проверили HH и убедились, что отклика нет? Будет создано новое согласование, старое разрешение не используется.'))
                return; await call('recover', { app_id: id, confirmed: true }); await open(id); }));
            p.append(recovery);
        }
        if (w.form && !locked) {
            const preview = section('Проверьте и разрешите действие'), inputs = new Map();
            preview.dataset.flowStep = 'review';
            preview.append(make('p', 'muted', 'Резюме: ' + c.resume_title + ' · письмо #' + w.revision + '\nДействие HH: «' + w.form.submit_label + '». Разрешение действует 15 минут для показанных текста и ответов.'));
            for (const f of w.form.fields) {
                const l = make('label', 'flowLabel', f.label + (f.required ? ' *' : '')), i = make(f.type === 'select' ? 'select' : ['checkbox', 'radio'].includes(f.type) ? 'input' : 'textarea');
                if (['checkbox', 'radio'].includes(f.type)) {
                    i.type = f.type;
                    i.name = 'flow-' + f.group;
                    i.checked = !!a.form_answers?.values?.[f.id];
                }
                else if (f.type === 'select') {
                    for (const option of f.options) {
                        const o = make('option', '', option.text);
                        o.value = option.value;
                        i.append(o);
                    }
                    i.value = a.form_answers?.values?.[f.id] ?? f.value;
                }
                else {
                    i.rows = f.purpose === 'cover' ? 6 : 3;
                    i.value = a.form_answers?.values?.[f.id] ?? f.value ?? '';
                    i.readOnly = f.purpose === 'cover';
                }
                l.append(i);
                preview.append(l);
                inputs.set(f.id, { f, i });
                if (f.purpose !== 'cover' && !['checkbox', 'radio', 'select'].includes(f.type)) {
                    preview.append(button('Предложить ответ · ' + f.label.slice(0, 30), async () => { const result = await call('answer', { app_id: id, question: f.label, model: model.value, comments: ct.value, field_id: f.id, fingerprint: w.form.fingerprint, revision: a.form_answers.revisions[f.id] || 0 }); i.value = result.answer; notice(result.needs_user ? 'Нужны уточнения: ' + result.missing.join('; ') : result.review_note); }), button('Ответ без API · ' + f.label.slice(0, 30), async () => { const packet = ChatGPTExport.buildAnswerPackage({ context: { ...c, user_facts: a.user_facts || [] }, question: f.label, draft: i.value, comments: ct.value, history: a.hh_messages.slice(-12).map(m => ({ direction: m.direction, text: m.text })) }); await copyOffline(packet, preview); notice('Промпт скопирован. Вставьте готовый ответ в поле вопроса выше и проверьте перед разрешением.'); }));
                }
            }
            preview.append(button('Сохранить ответы анкеты', async () => { let revisions = { ...a.form_answers.revisions }; for (const [field_id, { f, i }] of inputs)
                if (f.purpose !== 'cover') {
                    const saved = await call('field_answer', { app_id: id, field_id, value: ['checkbox', 'radio'].includes(f.type) ? i.checked : i.value, fingerprint: w.form.fingerprint, revision: revisions[field_id] || 0 });
                    revisions = saved.revisions;
                } await open(id); notice('Ответы сохранены; отправка не выполнялась.'); }));
            const permission = make('label', 'flowConsent'), check = make('input');
            check.type = 'checkbox';
            permission.append(check, document.createTextNode('Я проверил CV, письмо и все ответы; разрешаю выполнить показанное действие на HH.'));
            preview.append(permission);
            const approve = button('Разрешить «' + w.form.submit_label + '»', async () => { if (!check.checked)
                throw Error('Нужно ваше явное разрешение.'); const answers = Object.fromEntries([...inputs].map(([k, { f, i }]) => [k, ['checkbox', 'radio'].includes(f.type) ? i.checked : i.value])); const intent = await call('intent', { app_id: id, answers }); await call('approve', { app_id: id, answers, intent_hash: intent.intent_hash, confirmed: true }); await open(id); notice('Разрешение сохранено. Жду подтверждения HH.'); }, '');
            preview.append(approve);
            p.append(preview);
            for (const { i } of inputs.values())
                i.oninput = () => { check.checked = false; };
        }
        if (a.field_history?.length) {
            const history = make('details');
            history.append(make('summary', '', 'История ответов на анкеты · ' + a.field_history.length));
            for (const v of a.field_history) {
                const row = make('article', 'flowMessage');
                row.append(make('p', 'meta', v.question + ' · версия ' + v.revision + ' · ' + v.actor), make('p', 'flowText', String(v.value)));
                history.append(row);
            }
            p.append(history);
        }
        const recruiter = section('Сообщения работодателя');
        recruiter.dataset.flowStep = 'messages';
        recruiter.append(make('p', 'muted', 'Это прочитанная переписка HH. Обсуждение с редактором выше хранится отдельно. Новые сообщения из этого раздела рекрутеру не отправляются.'));
        for (const t of a.hh_threads)
            recruiter.append(external(t.source_url, 'Открыть чат HH ↗'));
        for (const m of a.hh_messages) {
            const b = make('article', 'flowMessage');
            b.append(make('p', 'meta', (m.direction === 'incoming' ? 'Входящее' : m.direction === 'outgoing' ? 'Исходящее' : 'Направление не определено') + ' · ' + date(m.message_at || m.observed_at)), make('p', 'flowText', m.text));
            recruiter.append(b);
        }
        if (!a.hh_messages.length)
            recruiter.append(make('p', 'muted', 'Сообщений ещё нет в архиве. Синхронизируйте загруженный чат через расширение.'));
        for (const o of a.hh_observations.slice(0, 8))
            recruiter.append(make('p', 'meta', (o.payload.status_text || labels[o.status] || o.status) + ' · ' + date(o.observed_at)), external(o.source_url, 'Источник HH ↗'));
        p.append(recruiter);
        finishLayout(p, target);
    }
    function reveal(p, key) { const section = p.querySelector('[data-flow-step="' + key + '"]') || p.querySelector('[data-flow-step="form"]'); if (!section)
        return; for (let el = section; el && el !== p; el = el.parentElement)
        if (el.tagName === 'DETAILS')
            el.open = true; section.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    function finishLayout(p, target) { for (const section of [...p.children].filter(n => n.matches('section.flowSection'))) {
        const key = section.dataset.flowStep;
        if (!key)
            continue;
        const details = make('details', 'flowStagePanel');
        details.open = key === target;
        details.append(make('summary', '', section.querySelector('h3')?.textContent || 'Подробности'));
        section.before(details);
        details.append(section);
    } }
    async function copyOffline(packet, parent) { try {
        await navigator.clipboard.writeText(packet);
    }
    catch {
        const t = make('textarea');
        t.value = packet;
        t.readOnly = true;
        t.rows = 10;
        t.setAttribute('aria-label', 'Промпт без API');
        parent.append(t);
        t.focus();
        t.select();
        notice('Промпт выделен. Нажмите Cmd+C / Ctrl+C.');
    } }
    async function create(job) {
        const resume = $('analysisCV').value, goal = tab === 'ranking' ? $('rankingGoal').value : summaryData.goal || '';
        if (!resume)
            throw Error('Выберите CV.');
        let a;
        try {
            a = await call('make', { resume_id: resume, vacancy_id: job.id, goal });
        }
        catch (e) {
            if (!/Отклик по этой вакансии уже создан|Отклик уже создан с другой карьерной целью/.test(e.message))
                throw e;
            const list = await api('workflow'), existing = list.items.find(i => i.vacancy_id === job.id && i.channel === (job.id.startsWith('hh_') ? 'hh' : 'career'));
            if (!existing)
                throw e;
            const current = await api('workflow?app_id=' + encodeURIComponent(existing.id));
            if (current.status !== 'queued' || current.crm.stage !== 'preparing')
                throw e;
            if (!confirm('Для этой вакансии уже есть подготовка с другим CV/версией или целью. Старая: ' + current.context.resume_title + ' (' + current.context.resume_hash.slice(0, 8) + '). Создать подготовку для выбранного сейчас CV? Прежнее письмо, ответы и обсуждение останутся в истории.')) {
                setTab('applications');
                await enter(existing.id);
                return;
            }
            a = await call('renew', { app_id: existing.id, resume_id: resume, goal });
        }
        setTab('applications');
        await enter(a.id);
    }
    return { enter, create, list };
})();
$('flowSync').onclick = async () => { try {
    await api('workflow', { op: 'sync' });
    notice('Синхронизация в очереди Chrome. Подключите отдельную вкладку HH через popup.');
}
catch (e) {
    notice(e.message);
} };
$('flowStageFilter').onchange = $('flowWorkFilter').onchange = () => Flow.list().catch(e => notice(e.message));
if ($('flowSearch')) {
    let timer;
    $('flowSearch').oninput = () => { clearTimeout(timer); timer = setTimeout(() => Flow.list().catch(e => notice(e.message)), 250); };
}
