"""One renewable SQLite lease lets HTTP and Telegram share the same scheduler."""
import asyncio,secrets,time,logging

async def scheduled_tick(service,now=None):
    holder=secrets.token_hex(16)
    with service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute("SELECT expires FROM career_leases WHERE name='scheduler'").fetchone()
        if old and old[0]>time.time():return False
        db.execute("INSERT OR REPLACE INTO career_leases VALUES('scheduler',?,?)",(holder,time.time()+90))
    async def renew():
        while True:
            await asyncio.sleep(15)
            with service.store.connect() as db:db.execute("UPDATE career_leases SET expires=? WHERE name='scheduler' AND holder=?",(time.time()+90,holder))
    renewal=asyncio.create_task(renew())
    try:
        from .career_application import CareerApplication
        await CareerApplication.tick(service,now)
        return True
    finally:
        renewal.cancel()
        try:await renewal
        except asyncio.CancelledError:pass
        with service.store.connect() as db:db.execute("DELETE FROM career_leases WHERE name='scheduler' AND holder=?",(holder,))

async def run(store_factory,period=30):
    from .career_application import CareerApplication
    await asyncio.sleep(period)
    while True:
        try:await scheduled_tick(CareerApplication(store_factory()))
        except Exception:logging.getLogger(__name__).exception('Career scheduler tick failed; persisted state retained')
        await asyncio.sleep(period)
