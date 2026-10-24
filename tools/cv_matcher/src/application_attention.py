"""One read-only queue for Today and scheduled owner reminders."""
import json
from datetime import datetime, timezone
from .application_workflow import CRM_STAGES, WORK_STATUSES

REVIEW_ACTIONS = {
    'needs_approval': 'Проверить ответы и разрешить действие',
    'fields_filled': 'Проверить перенесённые поля на сайте компании',
    'uncertain': 'Сверить результат с сайтом перед повтором',
    'needs_input': 'Уточнить данные и продолжить подготовку',
}

def items(store, now=None):
    now = now or datetime.now(timezone.utc)
    with store.connect() as db:
        rows = db.execute("""SELECT a.id,a.status,a.context,w.draft,w.state,w.revision,
          c.stage,c.work_status,c.next_action,c.follow_up_at FROM applications a
          LEFT JOIN application_workflow w ON w.app_id=a.id
          LEFT JOIN application_crm c ON c.app_id=a.id ORDER BY a.created DESC""").fetchall()
    result = []
    for row in rows:
        if row['status'] == 'superseded' or store.case_id(row['id']) != row['id']:
            continue
        c = json.loads(row['context']); state = row['state'] or 'draft'
        stage = row['stage'] or 'preparing'; work = row['work_status'] or 'preparing'
        closed = row['status'] in ('completed', 'rejected', 'withdrawn') or stage in ('offer', 'rejected') or work == 'done'
        sent = row['status'] in ('submitted', 'viewed', 'invited') or stage != 'preparing'
        review = not closed and not sent and state in REVIEW_ACTIONS
        due = False; deferred = False
        if row['follow_up_at']:
            try:
                stamp = datetime.fromisoformat(row['follow_up_at'].replace('Z', '+00:00'))
                if stamp.tzinfo:
                    due = stamp <= now; deferred = stamp > now
            except ValueError:
                pass
        if review: next_step = REVIEW_ACTIONS[state]
        elif closed: next_step = 'Завершено'
        elif state in ('approved', 'sending', 'fill_approved', 'filling'): next_step = 'Дождаться результата в Chrome'
        elif sent: next_step = row['next_action'] or 'Следить за ответом'
        elif row['draft']: next_step = 'Подготовить форму HH' if c['channel'] == 'hh' else 'Открыть форму компании и проверить ответы'
        else: next_step = row['next_action'] or 'Составить сопроводительное письмо'
        if due and not closed and not review: next_step = row['next_action'] or WORK_STATUSES.get(work, work)
        preparation = not closed and not sent and bool(row['draft']) and state == 'draft'
        reminder = not closed and not deferred and (review or preparation or due)
        result.append({'resume_id': c.get('resume_id'), 'resume_title': c.get('resume_title', ''),
            'state': state, 'status': row['status'], 'stage_key': stage,
            'work_status': WORK_STATUSES.get(work, work), 'follow_up_at': row['follow_up_at'],
            'id': row['id'], 'title': c['vacancy']['title'], 'company': c['vacancy'].get('company', ''),
            'stage': CRM_STAGES.get(stage, stage), 'next': next_step, 'needs_attention': review or due and not closed,
            'reminder_due': reminder, 'closed': closed, 'channel': c['channel']})
    return sorted(result, key=lambda item: (not item['needs_attention'], not item['reminder_due']))
