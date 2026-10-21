"""Evidence-bearing market tags, separate from personal fit and application status.

Role tags use titles, domain tags use job text; no model/network calls. A domain
is not an assertion of military purpose or a verified government contract.
"""
import re

DOMAINS=[
 ('drones','Дроны / БПЛА',r'дрон[а-я]*|\b(?:бпла|бплс|бла|uav|fpv|px4|ardupilot)\b|беспилотн.{0,20}(?:летатель|пол[её]т)|аэрологист'),
 ('space','Космос / Спутниковые системы',r'космическ.{0,25}(?:аппарат|систем|отрасл|связ|мисси)|спутников.{0,30}(?:связ|группиров|систем)|низкоорбит|орбитальн.{0,25}(?:аппарат|группиров|станци)|spacecraft|satellite'),
 ('automotive','Automotive / ADAS',r'\badas\b|automotive|self.driving|autonomous driving|автономн.{0,30}вожден|(?:беспилот|автономн|моделирован).{0,50}автомобил|автомобил.{0,50}(?:беспилот|автономн|модел)|автомобильн.{0,15}(?:электроник|промышлен)'),
 ('sensors','Sensors / Sensor Fusion',r'sensor fusion|sensor calibration|state estimation|\bslam\b|\bvslam\b|\bvio\b|лидар|\blidar\b|сбор.{0,30}(?:камер|датчик)|(?:объединени|слияни|комплексирован).{0,35}(?:сенсор|датчик)|калибровк.{0,20}(?:камер|сенсор|датчик)|биосенсор|sensor ai|wearables'),
 ('robotics','Робототехника / Автономные системы',r'robotics|робототех|робот[ -]?манипулятор|\bros2?\b|автономн.{0,20}(?:систем|робот)'),
 ('defense','Оборонная тематика · признаки',r'\b(?:впк|опк|гоз)\b|гособоронзаказ|(?:военно|оборонно)[ -]промышлен|оборонн.{0,15}(?:заказ|отрасл|промышлен|комплекс)|военн.{0,15}(?:назначени|техник|продукци)|министерств.{0,5}оборон'),
 ('government','Госзаказ / Госзаказчики · признаки',r'гос(?:ударственн[а-я]*)?[ -]?(?:оборон)?заказ|гос(?:ударственн[а-я]*)?[ -]?контракт|государственн.{0,15}(?:заказ|закупк)|госзакупк|\bгоз\b')]
ROLES=[
 ('education','Образование / Преподавание',r'преподавател|учител|репетитор|доцент|профессор|педагог|методист|тьютор'),
 ('quant','Quant / Trading',r'quant|trading|трейдинг|алгоритмическ.{0,8}торгов'),
 ('data_engineering','Data Engineering / Платформы данных',r'data.{0,4}engineer|инженер.{0,4}данных|дата.{0,3}инженер|analytics engineer|data platform|data warehouse|data lake|data quality|\betl\b|\bdwh\b|big data'),
 ('qa','QA / Автотестирование',r'\bqa\b|\baqa\b|sdet|тестиров|автотест|test.{0,4}(?:engineer|automat)|quality assurance'),
 ('embedded','Embedded / Firmware / Электроника',r'embedded|firmware|встраиваем|микроконтрол|плис|fpga|\bmcu\b|\brtl\b|\bpdk\b|сбис|hardware|cpu verification'),
 ('security','Кибербезопасность / Reverse',r'reverse|реверс|кибербезопас|киберугроз|криптограф|информационн.{0,5}безопас|security|appsec|pentest|\bsast\b|\bsiem\b|\bsoc\b'),
 ('devops','DevOps / SRE / Инфраструктура',r'devops|\bsre\b|системн.{0,5}админист|системн.{0,5}инженер|platform engineer|database administrator|\bdba\b'),
 ('vision','Computer Vision / Imaging',r'computer vision|компьютерн.{0,6}зрени|\bcv\b|imaging|обработк.{0,5}изображ|машинн.{0,6}зрени'),
 ('nlp','NLP / Speech',r'\bnlp\b|speech|лингвист|обработк.{0,8}(?:речи|текст)|распознаван.{0,5}речи'),
 ('scientific','Научные вычисления / Моделирование',r'научн.{0,6}сотрудник|research scientist|r&d|математик|физик|биоинформатик|bioinformatics|вычислительн|моделирован|\bcfd\b|\bhpc\b|динамик.{0,6}пол[её]т'),
 ('analytics','Аналитика данных / Продукта / Бизнеса',r'аналитик|analyst|business intelligence|\bbi\b|analytics'),
 ('management','Product / Project / Руководство',r'product|продакт|project|менеджер|руководител|директор|\bcto\b|head of|delivery|team.?lead|team lead|тимлид|начальник|chief.{0,15}officer'),
 ('ai_training','AI-тренеры / Разметка данных',r'ai[ -]?тренер|ии[ -]?тренер|разметк.{0,8}данных|асессор|аннотатор'),
 ('ai_automation','Прикладной AI / Агенты / Автоматизация',r'\bai\b|\bии\b|искусственн.{0,6}интеллект|агентн|ai.?агент|prompt|промпт|\bgpt\b|чат.?бот'),
 ('frontend','Frontend / Fullstack / Mobile',r'front.?end|full.?stack|фронтенд|фулстек|android|\bios\b|flutter|мобильн.{0,10}разработ|\breact\b|\bvue\b'),
 ('systems','C++ / Rust / Системная разработка',r'c\+\+|с\+\+|\brust\b|системн.{0,6}(?:программист|разработ)|\blow.latency\b|\bsdr\b|\bцос\b'),
 ('backend','Backend / Python / Сервисы',r'backend|back.end|бэкенд|бэк.енд|python|java|\bgo\b|golang|\.net|\bphp\b|\bruby\b'),
 ('support','Сопровождение / Поддержка',r'сопровожден|технич.{0,6}поддерж|support|helpdesk|инженер.{0,5}внедрен')]

