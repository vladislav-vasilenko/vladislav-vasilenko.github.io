"""Monthly ceiling for every OpenAI embedding request, whichever route started it."""
import json
from datetime import datetime, timezone
from .archive_store import canonical, now_iso

KEY = 'embedding-spend'
USD_PER_TOKEN = 0.02 / 1000000
DEFAULT_CEILING = 5.0
MAX_CEILING = 50.0
HISTORY = 20


def month(now=None):
    return (now or datetime.now(timezone.utc)).strftime('%Y-%m')


def read(archive):
    with archive.connect() as db:
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
    state = json.loads(row[0]) if row else {}
    state.setdefault('ceiling_usd', DEFAULT_CEILING); state.setdefault('history', [])
    if state.get('month') != month(): state.update(month=month(), tokens=0)
    return state


def save(archive, change):
    with archive.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM archive_meta WHERE key=?', (KEY,)).fetchone()
        state = json.loads(row[0]) if row else {}
        state.setdefault('ceiling_usd', DEFAULT_CEILING); state.setdefault('history', [])
        if state.get('month') != month(): state.update(month=month(), tokens=0)
        change(state)
        db.execute('INSERT OR REPLACE INTO archive_meta VALUES(?,?)', (KEY, canonical(state)))
    return state


def spent_usd(state):
    return round(state.get('tokens', 0) * USD_PER_TOKEN, 4)


def check(archive, texts):
    # Deliberately high estimate, checked before money is spent.
    estimate = sum(len(text) for text in texts) // 2
    state = read(archive)
    if (state['tokens'] + estimate) * USD_PER_TOKEN > state['ceiling_usd']:
        raise ValueError(f"Достигнут общий месячный потолок embeddings: ${state['ceiling_usd']:.2f}. Запрос к OpenAI не отправлен. Потолок можно изменить во вкладке рейтинга.")


def record(archive, tokens):
    def change(state): state['tokens'] = state.get('tokens', 0) + tokens
    save(archive, change)


def log(archive, action, **values):
    def change(state): state['history'] = [{'at': now_iso(), 'action': action, **values}, *state['history']][:HISTORY]
    save(archive, change)


def set_ceiling(archive, value, confirmed):
    if confirmed is not True: raise ValueError('Подтвердите новый потолок расходов.')
    if type(value) not in (int, float) or not 0.01 <= value <= MAX_CEILING: raise ValueError(f'Потолок должен быть от $0.01 до ${MAX_CEILING:.0f} в месяц.')
    value = round(float(value), 2)
    def change(state): state['ceiling_usd'] = value
    save(archive, change); log(archive, 'ceiling', ceiling_usd=value)
