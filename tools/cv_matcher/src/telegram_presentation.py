"""Small safe visual hierarchy; never interpret Markdown/HTML from CV or employers."""
from html import escape
import re

def format_text(text):
    lines=str(text).split('\n');out=[]
    for i,line in enumerate(lines):
        safe=escape(line,quote=False)
        if i==0 and 0<len(line)<=180:out.append('<b>'+safe+'</b>')
        elif re.match(r'^(CV|Следующее действие|Следующий шаг|Источники|API|Письмо #\d+|Найдено в прочитанной выдаче|Запланировано полных описаний|Прочитано полных описаний|Взято из свежего кэша|Не удалось прочитать|Обновлён рейтинг):',line):
            label,tail=safe.split(':',1);out.append('<b>'+label+':</b>'+tail)
        else:out.append(safe)
    return '\n'.join(out)

def keyboard_rows(rows):
    return [[{'text':label,**({'url':data} if data.startswith(('https://','http://127.0.0.1:8788/')) else {'callback_data':data})} for label,data in row] for row in rows]
