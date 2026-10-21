"""Run a private operator Bot API bot plus a Telethon user account for Giga recruiter.

First: .venv/bin/python telegram_recruiter.py --login
Then:  .venv/bin/python telegram_recruiter.py
"""
import argparse
import asyncio
import getpass
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from src.application_store import ApplicationStore
from src.recruiter_controller import RecruiterController

ROOT=Path(__file__).resolve().parent
TARGET='giga_recruiter_bot'

def telegram_parts(text):
    part=[];units=0
    for char in text:
        width=2 if ord(char)>0xffff else 1
        if units+width>3500:yield ''.join(part);part=[];units=0
        part.append(char);units+=width
    if part:yield ''.join(part)

def session_path():
    directory=ROOT/'.cache/telegram';directory.mkdir(parents=True,exist_ok=True);os.chmod(directory,0o700)
    return directory/'recruiter-user'

def user_client():
    try:from telethon import TelegramClient
    except ImportError:raise ValueError('Установите Telegram-зависимости: uv sync --extra telegram') from None
    id=os.environ.get('TELEGRAM_API_ID','');hash=os.environ.get('TELEGRAM_API_HASH','')
    if not id.isdigit() or len(hash)!=32:raise ValueError('Задайте TELEGRAM_API_ID и TELEGRAM_API_HASH в .env проекта.')
    return TelegramClient(str(session_path()),int(id),hash,flood_sleep_threshold=0,request_retries=0,connection_retries=2)

def protect_session():
    for path in session_path().parent.glob('recruiter-user*'):
        if path.is_file():os.chmod(path,0o600)

def snapshot(message):
    if not message:return None
    buttons=[]
    for row in message.buttons or []:
        for button in row:
            raw=button.button
            buttons.append({'text':button.text,'kind':type(raw).__name__,
                'data':getattr(raw,'data',b'').hex(),'url':getattr(raw,'url','')})
    stamp=message.edit_date or message.date
    return {'id':message.id,'text':message.raw_text or '[Нет текстового вопроса; откройте Telegram для просмотра вложения.]','buttons':buttons,'version':stamp.isoformat() if stamp else ''}

class UserTransport:
    def __init__(self,client,entity):self.client=client;self.entity=entity
    async def observe(self):
        messages=await self.client.get_messages(self.entity,limit=10)
        incoming=next((message for message in messages if not message.out),None)
        return snapshot(incoming)
    async def start(self,start_param=None,random_id=None):
        if start_param is None:return await self.client.send_message(self.entity,'/start',parse_mode=None,link_preview=False)
        from telethon.tl.functions.messages import StartBotRequest
        return await self.client(StartBotRequest(bot=self.entity,peer=self.entity,start_param=start_param,random_id=random_id))
    async def send_answer(self,text,reply_to):return await self.client.send_message(self.entity,text,reply_to=reply_to,parse_mode=None,link_preview=False)
    async def click(self,message_id,index):
        message=await self.client.get_messages(self.entity,ids=message_id)
        if not message:raise ValueError('Сообщение удалено.')
        flat=[button for row in message.buttons or [] for button in row]
        if index<0 or index>=len(flat) or type(flat[index].button).__name__ not in {'KeyboardButton','KeyboardButtonCallback'}:
            raise ValueError('Кнопку этого типа нужно обработать в Telegram вручную.')
        return await flat[index].click()

