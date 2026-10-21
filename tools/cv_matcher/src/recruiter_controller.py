"""Human-reviewed Telegram Q&A state machine; injected transports make it testable."""
import asyncio
import hashlib
from .recruiter_answers import MODELS, draft_answer
from .candidate_facts import answer_context

class RecruiterController:
    @staticmethod
    def draft_token(text):return hashlib.sha256(text.encode()).hexdigest()[:12]
    def __init__(self,store,operator,userbot,owner_id,cache_dir,*,drafter=draft_answer):
        self.store=store;self.operator=operator;self.userbot=userbot;self.owner_id=int(owner_id)
        self.cache_dir=cache_dir;self.drafter=drafter;self.lock=asyncio.Lock()
    def keyboard(self,turn):
        id=turn['id']
        rows=[[('Luna',f'gen:{id}:luna'),('Terra',f'gen:{id}:terra'),('Sol',f'gen:{id}:sol')]]
        if turn['status']=='draft':rows.append([('Отправить',f"send:{id}:{self.draft_token(turn['draft'])}"),('Редактировать',f'edit:{id}')])
        rows.append([('Ответ без API',f'offline:{id}'),('Свой ответ / из ChatGPT',f'own:{id}')]);rows.append([('Уточнить опыт',f'facts:{id}'),('Пожелания к ответу',f'prefs:{id}')])
        for index,button in enumerate(turn['buttons']):
            if button['kind'] in {'KeyboardButton','KeyboardButtonCallback'}:
                rows.append([(button['text'][:55],f'choice:{id}:{index}')])
        return rows
    async def show(self,turn,extra=''):
        app=self.store.get(turn['app_id']);c=app['context']
        text=f"{c['vacancy']['title']}\nCV: {c['resume_title']}\nЦель: {c['goal'] or 'не указана'}\n\nВопрос:\n{turn['question'][:2500]}"
        await self.operator.send(text)
        preview=('Черновик ('+turn['model']+'):\n'+turn['draft']) if turn['draft'] else 'Выберите модель для черновика или напишите свой ответ.'
        if turn['status']=='needs_input':preview+='\n\nНужны ваши уточнения. Сначала отредактируйте ответ.'
        await self.operator.send(preview+('\n\n'+extra if extra else ''),self.keyboard(turn))
    async def receive(self,source_id,text,buttons,version=''):
        app=self.store.active()
        if not app:return
        if not self.store.giga_question_current(app['id'],source_id,self.store.fingerprint(text,buttons,version)):return
        turn,changed=self.store.receive(app['id'],source_id,text,buttons,version)
        if changed:await self.show(turn)
    async def check_current(self,turn):
        app=self.store.active()
        if not app or app['id']!=turn['app_id']:raise ValueError('Этот диалог сейчас не активен.')
        current=await self.userbot.observe()
        if current and not self.store.giga_question_current(app['id'],current['id'],self.store.fingerprint(current['text'],current['buttons'],current.get('version',''))):raise ValueError('Это сообщение относится к предыдущему интервью. Сначала запустите приглашение текущей вакансии.')
        if not current or current['id']!=turn['source_id'] or self.store.fingerprint(current['text'],current['buttons'],current.get('version',''))!=turn['fingerprint']:
            raise ValueError('Вопрос/кнопки у рекрутера изменились. Нажмите /question и подготовьте новый ответ.')
        return app
    async def send(self,turn_id,choice=None,expected_token=None):
        turn=self.store.turn(turn_id)
        if choice is None and (turn['status']!='draft' or not turn['draft']):raise ValueError('Сначала подготовьте или отредактируйте ответ.')
        if choice is None and expected_token!=self.draft_token(turn['draft']):raise ValueError('Черновик уже изменился. Нажмите «Отправить» под последней показанной версией.')
        await self.check_current(turn)
        if choice is not None:
            if choice<0 or choice>=len(turn['buttons']) or turn['buttons'][choice]['kind'] not in {'KeyboardButton','KeyboardButtonCallback'}:
                raise ValueError('Эту кнопку нужно обработать вручную в Telegram (контакт, геопозиция, ссылка или WebApp).')
            self.store.draft(turn_id,turn['buttons'][choice]['text'],'manual_button')
        self.store.claim_send(turn_id)
        try:
            if choice is None:await self.userbot.send_answer(turn['draft'],turn['source_id'])
            else:await self.userbot.click(turn['source_id'],choice)
        except Exception:
            self.store.finish_send(turn_id,False)
            raise ValueError('Результат отправки неизвестен. Проверьте диалог с рекрутером; автоматический повтор запрещён.') from None
        self.store.finish_send(turn_id,True)
        await self.operator.send('Ответ отправлен в @giga_recruiter_bot. Жду следующий вопрос.')
    async def update(self,update):
        callback=update.get('callback_query');message=update.get('message')
        actor=(callback or message or {}).get('from',{})
        chat=(callback.get('message',{}) if callback else message or {}).get('chat',{})
        if actor.get('id')!=self.owner_id or chat.get('id')!=self.owner_id or chat.get('type')!='private':return
        async with self.lock:
            try:
                if callback:
                    await self.operator.ack(callback['id'])
                    data=callback.get('data','').split(':');action=data[0]
                    if action!='facts':self.store.setting('awaiting_candidate_fact','')
                    if action in {'activate','gen','prefs','facts','offline','edit','own'}:self.store.setting('workflow_waiting','')
                    if action in {'activate','gen','edit','own'}:self.store.setting('awaiting_answer_preferences','');self.store.setting('awaiting_answer','')
                    if action=='activate':
                        app=self.store.activate(data[1]);await self.operator.send('Активен отклик: '+app['context']['vacancy']['title']+'\n/start_recruiter — проверить запуск интервью по приглашению. /question — продолжить существующий диалог. /pause — пауза. /done — завершить.')
                    elif action=='gstart':
                        app=self.store.active()
                        if not app or app['id']!=data[1]:raise ValueError('Сначала выберите этот Giga-диалог.')
                        current=await self.userbot.observe()
                        baseline={'id':current['id'],'fingerprint':self.store.fingerprint(current['text'],current['buttons'],current.get('version',''))} if current else None
                        run=self.store.claim_giga_start(app['id'],data[2],baseline)
                        try:await self.userbot.start(run['start_param'],run['nonce'])
                        except Exception:
                            self.store.finish_giga_start(run['invite_id'],False)
                            raise ValueError('Результат запуска Giga неизвестен. Проверьте диалог; повторный запуск запрещён. /question — прочитать новый вопрос.') from None
                        self.store.finish_giga_start(run['invite_id'],True)
                        await self.operator.send('Приглашение этой вакансии запущено. /question — прочитать вопрос. Каждый ответ отправляется только после вашего подтверждения.')
                    elif action=='screened':
                        result=self.store.complete_screening(data[1],data[2],confirmed=True)
                        await self.operator.send('AI-интервью завершено вами. Общий план CRM обновлён; дальнейший этап, если он уже был записан, сохранён.',[[('Открыть общий отклик',f'w:open:{result["case_id"]}')]])
                    elif action=='gen':
                        turn=self.store.turn(data[1]);app=await self.check_current(turn)
                        if turn['status'] not in {'received','draft','needs_input'}:raise ValueError('Вопрос уже обработан.')
                        await self.operator.send('Готовлю черновик: '+data[2]+'. Он не отправится без вашего нажатия.')
                        result=await asyncio.to_thread(self.drafter,answer_context(self.store,app['context'],preferences=self.store.setting('answer_preferences:'+turn['id']) or '',history=self.store.history(app['id'])),turn['question'],data[2],self.cache_dir)
                        await self.check_current(turn)
                        turn=self.store.draft(turn['id'],result['answer'],result['model'],result['needs_user'])
                        evidence='\n'.join(item.get('id','')+': '+item['quote'] for item in result['evidence'])
                        await self.show(turn,'Уточнения: '+('; '.join(result['missing']) or 'нет')+'\n'+result['review_note'])
                        if evidence:await self.operator.send('Источники: R — CV; U — ваши уточнения; H — утверждённые ответы; G — цель.\n'+evidence)
                    elif action=='facts':
                        turn=self.store.turn(data[1]);await self.check_current(turn);self.store.setting('awaiting_candidate_fact',turn['id']);self.store.setting('awaiting_answer','');self.store.setting('awaiting_answer_preferences','')
                        await self.operator.send('Сообщите факт о вашем опыте от первого лица: что именно делали, с какой моделью / библиотекой и в каком контексте. Сохраню как ваше уточнение отдельно от HH-резюме, для API и режима без API. Например: «В исследовательском стенде подключал LoRA через Diffusers». Не указывайте навыки, которыми ещё только хотите заниматься. /cancel — отмена.')
                    elif action=='prefs':
                        turn=self.store.turn(data[1]);await self.check_current(turn);self.store.setting('awaiting_answer_preferences',turn['id']);self.store.setting('awaiting_answer','')
                        await self.operator.send('Пришлите пожелания и дополнительные факты для ответа. Они будут приложены к промпту в обоих режимах, отдельно от фактов CV. /cancel — отмена.')
                    elif action=='offline':
                        from .external_prompt import build_prompt
                        turn=self.store.turn(data[1]);app=await self.check_current(turn)
                        if turn['status'] not in {'received','draft','needs_input'}:raise ValueError('Вопрос уже обработан.')
                        prompt=build_prompt(answer_context(self.store,app['context']),'answer',question=turn['question'],comments=self.store.setting('answer_preferences:'+turn['id']) or '',draft=turn['draft'],history=self.store.history(app['id']))
                        if hasattr(self.operator,'send_prompt'):await self.operator.send_prompt(prompt)
                        else:await self.operator.send(prompt)
                        self.store.setting('awaiting_answer_preferences','');self.store.setting('awaiting_answer',turn['id'])
                        await self.operator.send('Вставьте промпт в ChatGPT. Пришлите готовый ответ сюда: он сохранится как редактируемый черновик. Вызовов API модели: 0. Отправка рекрутеру — отдельной кнопкой. /cancel — отмена.')
                    elif action in {'edit','own'}:

                        turn=self.store.turn(data[1]);await self.check_current(turn)
                        self.store.setting('awaiting_answer',turn['id'])
                        await self.operator.send('Пришлите полный текст ответа одним сообщением. Затем покажу его с кнопкой «Отправить». /cancel отменит ввод.')
                    elif action=='send':await self.send(data[1],expected_token=data[2])
                    elif action=='choice':await self.send(data[1],int(data[2]))
                    else:raise ValueError('Неизвестная кнопка.')
                else:
                    if message.get('text','').startswith('/') and message.get('text')!='/cancel':self.store.setting('workflow_waiting','')
                    await self.message(message.get('text',''))
            except (ValueError,KeyError,IndexError) as error:await self.operator.send(str(error) if isinstance(error,ValueError) else 'Кнопка устарела. Нажмите /question.')
    async def message(self,text):
        if text.startswith('/start') and not text.startswith('/start_recruiter') or text=='/applications':
            rows=[[(a['context']['vacancy']['title'][:45],f"activate:{a['id']}")] for a in self.store.list() if a['context']['channel']=='telegram' and a['status'] not in {'completed','submitted'}]
            await self.operator.send('Выберите отклик. Новые отклики добавляются кнопкой «Откликнуться» в расширении. Модели: Luna / Terra / Sol. /question — текущий вопрос; /pause — пауза; /done — завершить.',rows)
        elif text=='/cancel':self.store.setting('awaiting_candidate_fact','');self.store.setting('awaiting_answer','');self.store.setting('awaiting_answer_preferences','');await self.operator.send('Ввод отменён.')
        elif text=='/done':
            app=self.store.active()
            if not app:raise ValueError('Сначала выберите диалог: /applications.')
            preview=self.store.screening_preview(app['id'])
            await self.operator.send('Подтвердите: AI-интервью по этой вакансии действительно завершено.\n'+preview['title']+'\nCV: '+preview['resume_title']+'\nПоследнее сообщение Giga:\n'+preview['last_message'][:2200]+'\nПосле подтверждения: AI-интервью пройдено → ждём приглашения. Более поздний этап CRM сохранится.',[[('Подтверждаю завершение AI-интервью',f'screened:{app["id"]}:{preview["token"]}')]])
        elif text=='/pause':
            app=self.store.active()
            if app:self.store.set_status(app['id'],'paused')
            self.store.setting('awaiting_answer','');await self.operator.send('Диалог приостановлен.')
        elif text=='/start_recruiter':
            app=self.store.active()
            if not app:raise ValueError('Сначала выберите отклик: /applications.')
            if self.store.giga_invitation(app['id']):
                preview=self.store.giga_start_preview(app['id'])
                await self.operator.send('Запустить первичное интервью в @Giga_recruiter_bot?\nВакансия: '+preview['title']+'\nCV: '+preview['resume_title']+'\nПриглашение из HH: '+preview['invite']['url']+'\nБудет отправлена команда запуска с параметром этой вакансии. Ответы на вопросы требуют отдельного подтверждения.',[[('Подтверждаю запуск этого интервью',f'gstart:{app["id"]}:{preview["token"]}')]])
                return
            key='started:'+app['id']
            if self.store.setting(key):raise ValueError('/start уже отправлялся для этого отклика. Используйте /question.')
            self.store.setting(key,'sending');self.store.setting('giga_current_invite','legacy:'+app['id'])
            try:await self.userbot.start()
            except Exception:raise ValueError('Неясно, получил ли бот /start. Проверьте диалог и используйте /question.') from None
            self.store.setting(key,'sent');await self.operator.send('/start отправлен. Жду вопрос рекрутера.')
        elif text=='/question':
            if not self.store.active():raise ValueError('Сначала выберите отклик: /applications.')
            current=await self.userbot.observe()
            if not current:raise ValueError('У бота пока нет сообщений. Используйте /start_recruiter.')
            if not self.store.giga_question_current(self.store.active()['id'],current['id'],self.store.fingerprint(current['text'],current['buttons'],current.get('version',''))):raise ValueError('Нового вопроса по этому приглашению пока нет. /start_recruiter — просмотреть запуск; прежний вопрос не привязывается к новой вакансии.')
            turn,_=self.store.receive(self.store.active()['id'],current['id'],current['text'],current['buttons'],current.get('version',''));await self.show(turn)
        elif text.startswith('/'):raise ValueError('Команды: /applications /question /pause /done /cancel.')
        else:
            fact_turn=self.store.setting('awaiting_candidate_fact')
            if fact_turn:
                turn=self.store.turn(fact_turn);app=await self.check_current(turn)
                from .candidate_facts import save
                save(self.store,app['context']['resume_id'],'telegram-'+self.draft_token(text),text,'owner_telegram:'+turn['id'])
                self.store.setting('awaiting_candidate_fact','');await self.show(turn,'Факт сохранён отдельно от HH-CV и будет источником U. Выберите модель заново или ответ без API; прежний черновик не изменён и не отправлен.');return
            preferences_id=self.store.setting('awaiting_answer_preferences')
            if preferences_id:
                if len(text)>4000:raise ValueError('Пожелания — до 4000 символов.')
                turn=self.store.turn(preferences_id);await self.check_current(turn);self.store.setting('answer_preferences:'+preferences_id,text);self.store.setting('awaiting_answer_preferences','');await self.show(turn,'Пожелания сохранены для API и режима без API.');return
            id=self.store.setting('awaiting_answer')
            if not id:raise ValueError('Сначала нажмите «Редактировать» или «Свой ответ» у нужного вопроса.')
            turn=self.store.turn(id);await self.check_current(turn);turn=self.store.draft(id,text)
            self.store.setting('awaiting_answer','');await self.show(turn)