# Names are hints explicitly shown as such, not verified military-purpose claims.
DEFENSE_EMPLOYER=re.compile(r'калашников|алмаз[\s-]*антей|концерн\s+вко',re.I)
SPACE_EMPLOYER=re.compile(r'бюро[\s«»"-]*1440\b|bureau[\s-]*1440\b',re.I)

def matches(data,body):
    title=data.get('title','');company=data.get('company','');text=title+'\n'+body;out=[]
    def add(key,match,source,basis,value=None):
        value=value if value is not None else company if source=='company' else title if source=='title' else text
        out.append({'category':key,'match':match.group(0),'quote':value[max(0,match.start()-55):match.end()+95].strip(),'source':source,'basis':basis})
    for key,_,pattern in DOMAINS:
        value=title+'\n'+data.get('description','') if key in ('defense','government') else text;source='job_text'
        for match in re.finditer(pattern,value,re.I):
            before=value[max(0,match.start()-65):match.start()]
            if key in ('defense','government') and re.search(r'(?:не\s+(?:работаем|работа|связан[а-я]*|участвуем|выполняем|относимся)|без(?:\s+работы)?|нет).{0,40}$',before,re.I):continue
            add(key,match,source,'Признак в тексте вакансии' if source=='job_text' else 'Работодатель указан в вакансии',value);break
        else:
            if key=='defense':
                match=DEFENSE_EMPLOYER.search(company)
                if match:add(key,match,'company','Возможная связь по названию работодателя; назначение проекта требует проверки')
    # Employer identity is a facet, not a specialization or a separate flow.
    employer=SPACE_EMPLOYER.search(company)
    if employer and not any(e['category']=='space' for e in out):
        add('space',employer,'company','Направление по работодателю Бюро 1440; задачи конкретной роли уточняются')
    for key,_,pattern in ROLES:
        if key=='ai_automation' and any(e['category']=='ai_training' for e in out):continue
        match=re.search(pattern,title,re.I)
        if match:add(key,match,'title','Направление по названию роли; для короткой карточки предварительно')
    return out

WORK_FORMATS=[
    ('remote','Удалённая работа',r'удаленн|удалённ|дистанционн|\bremote\b|из любой точки|работа из дома|удаленный формат|удалённый формат'),
    ('hybrid','Гибридный формат',r'гибридн|гибрид|\bhybrid\b|частично в офисе|несколько дней в офисе'),
    ('onsite','Офис / Onsite',r'только в офис|в офис[еа]|на территории работодателя|\bonsite\b|\bon-site\b')
]
REGIONS=[
    ('moscow','Москва',r'москв|moscow'),
    ('spb','Санкт-Петербург',r'санкт-петербург|петербург|питер|спб|st\.?\s*petersburg'),
    ('rf','Регионы РФ',r'росси|рф|новосибирск|екатеринбург|казан|нижний новгород|самара|ростов|томск|красноярск|воронеж|пермь|уфа'),
    ('global','Международный / Релокация',r'релокац|relocat|европ|сша|серби|кипр|армени|грузи|дубай|оаэ|казахстан|турци|германи|великобритан|лондон|берлин')
]

def classify_work_format(data,body=''):
    title=data.get('title','')
    locations=' '.join(map(str,data.get('locations') or []))
    loc=str(data.get('location') or '')
    city=str(data.get('city') or '')
    text=f"{title}\n{locations}\n{loc}\n{city}\n{body}"
    fmt='unknown'
    for key,_,pat in WORK_FORMATS:
        if re.search(pat,text,re.I):
            fmt=key;break
    reg='unknown'
    for key,_,pat in REGIONS:
        if re.search(pat,text,re.I):
            reg=key;break
    return fmt,reg