class OperatorBot:
    def __init__(self,token,owner):
        import httpx
        self.http=httpx.AsyncClient(timeout=40);self.url='https://api.telegram.org/bot'+token+'/';self.owner=int(owner)
    async def call(self,method,data):
        try:
            response=await self.http.post(self.url+method,json=data);result=response.json()
            if result.get('ok') is False:
                from src.delivery_store import DeliveryRejected
                raise DeliveryRejected('Telegram Bot API отклонил '+method+'. Проверьте токен, доступ и webhook.')
            if not response.is_success:raise ValueError('Нет подтверждения Telegram Bot API.')
            return result['result']
        except ValueError:raise
        except Exception:raise ValueError('Нет ответа управляющего Telegram-бота.') from None
    async def send(self,text,keyboard=None):
        from src.telegram_presentation import format_text,keyboard_rows
        parts=list(telegram_parts(text)) or [' ']
        receipts=[]
        for index,part in enumerate(parts):
            payload={'chat_id':self.owner,'text':format_text(part),'parse_mode':'HTML','link_preview_options':{'is_disabled':True}}
            if keyboard and index==len(parts)-1:
                payload['reply_markup']={'inline_keyboard':keyboard_rows(keyboard)}
            receipt=await self.call('sendMessage',payload);receipts.append(receipt['message_id'])
        return receipts
    async def edit(self,message_id,text,keyboard=None):
        from src.agent_progress import EditRetry
        from src.telegram_presentation import format_text,keyboard_rows
        payload={'chat_id':self.owner,'message_id':message_id,'text':format_text(text),'parse_mode':'HTML','link_preview_options':{'is_disabled':True}}
        if keyboard:payload['reply_markup']={'inline_keyboard':keyboard_rows(keyboard)}
        try:
            response=await self.http.post(self.url+'editMessageText',json=payload);result=response.json()
            if result.get('ok'):return True
            description=str(result.get('description','')).lower()
            if 'message is not modified' in description:return True
            if 'message to edit not found' in description or "message can't be edited" in description:return False
            raise EditRetry(result.get('parameters',{}).get('retry_after',30))
        except EditRetry:raise
        except Exception:raise EditRetry(30) from None
    async def send_prompt(self,text):
        try:
            response=await self.http.post(self.url+'sendDocument',data={'chat_id':str(self.owner),'caption':'Промпт без API: откройте файл, скопируйте текст в ChatGPT.'},files={'document':('prompt-chatgpt.txt',text.encode('utf-8'),'text/plain; charset=utf-8')})
            if not response.is_success or not response.json().get('ok'):raise ValueError('Telegram не принял файл промпта. Попробуйте ещё раз.')
        except ValueError:raise
        except Exception:raise ValueError('Не удалось передать файл промпта в управляющий бот.') from None
    async def ack(self,id):await self.call('answerCallbackQuery',{'callback_query_id':id})

async def login():
    from telethon.errors import SessionPasswordNeededError
    client=user_client()
    try:
        await client.connect()
        if not await client.is_user_authorized():
            phone=getpass.getpass('Номер Telegram (ввод скрыт): ')
            await client.send_code_request(phone)
            try:await client.sign_in(phone=phone,code=getpass.getpass('Код Telegram (ввод скрыт): '))
            except SessionPasswordNeededError:await client.sign_in(password=getpass.getpass('Пароль 2FA (ввод скрыт): '))
        me=await client.get_me()
        if me.bot:raise ValueError('Нужна сессия вашего пользовательского аккаунта, а не бот.')
        expected=os.environ.get('TELEGRAM_OWNER_ID')
        if expected and str(me.id)!=expected:raise ValueError('Аккаунт не совпадает с TELEGRAM_OWNER_ID.')
        print('Вход выполнен. Ваш TELEGRAM_OWNER_ID:',me.id)
        print('Сообщения рекрутеру не отправлялись.')
    finally:await client.disconnect();protect_session()

