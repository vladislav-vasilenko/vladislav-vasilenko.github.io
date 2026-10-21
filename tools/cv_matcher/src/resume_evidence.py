"""Local, reviewed supporting documents. Never creates a resume or executes formulas."""
import base64
import binascii
import hashlib
import io
from datetime import date,datetime,time
from pathlib import Path
from .resume_files import MAX_FILE,extract_resume,safe_zip

def spreadsheet(data,suffix):
    from python_calamine import CalamineWorkbook
    if suffix=='.xlsx':safe_zip(data).close()
    lines=[];characters=0
    try:
        workbook=CalamineWorkbook.from_filelike(io.BytesIO(data))
        try:
            if len(workbook.sheet_names)>20:raise ValueError('В таблице больше 20 листов. Сохраните нужный фрагмент.')
            for name in workbook.sheet_names:
                sheet=workbook.get_sheet_by_name(name);lines.append('Лист: '+name);offset=sheet.start[0] if sheet.start else 0
                for i,row in enumerate(sheet.iter_rows(),1):
                    if i>5000 or len(row)>100:raise ValueError('Таблица слишком велика: максимум 5000 строк и 100 столбцов на лист.')
                    def cell(value):return value.isoformat() if isinstance(value,(date,datetime,time)) else str(value)
                    if not any(str(v).strip() for v in row):continue
                    line='Строка '+str(offset+i)+': '+' | '.join(cell(v) for v in row);characters+=len(line)
                    if characters>60000:raise ValueError('Извлечено больше 60 000 символов. Выберите нужные листы/строки.')
                    lines.append(line)
        finally:workbook.close()
    except ValueError:raise
    except Exception:raise ValueError('Не удалось прочитать Excel. Проверьте файл и отсутствие пароля; можно сохранить нужные строки в TXT.') from None
    return '\n'.join(lines)

def extract(data):
    name=data.get('filename');encoded=data.get('content_base64')
    if not isinstance(name,str) or len(name)>300 or not isinstance(encoded,str) or len(encoded)>MAX_FILE*4//3+4:raise ValueError('Нужен файл до 12 МБ.')
    name=Path(name.replace('\\','/')).name;suffix=Path(name).suffix.lower()
    try:content=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise ValueError('Файл повреждён при передаче.') from None
    if not content or len(content)>MAX_FILE:raise ValueError('Нужен непустой файл до 12 МБ.')
    if suffix in ('.xls','.xlsx'):
        text=spreadsheet(content,suffix);method='calamine';warnings=['Даты с форматом даты показаны в ISO. Числа без формата оставлены числами; формулы не вычисляются, используются сохранённые значения. Проверьте листы и даты по оригиналу.']
    else:
        result=extract_resume(content,name,min_text=15);text=result['text'];method=result['extraction_method'];warnings=result['warnings']
    from .resume_portfolio import professional_text
    text=professional_text(text.strip())
    if not 15<=len(text)<=60000:raise ValueError('Для одного подтверждения нужен текст от 15 до 60 000 символов.')
    return {'candidate':{'label':professional_text(name),'text':text,'file_hash':hashlib.sha256(content).hexdigest(),'extraction_method':method,'warnings':warnings},'api_requests':0}
