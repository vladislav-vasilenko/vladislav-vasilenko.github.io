"""Versioned local skill ontology and curated primary learning sources. No network."""
VERSION='career-skills-2'
CHECKED='2026-10-20'

# Effort is a planning range for one focused exercise, never time to mastery.
def skill(key,label,pattern,prerequisites=(),hours=(4,8),resources=()):
 return {'id':key,'label':label,'pattern':pattern,'prerequisites':list(prerequisites),'effort_hours':list(hours),'resource_ids':list(resources)}

SKILLS={s['id']:s for s in [
 skill('linear_algebra','Линейная алгебра',r'linear algebra|линейн\w* алгебр',hours=(6,12),resources=('dl_book',)),
 skill('calculus','Многомерный анализ',r'calculus|математическ\w* анализ|многомерн\w* анализ|дифференциальн\w* исчислен',hours=(6,12),resources=('dl_book',)),
 skill('probability','Вероятность и статистика',r'probability|statistics|вероятност|статистик',hours=(6,12),resources=('dl_book',)),
 skill('python','Python',r'\bpython\b|питон',hours=(3,6),resources=('python_tutorial',)),
 skill('pytorch','PyTorch / autograd',r'\bpytorch\b|\btorch\b|autograd',('python',),resources=('pytorch_basics',)),
 skill('deep_learning','Основы Deep Learning',r'deep learning|глубок\w*.{0,12}обуч|нейросет',('linear_algebra','calculus','probability','pytorch'),(8,16),('dl_book',)),
 skill('optimization','Оптимизация обучения',r'метод\w* оптимизац|gradient descent|\badamw?\b|\bsgd\b|градиентн\w*.{0,15}(?:спуск|оптимизац)',('calculus','deep_learning'),resources=('cs336',)),
 skill('transformers','Transformers / Attention',r'transformer|трансформер|attention|внимани\w* в модел',('deep_learning',),resources=('cs336',)),
 skill('tokenization','Токенизация и BPE',r'tokeniz|токенизац|\bbpe\b',('python',),resources=('cs336',)),
 skill('pretraining','LLM Pretraining',r'pre[\s-]?train|предобуч|претрен',('transformers','optimization','tokenization'),(8,16),('cs336',)),
 skill('data_curation','Подготовка обучающих данных',r'больш\w*.{0,15}датасет|работ\w*.{0,20}данн\w*|data curation|data dedup|дедупликац|очистк\w*.{0,20}данных|качеств\w*.{0,20}датасет|training data',('python',),resources=('cs336',)),
 skill('evaluation','Оценка моделей / Абляции',r'оцен\w*.{0,20}результат\w*.{0,20}эксперимент|evaluat|ablation|абляци|бенчмарк|benchmark|оценк\w*.{0,20}(?:модел|качеств)',('deep_learning',),resources=('cs336',)),
 skill('sft','SFT / Fine-tuning / LoRA',r'\bsft\b|fine[\s-]?tun|finetun|дообуч|\blora\b|\bpeft\b',('transformers','pytorch'),resources=('cs336',)),
 skill('rl','Reinforcement Learning',r'reinforcement learning|обучени\w* с подкреплен|\b(?:ppo|grpo|rlhf|rlvr)\b|\bRL\b',('probability','deep_learning'),(8,16),('cs336',)),
 skill('alignment','Post-training / Preference Optimization',r'post[\s-]?train|пост.?обуч|\b(?:dpo|rlhf|rlvr|grpo)\b|preference optim|alignment',('sft','rl'),(6,12),('cs336',)),
 skill('ode_sde','ODE / SDE и численное моделирование',r'\b(?:ode|sde)\b|стохастическ\w*.{0,18}(?:дифференц|уравнен)|дифференциальн\w* уравнен|fokker.planck',('calculus','probability','python'),(6,12),('mit_lab1',)),
 skill('diffusion','Diffusion / Score Matching',r'diffusion|диффуз|score[\s-]?matching|denoising',('ode_sde','deep_learning'),(8,16),('mit_lab2','ddpm')),
 skill('flow_matching','Flow Matching',r'flow[\s-]*matching|потоков\w*.{0,12}сопоставлен',('ode_sde','deep_learning'),(8,16),('mit_lab2','flow_paper')),
 skill('dit_vae','DiT / VAE / Latent Generative Models',r'\bdit\b|diffusion transformer|\bvae\b|вариационн\w* автоэнкод|latent diffusion',('diffusion','transformers'),(8,16),('mit_lab3',)),
 skill('distributed','Распределённое обучение / DDP',r'distributed training|распредел[её]нн\w*.{0,20}обуч|\bddp\b|\bnccl\b|torchrun',('pytorch',),resources=('fsdp2','cs336')),
 skill('fsdp','FSDP / ZeRO / Sharding',r'\bfsdp\w*\b|\bzero[\s-]?[123]?\b|deepspeed|шардинг',('distributed',),resources=('fsdp2',)),
 skill('cpp','C++',r'\b[cс]\+\+(?!\+)',hours=(6,12)),
 skill('cuda','CUDA / GPU kernels',r'\bcuda\b|\bcutlass\b|\bcute\b|gpu[\s-]?kernel|ядр\w*.{0,12}gpu',('cpp','linear_algebra'),(8,16),('cuda_guide','cs336')),
 skill('triton','Triton GPU kernels',r'\btriton\b',('pytorch','cuda'),(6,12),('cs336',)),
 skill('profiling','Профилирование и производительность',r'profiling|профилирован|nsight|memory hierarchy|иерархи\w* памяти|оптимизац\w*.{0,20}инференс',('pytorch',),resources=('cs336','cuda_guide')),
 skill('inference','LLM Inference / Serving',r'\binference\b|инференс|\bvllm\b|serving|tensor.?rt',('transformers',),resources=('cs336',)),
 skill('quantization','Квантизация',r'quantization|квантизац|\bint[48]\b',('linear_algebra','pytorch'),resources=('torchao',)),
 skill('mlx','Apple MLX',r'\bmlx\b',('python','deep_learning'),resources=('mlx_docs',)),
 skill('metal','Apple MPS / Metal',r'\bmps\b|\bmetal\b|apple silicon',('pytorch',),resources=('mps_docs',)),
 skill('robotics','Робототехника',r'robotics|робототех|робот[\s-]?манипулятор',('linear_algebra','python'),(8,16),('robotics_book',)),
 skill('control','Управление / MPC',r'control theory|теори\w* управлен|\bmpc\b|model predictive control|управлени\w*.{0,15}робот',('robotics','calculus'),resources=('robotics_book',)),
 skill('slam','SLAM / Sensor Fusion',r'\b(?:v?slam|vio|lidar)\b|sensor fusion|state estimation|лидар|слияни\w*.{0,15}сенсор',('robotics','probability'),(8,16),('robotics_book',)),
 skill('model_training','Обучение генеративных / CV-моделей',r'обуч\w*.{0,22}(?:генеративн|cv[- ]?модел)|model training|training (?:generative|vision) models',('python','pytorch','data_curation'),(8,16),('pytorch_basics',)),
 skill('research_methods','Воспроизведение исследований / Эксперименты',r'воспроизвод\w*.{0,30}(?:исследоват|стат|подход)|провер\w*.{0,20}гипотез|reproduc\w*.{0,20}(?:paper|research)|research methodology',('evaluation',),resources=('cs336',)),
 skill('torch_compile','torch.compile',r'torch\.compile',('pytorch',),resources=('pytorch_basics',)),
 skill('backend','Backend / API',r'fastapi|(?:backend|б[эе]кенд)[- ]?(?:сервис|service|разработ|develop|инженер)|архитектур\w*.{0,12}api',('python',)),
 skill('containers','Docker / Kubernetes',r'\bdocker\b|kubernetes|\bk8s\b|контейнеризац',('python',)),
 skill('agents','AI-агенты и проверка результатов',r'ai[- ]агент|ии[- ]агент|ai agents|agentic|агентн\w*.{0,15}(?:систем|сценар)',('python',)),
 skill('ros','ROS / ROS2',r'\bros2?\b',('robotics',)),
 ]}

