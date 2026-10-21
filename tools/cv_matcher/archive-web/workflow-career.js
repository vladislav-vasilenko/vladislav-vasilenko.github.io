'use strict';
const WorkflowCareer = (() => {
    function render({ a, w, c, p, id, locked, lt, ct, model, isCurrent, call, open, reveal, button, section, copyOffline, labels, readiness }) {
        function renderBrowser() {
            const browser = section('4. Открыть и прочитать анкету в Chrome');
            browser.dataset.flowStep = 'form';
            const browserStatus = make('p', 'muted');
            browserStatus.setAttribute('role', 'status');
            const connection = WorkflowCore.careerConnection(readiness.browser);
            browser.append(make('p', connection.state === 'ready' ? 'muted' : 'flowSourceIssue', connection.message));
            browser.append(make('p', 'muted', 'Откройте вакансию в Chrome, при необходимости войдите и нажмите «Откликнуться» на сайте. Затем прочитайте открывшуюся анкету. Подготовленные ответы передаются только после проверки и разрешения.'));
            const startRead = async () => {
                const task = await call('career_open', { app_id: id });
                if (!isCurrent())
                    return;
                browserStatus.textContent = task.note;
                if (task.browser && !task.browser.connected)
                    browserStatus.textContent += ' ' + WorkflowCore.careerConnection(task.browser).message;
            };
            browser.append(button(w.form ? 'Перечитать форму в Chrome' : 'Открыть и прочитать форму в Chrome', startRead), button('Проверить состояние', () => open(id)), button('Настроить расширение', () => Journey.connect()), external(c.vacancy.link, 'Открыть вакансию на сайте ↗'), browserStatus);
            for (const cmd of a.commands.filter(x => x.kind === 'career_open').slice(0, 2)) {
                const result = WorkflowCore.commandResult(cmd);
                const label = cmd.state === 'queued' ? 'Ждёт обработчик Chrome' : cmd.state === 'running' ? 'Чтение формы' : cmd.state === 'complete' ? 'Форма прочитана' : 'Нужен ваш шаг';
                browser.append(make('p', 'meta', label + (result.note ? ' · ' + result.note : '')));
            }
            p.append(browser);
        }
        function renderProfile() {
            const profile = make('details');
            profile.append(make('summary', '', 'Данные для автозаполнения · контакты, город, соцсети, портфолио'), make('p', 'muted', 'Сохраняются в вашем локальном профиле и предлагаются для пустых полей на других сайтах. Уже введённые на сайте значения и ответы этой анкеты имеют приоритет. Контакты не добавляются в контекст ИИ.'));
            let profileLoaded = false;
            profile.ontoggle = async () => {
                if (!profile.open || profileLoaded)
                    return;
                profileLoaded = true;
                try {
                    const saved = await call('candidate_profile');
                    if (!isCurrent())
                        return;
                    const inputs = new Map();
                    for (const [key, label] of Object.entries(saved.labels)) {
                        const l = make('label', 'flowLabel', label), i = make('input');
                        i.type = key === 'email' ? 'email' : key === 'phone' ? 'tel' : key.endsWith('_url') ? 'url' : 'text';
                        i.value = saved.values[key];
                        l.append(i);
                        profile.append(l);
                        inputs.set(key, i);
                    }
                    profile.append(button('Сохранить общие данные', async () => { await call('candidate_profile_save', { values: Object.fromEntries([...inputs].map(([k, i]) => [k, i.value])), revisions: saved.revisions }); await open(id); notice('Данные сохранены. Они будут предложены в пустых полях анкет; перенос на сайт требует вашего разрешения.'); }));
                }
                catch (e) {
                    profileLoaded = false;
                    notice(e.message);
                }
            };
            p.append(profile);
        }
        function renderQuestions() {
            if (w.form) {
                const q = section('Анкета работодателя · сохранённая версия');
                q.dataset.flowStep = 'review';
                q.append(make('p', 'muted', 'Сохраните ответы и проверьте состав перед переносом в Chrome. Вложения, согласия и нестандартные поля проверяются на сайте. Финальная отправка пока ручная.'));
                for (const f of w.form.fields) {
                    const row = make('details'), label = make('label', 'flowLabel', f.label + (f.required ? ' *' : ''));
                    row.append(make('summary', '', f.label + (a.form_answers.from_resume?.[f.id] ? ' · из выбранного CV' : a.form_answers.from_profile?.[f.id] ? ' · из профиля' : a.form_answers.values[f.id] ? ' · сохранено' : '')), label);
                    row.open = f.purpose === 'about';
                    if (f.purpose === 'cover') {
                        row.append(make('p', 'flowText', w.draft || 'Подготовьте письмо редактором выше.'));
                        q.append(row);
                        continue;
                    }
                    if (f.manual_only || f.type === 'file') {
                        row.append(make('p', 'muted', f.type === 'file' ? 'Выберите файл на сайте работодателя.' : 'Это поле проверяется на сайте. Автоматический перенос его не меняет.'));
                        q.append(row);
                        continue;
                    }
                    const value = a.form_answers.values[f.id];
                    const i = make(f.type === 'select' ? 'select' : ['checkbox', 'radio'].includes(f.type) ? 'input' : 'textarea');
                    if (['checkbox', 'radio'].includes(f.type)) {
                        i.type = f.type;
                        i.name = 'career-' + f.group;
                        i.checked = !!value;
                    }
                    else if (f.type === 'select') {
                        for (const o of f.options || []) {
                            const option = make('option', '', o.text);
                            option.value = o.value;
                            i.append(option);
                        }
                        i.value = value;
                    }
                    else {
                        i.value = value || '';
                        i.rows = 3;
                    }
                    label.append(i);
                    let revision = a.form_answers.revisions[f.id] || 0;
                    if (!['checkbox', 'radio', 'select', 'email', 'tel'].includes(f.type) && !['contact', 'resume_url'].includes(f.purpose) && !/^(?:имя|фамилия|фио|e-?mail|телефон|номер телефона)(?:\s|[*:]|$)/i.test(f.label))
                        row.append(button('Предложить ответ · API', async () => { const result = await call('answer', { app_id: id, question: f.label, model: model.value, comments: ct.value, field_id: f.id, fingerprint: w.form.fingerprint, revision }); i.value = result.answer; notice(result.needs_user ? 'Уточните факты: ' + result.missing.join('; ') : result.review_note); }), button('Ответ без API', async () => { await copyOffline(ChatGPTExport.buildAnswerPackage({ context: { ...c, user_facts: a.user_facts || [] }, question: f.label, draft: i.value, comments: ct.value, history: [] }), row); }));
                    row.append(button('Сохранить ответ', async () => { const saved = await call('field_answer', { app_id: id, field_id: f.id, value: ['checkbox', 'radio'].includes(f.type) ? i.checked : i.value, fingerprint: w.form.fingerprint, revision }); revision = saved.revisions[f.id]; notice('Ответ сохранён в общей истории. Отправки работодателю не было.'); }));
                    q.append(row);
                }
                p.append(q);
            }
        }
        function renderTransfer() {
            if (w.form && ['career-fields-v1', 'career-fields-v2'].includes(w.form.adapter_version) && !locked && w.state !== 'fill_approved') {
                const transfer = section('5. Проверить и разрешить заполнение');
                transfer.dataset.flowStep = 'transfer';
                transfer.append(make('p', 'muted', 'Будут использованы сохранённые ответы и письмо. Исходная вкладка компании должна оставаться открытой. Сайт может сохранять данные при вводе.'), button('Проверить, что будет заполнено', async () => {
                    const intent = await call('career_fill_intent', { app_id: id });
                    if (!isCurrent())
                        return;
                    const review = make('div');
                    review.append(make('p', 'meta', intent.source_url + '\nКонтекст CV: ' + c.resume_title + ' · письмо #' + intent.revision));
                    for (const f of intent.form_snapshot.fields)
                        if (Object.hasOwn(intent.answers, f.id))
                            review.append(make('h4', '', f.label), make('pre', 'flowText', intent.answers[f.id]));
                    review.append(make('p', 'muted', 'На сайте вручную: ' + (intent.manual_fields.join('; ') || 'файлы, согласия, нестандартные поля') + '\n' + intent.limitations.join('\n')));
                    const label = make('label', 'flowConsent'), check = make('input');
                    check.type = 'checkbox';
                    label.append(check, document.createTextNode('Я проверил показанные тексты и разрешаю передать их в форму этой компании. Отправка отклика — отдельно на сайте.'));
                    review.append(label, button('Разрешить заполнение полей', async () => { if (!isCurrent())
                        return; if (!check.checked)
                        throw Error('Подтвердите передачу текстов.'); const ready = await call('application_readiness', { app_id: id }); if (!isCurrent())
                        return; if (!ready.activity_fresh || !ready.can_prepare) {
                        reveal(p, 'sources');
                        throw Error('Сначала обновите проверку источников в шаге 1. Затем проверьте ответы и разрешите перенос заново.');
                    } await call('career_fill_approve', { app_id: id, intent_hash: intent.intent_hash, confirmed: true }); await open(id); notice('Перенос в очереди Chrome. Отклик не отправляется.'); }));
                    transfer.replaceChildren(review);
                }));
                p.append(transfer);
            }
        }
        function renderResults() {
            if (w.state === 'fill_approved' || w.state === 'filling')
                p.append(make('p', 'muted', 'Перенос ждёт исходную открытую вкладку компании. Он выполняется один раз, без нажатия кнопки отправки.'), button('Обновить результат переноса', () => open(id)));
            if (w.state === 'fields_filled')
                p.append(make('p', '', 'Тексты перенесены. Проверьте резюме, файлы, согласия и остальные поля на сайте. Отклик ещё не отправлен.'));
            for (const cmd of a.commands.filter(x => x.kind === 'career_fill').slice(0, 2)) {
                let note = '';
                try {
                    note = JSON.parse(cmd.result || '{}').note || '';
                }
                catch { }
                p.append(make('p', 'meta', 'Перенос: ' + (labels[cmd.state] || cmd.state) + (note ? ' · ' + note : '')));
            }
            if (a.field_history?.length) {
                const history = make('details');
                history.append(make('summary', '', 'История ответов на анкеты · ' + a.field_history.length));
                for (const v of a.field_history)
                    history.append(make('p', 'meta', v.question + ' · версия ' + v.revision), make('p', 'flowText', String(v.value)));
                p.append(history);
            }
            const manual = section('Проверить и отправить на сайте компании');
            manual.dataset.flowStep = 'manual';
            manual.append(external(c.vacancy.link, 'Открыть форму на сайте компании ↗'), button('Скопировать письмо', () => navigator.clipboard.writeText(lt.value)), make('p', 'muted', 'После переноса проверьте анкету на сайте, выберите файлы и согласия, отправьте отклик вручную и обновите этап CRM. Заполнение полей не считается отправкой.'));
            p.append(manual);
        }
        renderBrowser();
        renderProfile();
        renderQuestions();
        renderTransfer();
        renderResults();
    }
    return { render };
})();
