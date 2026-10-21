"""Compatibility labels for career notifications and Telegram presentation."""
import re
TITLES={'queued':'Подготовка','submitted':'Отправлен','viewed':'Просмотрен','invited':'Приглашение','rejected':'Отказ','withdrawn':'Отозван','unknown':'Не определён','needs_approval':'Нужно разрешение','uncertain':'Нужна сверка с HH','needs_input':'Нужны ваши данные','approved':'Разрешён','draft':'Черновик','sending':'Отправляется'}
CHROME_HELP='HH подключается один раз в Google Chrome.\n1. Chrome → chrome://extensions → обновить ML Research Vacancy Search до 0.11.19.\n2. Значок расширения → 5. Отклик → «Подключить HH один раз» (или Параметры расширения).\n3. Подключите локальный сервис кодом из .cache/resume_import/token.txt, затем разрешите HH. Расширение само откроет служебную вкладку.\n4. Если HH просит вход или CAPTCHA, выполните их вручную в этой вкладке. Оставьте Chrome и компьютер включёнными.\n/status покажет связь. Telethon управляет Giga; HH читает расширение.'

def browser_note(note):
 if not isinstance(note,str):return 'Не удалось завершить задачу HH. Откройте отклик для проверки.'
 if re.search(r'Frame.*showing error page',note,re.I):return 'Не удалось загрузить страницу HH в служебной вкладке Chrome. Проверьте доступ к HH и обновите эту вкладку; если отправка уже запускалась, сначала проверьте её результат.'
 if re.search(r'Cannot read propert|reading [\'"]state|undefined|null',note,re.I):return 'Не удалось прочитать форму HH. Откройте форму нужной вакансии в служебной вкладке и повторите подготовку. Если отправка уже запускалась, сначала проверьте её результат на HH.'
 return note