async def run(operator_only=False,notify_ready=False):
    import fcntl
    from src.workflow_bot import WorkflowBot
    token=os.environ.get('TELEGRAM_BOT_TOKEN','');owner=os.environ.get('TELEGRAM_OWNER_ID','')
    if not token or not owner.isdigit():raise ValueError('Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_OWNER_ID в .env.')
    lock_path=session_path().parent/'operator.lock'
    lock_file=lock_path.open('a');os.chmod(lock_path,0o600)
    try:fcntl.flock(lock_file,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise ValueError('Управляющий бот уже запущен.') from None
    operator=OperatorBot(token,owner);client=None;progress_updates=None
    store=ApplicationStore(ROOT/'.cache/applications/state.sqlite3')
    try:
        me=await operator.call('getMe',{});expected=os.getenv('TELEGRAM_BOT_USERNAME','baniartbot').lstrip('@').lower()
        if me.get('username','').lower()!=expected:raise ValueError('Токен относится к другому боту. Проверьте TELEGRAM_BOT_USERNAME.')
        webhook=await operator.call('getWebhookInfo',{})
        if webhook.get('url'):raise ValueError('У бота настроен webhook. Он не изменён; для long polling нужен отдельный бот.')
        chat=await operator.call('getChat',{'chat_id':int(owner)})
        if chat.get('type')!='private':raise ValueError('TELEGRAM_OWNER_ID должен указывать ваш личный чат.')
        workflow=WorkflowBot(store,operator,owner);controller=None
        progress_updates=asyncio.create_task(workflow.progress_updates())
        if not operator_only and session_path().with_suffix('.session').exists():client=user_client()
        from src.runtime_health import GigaHealth,write_health
        giga_health=GigaHealth(store,client,owner)
        workflow.giga_ready=False
        async def attach_giga():
            nonlocal controller
            if not await giga_health.check():return False
            if controller is not None:return True
            try:
                from telethon import events
                entity=await asyncio.wait_for(client.get_entity(TARGET),timeout=8)
                if not entity.bot or entity.username.lower()!=TARGET:
                    write_health(store,'giga','unauthorized');return False
                controller=RecruiterController(store,operator,UserTransport(client,entity),owner,ROOT/'.cache/recruiter_answers')
                async def incoming(event):
                    current=snapshot(event.message)
                    try:await controller.receive(current['id'],current['text'],current['buttons'],current['version'])
                    except Exception:logging.warning('Не удалось обработать вопрос рекрутера. Используйте /question.')
                client.add_event_handler(incoming,events.NewMessage(chats=entity,incoming=True))
                client.add_event_handler(incoming,events.MessageEdited(chats=entity,incoming=True))
                return True
            except Exception:
                write_health(store,'giga','error');return False
        workflow.giga_ready=await attach_giga()
        print('@'+expected+' запущен. Подборки 10:00/19:00 Europe/Moscow; команды /today /hh /sync_hh. Telethon: '+('подключён' if controller else 'не подключён; для входа используйте --login.'),flush=True)
        if notify_ready:
            await workflow.notify('ready:0.9.0','CRM поиска работы подключена.\nЭтапы: общение с рекрутером → первый / второй / третий этап → отказ или оффер.\n/hh — отклики, этапы и обсуждение писем\n/today — подборка с проверкой активности\n/sync_hh — обновить отклики HH\nПодборки: 10:00 и 19:00 по Москве. Для проверки вакансий подключите HH один раз в параметрах расширения. /start — главное меню; /status — состояние Chrome и Giga.')
            print('Уведомление о готовности сохранено в очереди доставки.',flush=True)
        # A restart preserves pending messages and scheduled delivery state; no greeting spam.
        while True:
            workflow.giga_ready=await attach_giga()
            offset=int(store.setting('operator_offset') or 0)
            try:
                updates=await operator.call('getUpdates',{'offset':offset,'timeout':25,'allowed_updates':['message','callback_query']})
                for update in updates:
                    # Never replay an approval or a paid generation after an interrupted handler.
                    store.setting('operator_offset',update['update_id']+1)
                    if not await workflow.update(update):
                        if controller and workflow.giga_ready:await controller.update(update)
                        else:
                            cb=update.get('callback_query');m=update.get('message',{});actor=(cb or m).get('from',{});chat=(cb.get('message',{}) if cb else m).get('chat',{})
                            if actor.get('id')==int(owner) and chat.get('id')==int(owner) and chat.get('type')=='private':
                                if cb:await operator.ack(cb['id'])
                                await operator.send('Соединение Giga пока не подтверждено. /status покажет переподключение. Если сессия истекла, выполните вход:  .venv/bin/python telegram_recruiter.py --login. Затем перезапустите бот без --operator-only. Подборки и HH уже доступны: /today /hh.')
            except ValueError:
                logging.warning('Нет ответа Telegram или недоступен контекст. Отправка автоматически не повторяется; повтор чтения через 5 секунд.')
                await asyncio.sleep(5)
            # Scheduling and durable receipts do not depend on a successful long poll.
            try:await workflow.tick()
            except Exception:logging.warning('Задача конвейера не завершена; состояние сохранено для следующего прохода.')
    finally:
        if progress_updates:
            progress_updates.cancel()
            from contextlib import suppress
            with suppress(asyncio.CancelledError):await progress_updates
        await operator.http.aclose()
        from src.runtime_health import write_health
        write_health(store,'giga','offline')
        if client:await client.disconnect();protect_session()
        lock_file.close()

async def check_models():
    from openai import AsyncOpenAI
    from src.recruiter_answers import MODELS
    try:
        async with AsyncOpenAI(timeout=20,max_retries=0) as client:
            available={m.id for m in (await client.models.list()).data}
        print('OpenAI key valid: true')
        for alias,model in MODELS.items():print(alias,model,'available:',model in available)
        print('Available text models:',', '.join(sorted(m for m in available if m.startswith(('gpt-5','gpt-4.1')) and not any(x in m for x in ('audio','realtime','search','codex','chat-latest')))))
    except Exception as error:
        print('OpenAI check failed:',type(error).__name__,'HTTP',getattr(error,'status_code',None))

async def verify_draft(app_id):
    from src.application_conversation import discuss
    from src.application_workflow import hashed
    store=ApplicationStore(ROOT/'.cache/applications/state.sqlite3')
    app=store.workflow(app_id)
    if app['context']['channel']!='hh' or not app['workflow']['draft']:raise ValueError('Для проверки нужен существующий HH-отклик с письмом.')
    store.validate_current(app_id)
    result=await asyncio.to_thread(discuss,store,app_id,'Проверка редактора: сократи текущее сопроводительное письмо до трёх предложений. Подчеркни интерес к генеративным моделям и сильной R&D-команде. Факты опыта используй только из CV; если техническая гипотеза не подтверждается вакансией или CV, убери её. Не отправляй отклик.', 'smoke-'+hashed([app_id,app['workflow']['revision']])[:24],'luna')
    print('model:',result['model'],'draft_saved:',result['draft_applied'],'needs_user:',result['needs_user'],'evidence_count:',len(result['evidence']))
    print(result['reply'])
    print(result['draft_text'] or '')
    print('Отклик HH не отправлялся.')

def main():
    load_dotenv(ROOT/'.env');logging.getLogger('httpx').setLevel(logging.CRITICAL)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--login',action='store_true');parser.add_argument('--check-models',action='store_true');parser.add_argument('--verify-draft',metavar='APPLICATION_ID');parser.add_argument('--notify-ready',action='store_true');parser.add_argument('--operator-only',action='store_true',help='Подборки и HH без сессии личного аккаунта');args=parser.parse_args()
    try:asyncio.run(verify_draft(args.verify_draft) if args.verify_draft else check_models() if args.check_models else login() if args.login else run(args.operator_only,args.notify_ready))
    except ImportError:print('Установите Telegram-зависимости: uv sync --extra telegram');return 1
    except (ValueError,KeyboardInterrupt) as error:
        print(str(error) if isinstance(error,ValueError) else 'Остановлено. Состояние сохранено.');return 1
    except Exception:
        print('Telegram-клиент остановлен из-за ошибки подключения/авторизации. Проверьте локальные настройки; секреты не выводятся.');return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