def track(key,label,weights,aliases):
 return {'id':key,'label':label,'revision':1,'skills':{k:{'importance':w,'effort_hours':SKILLS[k]['effort_hours']} for k,w in weights.items()},'aliases':aliases,'catalog_version':VERSION,'source':'builtin'}

TRACKS={t['id']:t for t in [
 track('pretraining','LLM Pretraining',{'pretraining':3,'transformers':3,'data_curation':3,'distributed':2,'fsdp':2,'evaluation':2,'pytorch':2,'tokenization':2,'optimization':2},['pretraining','pre-training','претрейн','предобучение']),
 track('post_training','Post-training / RL',{'alignment':3,'rl':3,'sft':3,'evaluation':3,'transformers':2,'distributed':2,'pytorch':2},['post-training','post training','posttrain','post-train','rl','rlhf','постобучение']),
 track('generative','Generative Models Research',{'flow_matching':3,'diffusion':3,'dit_vae':3,'ode_sde':3,'evaluation':2,'transformers':2,'pytorch':2},['generative models','generative models research','генеративные модели','generative','diffusion','flow matching']),
 track('ml_systems','ML Systems',{'distributed':3,'fsdp':3,'cuda':3,'profiling':3,'triton':2,'inference':2,'quantization':2,'pytorch':2},['ml systems','ml-системы','распределенное обучение','распределённое обучение']),
 track('robotics','Robotics / Embodied AI',{'robotics':3,'control':3,'slam':3,'ros':2,'rl':2,'cpp':2,'pytorch':2},['robotics','робототехника','embodied ai','роботы']),
 track('apple','Apple MLX / MPS',{'mlx':3,'metal':3,'pytorch':2,'profiling':2,'quantization':2,'inference':2},['apple','mlx','mps','metal']),
 ]}

