"""Preserve explicit source locations; never infer a city from a job title or JD."""
import re


def normalize_locations(row):
    values=row.get('locations',[])
    if not isinstance(values,list) or len(values)>100:raise ValueError('Locations должен содержать до 100 мест работы.')
    locations=[]
    for value in values:
        if not isinstance(value,str) or len(value)>500:raise ValueError('Некорректная локация вакансии.')
        value=' '.join(value.split())
        if value and value.casefold() not in {v.casefold() for v in locations}:locations.append(value)
    for key in ('location','city'):
        value=row.get(key,'')
        if value is None:continue
        if not isinstance(value,str) or len(value)>1000:raise ValueError('Некорректное поле локации.')
        value=' '.join(value.split())
        if value and not locations:locations.append(value)
    formats=list(row.get('work_formats',[]))
    if any(x not in ('remote','hybrid','onsite') for x in formats):raise ValueError('Неизвестный формат работы.')
    explicit=' '.join(locations+[str(row.get('work_format',''))])
    for key,pattern in [('remote',r'\bremote\b|удал[её]н'),('hybrid',r'\bhybrid\b|гибрид'),('onsite',r'\bon[ -]?site\b|\bофис\b')]:
        if re.search(pattern,explicit,re.I) and key not in formats:formats.append(key)
    return {**row,'locations':locations,'work_formats':formats,
            'locations_status':'partial' if row.get('locations_status')=='partial' and locations else 'provided' if locations else 'missing'}
