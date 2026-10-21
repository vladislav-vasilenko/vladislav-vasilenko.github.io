/* Pure presentation decisions. No DOM, network, timers or workflow mutations. */
(function (root) {
    'use strict';
    const pending = new Set(['approved', 'sending', 'fill_approved', 'filling']);
    const sentStates = new Set(['submitted', 'viewed', 'invited']);
    function nextStep(application, readiness) {
        const workflow = application.workflow;
        const channel = application.context.channel;
        const uncertain = workflow.state === 'uncertain';
        const sent = sentStates.has(application.status);
        let target, title;
        if (uncertain) {
            target = channel === 'career' ? 'manual' : 'recovery';
            title = 'Сверьте результат на сайте работодателя';
        }
        else if (sent) {
            target = channel === 'career' ? 'manual' : channel === 'telegram' ? 'telegram' : 'messages';
            title = 'Продолжайте диалог с работодателем';
        }
        else if (!readiness.can_prepare) {
            target = 'sources';
            title = 'Обновите контекст CV и вакансии';
        }
        else if (pending.has(workflow.state)) {
            target = 'form';
            title = 'Ожидаем результат Chrome';
        }
        else if (workflow.state === 'fields_filled') {
            target = 'manual';
            title = 'Проверьте заполненную форму на сайте';
        }
        else if (workflow.form && !readiness.activity_fresh) {
            target = 'sources';
            title = 'Обновите проверку активности вакансии';
        }
        else if (workflow.form) {
            target = 'review';
            title = 'Проверьте ответы анкеты';
        }
        else if (!workflow.draft) {
            target = 'fit';
            title = 'Оцените соответствие и уточните пробелы';
        }
        else {
            target = channel === 'telegram' ? 'telegram' : 'form';
            title = channel === 'telegram' ? 'Продолжите подготовку в Telegram' : 'Откройте и прочитайте форму отклика';
        }
        return { target, title, uncertain, sent };
    }
    function commandResult(command) {
        try {
            const value = typeof command?.result === 'string' ? JSON.parse(command.result) : command?.result;
            return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
        }
        catch {
            return {};
        }
    }
    function careerConnection(worker) {
        if (worker?.connected)
            return { state: 'ready', message: 'Обработчик форм компаний на связи.' };
        return {
            state: 'offline',
            message: 'Обработчик форм компаний не на связи. В Chrome перезагрузите расширение «ML Research Vacancy Search», проверьте подключение сервиса и доступ к карьерным сайтам. Подключение HH само по себе не подтверждает работу форм компаний.'
        };
    }
    root.WorkflowCore = { nextStep, commandResult, careerConnection };
})(globalThis);