RESOURCES={r['id']:r for r in [
 {'id':'python_tutorial','title':'Python — официальный tutorial для программистов','url':'https://docs.python.org/3/tutorial/','kind':'tutorial','prerequisites':[],'topics':['python']},
 {'id':'pytorch_basics','title':'PyTorch — Learn the Basics / Quickstart','url':'https://docs.pytorch.org/tutorials/beginner/basics/quickstart_tutorial.html','kind':'tutorial','prerequisites':['python'],'topics':['pytorch']},
 {'id':'torchao','title':'PyTorch torchao — квантизация и оптимизация','url':'https://docs.pytorch.org/ao/stable/index.html','kind':'documentation','prerequisites':['pytorch'],'topics':['quantization']},
 {'id':'dl_book','title':'Deep Learning — Goodfellow, Bengio, Courville','url':'https://www.deeplearningbook.org/','kind':'book','prerequisites':[],'topics':['linear_algebra','calculus','probability','deep_learning']},
 {'id':'cs336','title':'Stanford CS336 — Language Modeling from Scratch','url':'https://cs336.stanford.edu/','kind':'course_and_exercises','prerequisites':['python','pytorch','linear_algebra','calculus','probability','deep_learning'],'topics':['pretraining','alignment','sft','rl','data_curation','evaluation','transformers','tokenization','optimization','triton','profiling','distributed','inference']},
 {'id':'mit_lab1','title':'MIT 6.S184 (2026) — Lab 1: ODE / SDE','url':'https://diffusion.csail.mit.edu/2026/index.html','kind':'lab','prerequisites':['python','pytorch','linear_algebra','calculus','probability'],'topics':['ode_sde']},
 {'id':'mit_lab2','title':'MIT 6.S184 (2026) — Lab 2: Flow / Score Matching','url':'https://diffusion.csail.mit.edu/2026/index.html','kind':'lab','prerequisites':['python','pytorch','ode_sde','deep_learning'],'topics':['flow_matching','diffusion']},
 {'id':'mit_lab3','title':'MIT 6.S184 (2026) — Lab 3: DiT / VAE','url':'https://diffusion.csail.mit.edu/2026/index.html','kind':'lab','prerequisites':['diffusion','transformers'],'topics':['dit_vae']},
 {'id':'flow_paper','title':'Flow Matching for Generative Modeling','url':'https://arxiv.org/abs/2210.02747','kind':'paper','prerequisites':['ode_sde','deep_learning'],'topics':['flow_matching']},
 {'id':'ddpm','title':'Denoising Diffusion Probabilistic Models','url':'https://arxiv.org/abs/2006.11239','kind':'paper','prerequisites':['probability','deep_learning','ode_sde'],'topics':['diffusion']},
 {'id':'fsdp2','title':'PyTorch — Getting Started with FSDP2','url':'https://docs.pytorch.org/tutorials/intermediate/FSDP_tutorial.html','kind':'tutorial','prerequisites':['python','pytorch','distributed'],'topics':['fsdp']},
 {'id':'cuda_guide','title':'NVIDIA — CUDA Programming Guide','url':'https://docs.nvidia.com/cuda/cuda-programming-guide/index.html','kind':'documentation','prerequisites':['cpp'],'topics':['cuda','profiling']},
 {'id':'mps_docs','title':'PyTorch — MPS backend on macOS','url':'https://docs.pytorch.org/docs/stable/notes/mps.html','kind':'documentation','prerequisites':['pytorch'],'topics':['metal']},
 {'id':'mlx_docs','title':'MLX — официальная документация Apple ML Explore','url':'https://ml-explore.github.io/mlx/build/html/index.html','kind':'documentation','prerequisites':['python','deep_learning'],'topics':['mlx']},
 {'id':'robotics_book','title':'Modern Robotics — Lynch, Park','url':'https://modernrobotics.northwestern.edu/nu-gm-book-resource/','kind':'book_and_exercises','prerequisites':['linear_algebra','calculus'],'topics':['robotics','control']},
 ]}
for resource in RESOURCES.values():resource.update(checked_at=CHECKED,verification='primary_source_reviewed',access='public',cost_note='Ресурс доступен по ссылке; вычислительные ресурсы для лабораторных могут потребовать расходов.')

ACTION_LABELS={'learn':'Изучить основы','practice':'Закрепить практикой','validate':'Проверить и подтвердить уровень','document_in_cv':'Добавить подтверждённый опыт в CV','publish_project':'Описать и опубликовать результат'}
