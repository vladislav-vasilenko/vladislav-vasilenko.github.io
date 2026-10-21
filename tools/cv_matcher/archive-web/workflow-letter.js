'use strict';
const WorkflowLetter = (() => {
    function render({ a, w, c, p, id, locked, hhKnown, sent, letterPreferences, isCurrent, call, open, button, section, text }) {
        const letter = section('Сопроводительное письмо');
        letter.dataset.flowStep = 'letter';
        if (hhKnown) {
            const archive = make('details');
            archive.append(make('summary', '', 'Письмо и контекст отправленного отклика'), letter);
            p.append(archive);
        }
        else if (w.form || w.state === 'fields_filled' || sent) {
            const folded = make('details');
            folded.append(make('summary', '', 'Письмо · версия ' + w.revision), letter);
            p.append(folded);
        }
        else
            p.append(letter);
        const preferences = letterPreferences.get(id) || { comments: '', sentences: 3, model: 'luna', view: 'letter', includeDraft: true };
        letterPreferences.set(id, preferences);
        const modes = make('div', 'flowModes');
        modes.setAttribute('role', 'tablist');
        modes.setAttribute('aria-label', 'Работа с письмом');
        const compose = make('div'), discussion = make('div'), chatgpt = make('div');
        const panels = { letter: compose, discussion, chatgpt }, modeButtons = {};
        function showMode(key) { preferences.view = key; for (const [name, panel] of Object.entries(panels)) {
            panel.hidden = name !== key;
            modeButtons[name].setAttribute('aria-selected', String(name === key));
        } if (key === 'discussion')
            mt.focus(); }
        for (const [key, label] of [['letter', 'Письмо'], ['discussion', 'Диалог с ИИ'], ['chatgpt', 'ChatGPT без API']]) {
            const b = button(label, () => showMode(key));
            b.setAttribute('role', 'tab');
            b.setAttribute('aria-controls', 'flow-letter-' + key);
            modeButtons[key] = b;
            modes.append(b);
            panels[key].id = 'flow-letter-' + key;
            panels[key].setAttribute('role', 'tabpanel');
        }
        const settings = make('details', 'flowLetterSettings'), [cl, ct] = text('Что подчеркнуть в письме', preferences.comments, 2), lengthLabel = make('label', 'flowLabel', 'Предложений'), length = make('input'), modelLabel = make('label', 'flowLabel', 'Модель ИИ'), model = make('select');
        ct.maxLength = 4000;
        ct.placeholder = 'Например: интерес к Flow Matching и исследовательским задачам. Без выдуманного опыта.';
        length.type = 'number';
        length.min = '1';
        length.max = '50';
        length.step = '1';
        length.value = preferences.sentences;
        length.setAttribute('aria-label', 'Количество предложений');
        lengthLabel.append(length);
        model.setAttribute('aria-label', 'Модель редактора');
        for (const name of ['luna', 'terra', 'sol']) {
            const o = make('option', '', name);
            o.value = name;
            model.append(o);
        }
        model.value = preferences.model;
        modelLabel.append(model);
        settings.append(make('summary', '', 'Акценты, длина и модель'), cl, lengthLabel, modelLabel);
        const includeLabel = make('label', 'flowIncludeDraft'), includeDraft = make('input');
        includeDraft.type = 'checkbox';
        includeDraft.checked = preferences.includeDraft !== false;
        includeLabel.append(includeDraft, document.createTextNode('Добавить текущий текст письма в промпт'));
        settings.append(includeLabel);
        letter.append(modes, settings, compose, discussion, chatgpt);
        const [ll, lt] = text('Текст письма · версия ' + w.revision, w.draft, 8);
        lt.disabled = locked;
        lt.maxLength = 16000;
        lt.placeholder = 'Сгенерируйте письмо, напишите сами или вставьте результат из ChatGPT.';
        const feedback = make('p', 'muted');
        feedback.setAttribute('role', 'status');
        feedback.setAttribute('aria-live', 'polite');
        const generate = button(w.draft ? 'Сгенерировать другой вариант' : 'Сгенерировать письмо', async () => {
            remember();
            const count = Number(length.value);
            ChatGPTExport.coverTask(count);
            await askEditor('Сгенерируй полное сопроводительное письмо от моего лица для этой вакансии. Длина: ' + count + ' предложений. ' + (ct.value.trim() ? 'Мои пожелания: ' + ct.value.trim() : ''), 'letter');
        }, '');
        generate.disabled = locked;
        const save = button('Сохранить редакцию', async () => { await call('draft', { app_id: id, text: lt.value, revision: w.revision }); await open(id); notice('Редакция сохранена. Предыдущее разрешение отозвано.'); });
        save.disabled = locked;
        const actions = make('div', 'flowLetterActions');
        actions.append(generate, button('Подготовить без API', () => showMode('chatgpt')));
        compose.append(make('p', 'muted', 'Сначала создайте письмо, затем уточните его в диалоге или отредактируйте вручную. Генерация через API — платный запрос.'), actions, ll, save, feedback);
        const versions = make('details');
        versions.append(make('summary', '', 'История писем · ' + a.draft_versions.length));
        for (const v of a.draft_versions)
            versions.append(make('p', 'meta', '#' + v.revision + ' · ' + date(v.at) + ' · ' + v.actor), make('pre', 'flowText', v.text));
        compose.append(versions);
        const messages = make('div', 'flowMessages');
        for (const m of a.discussion) {
            const box = make('article', 'flowMessage ' + m.role);
            box.append(make('strong', '', m.role === 'user' ? 'Вы' : 'Редактор'), make('p', 'flowText', m.text));
            messages.append(box);
        }
        discussion.append(messages);
        if (!a.discussion.length)
            messages.append(make('p', 'muted', 'Попросите составить письмо или уточните акценты. Письмо и история диалога сохраняются в этой карточке.'));
        const [ml, mt] = text('Сообщение ИИ-редактору', '', 3);
        mt.placeholder = 'Например: сократи до 3 предложений и сделай мотивацию конкретнее.';
        mt.maxLength = 6000;
        mt.disabled = locked;
        discussion.append(ml, make('p', 'muted', 'Платный запрос: выбранные CV, вакансия, текущая редакция и диалог передаются в OpenAI.'));
        const send = button('Отправить редактору', async () => { const message = mt.value.trim(); if (!message)
            throw Error('Напишите сообщение.'); await askEditor(message, 'discussion'); }, '');
        send.disabled = locked;
        discussion.append(send, button('Обсудить без API · скопировать промпт', () => copyPackage('discuss_cover_letter')));
        const packageText = make('textarea');
        packageText.readOnly = true;
        packageText.rows = 14;
        packageText.setAttribute('aria-label', 'Промпт для генерации сопроводительного письма');
        packageText.hidden = true;
        const packageStatus = make('p', 'muted');
        packageStatus.setAttribute('role', 'status');
        chatgpt.append(make('p', '', 'Скопируйте готовое задание «Сгенерируй сопроводительное письмо» вместе с CV, полной вакансией, целью, длиной и вашими пожеланиями. Вставьте в ChatGPT App и обсуждайте письмо там.'), make('p', 'muted', 'Копирование работает локально, без вызова нашего API. Готовое письмо вставьте во вкладке «Письмо» и сохраните редакцию.'), button('Скопировать промпт для письма', copyPackage), button('Обсудить с ИИ без API', () => copyPackage('discuss_cover_letter')), packageStatus, packageText);
        function remember() { preferences.comments = ct.value; preferences.sentences = length.value; preferences.model = model.value; preferences.includeDraft = includeDraft.checked; }
        for (const input of [ct, length, model, includeDraft])
            input.oninput = () => { remember(); packageText.hidden = true; packageStatus.textContent = 'Параметры изменены. Скопируйте промпт заново.'; };
        async function copyPackage(task = 'generate_cover_letter') {
            remember();
            const packet = ChatGPTExport.buildApplicationPackage({ context: { ...c, user_facts: a.user_facts || [] }, draft: lt.value, comments: ct.value, message: task === 'discuss_cover_letter' ? mt.value : '', sentences: length.value, task, includeDraft: includeDraft.checked, history: task === 'discuss_cover_letter' ? a.discussion.map(m => ({ role: m.role, text: m.text })) : [] });
            packageText.value = packet;
            try {
                await navigator.clipboard.writeText(packet);
                packageStatus.textContent = 'Скопировано: ' + (task === 'discuss_cover_letter' ? 'обсуждение письма' : 'генерация письма') + ', CV, вакансия и пожелания' + (includeDraft.checked ? ' с текущим текстом письма.' : '.') + ' Вставьте в ChatGPT App.';
                notice(packageStatus.textContent);
            }
            catch {
                showMode('chatgpt');
                packageText.hidden = false;
                packageText.focus();
                packageText.select();
                packageStatus.textContent = 'Промпт выделен ниже. Нажмите Cmd+C / Ctrl+C.';
            }
        }
        async function askEditor(message, view) {
            if (locked || !isCurrent())
                return;
            remember();
            preferences.view = view;
            generate.disabled = true;
            send.disabled = true;
            save.disabled = true;
            feedback.textContent = 'Редактор готовит ответ…';
            notice('Редактор готовит ответ. Отправки отклика не происходит.');
            try {
                if (lt.value !== w.draft) {
                    const saved = await call('draft', { app_id: id, text: lt.value, revision: w.revision });
                    w.revision = saved.workflow.revision;
                    w.draft = saved.workflow.draft;
                }
                if (!isCurrent()) return;
                const result = await call('chat', { app_id: id, message, model: model.value, request_id: crypto.randomUUID() });
                if (isCurrent()) {
                    if (result.needs_user || !result.draft_applied)
                        preferences.view = 'discussion';
                    await open(id);
                    notice(result.needs_user ? 'Редактор запросил уточнения — откройте «Диалог с ИИ».' : result.draft_applied ? 'Новая версия письма сохранена. Её можно править вручную или в диалоге.' : 'Ответ редактора готов — откройте «Диалог с ИИ».');
                }
            }
            catch (e) {
                feedback.textContent = e.message;
                throw e;
            }
            finally {
                generate.disabled = locked;
                send.disabled = locked;
                save.disabled = locked;
            }
        }
        showMode(preferences.view in panels ? preferences.view : 'letter');
        return { lt, ct, model };
    }
    return { render };
})();
