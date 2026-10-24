"""Visible LinkedIn card signals; not application outcomes or fit scores."""
def validate(value):
    flags=('viewed','early_applicant','promoted','actively_reviewing','applicants_lower_bound')
    labels=('school_alumni_label','posted_label','applicants_label','salary_label','work_format_label','employment_label')
    counts=('school_alumni_count','applicants_count')
    if not isinstance(value,dict) or set(value)-set(flags)-set(labels)-set(counts):
        raise ValueError('Неизвестные отметки LinkedIn.')
    if any(type(value[k]) is not bool for k in flags if k in value):raise ValueError('Некорректная отметка LinkedIn.')
    for key in counts:
        if key in value and (type(value[key]) is not int or not 0<=value[key]<=10000000):raise ValueError('Некорректное число в отметке LinkedIn.')
    for key in labels:
        if key in value and (not isinstance(value[key],str) or len(value[key])>200):raise ValueError('Некорректная подпись LinkedIn.')
    return dict(value)
