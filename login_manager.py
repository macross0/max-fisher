import asyncio
import os
import pymax
from pymax.auth.providers import SmsCodeProvider
from config import SESSIONS_DIR


class SMSWrapperProvider(SmsCodeProvider):
    """Bridges pymax's code_provider API to a plain async callable."""

    def __init__(self, func):
        self.func = func

    async def get_code(self, phone: str) -> str:
        return await self.func(phone)


class LoginManager:
    def __init__(self):
        self.active_logins: dict[str, asyncio.Queue] = {}
        self.tasks: set[asyncio.Task] = set()
        os.makedirs(SESSIONS_DIR, exist_ok=True)

    # ---- task bookkeeping ------------------------------------------------
    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)
        return t

    # ---- code provider ---------------------------------------------------
    async def get_sms_code(self, phone: str) -> str:
        print(f"[PyMax] Клиент {phone} ожидает SMS-код...")
        queue = self.active_logins[phone]
        code = await queue.get()
        return str(code)

    # ---- the actual login flow ------------------------------------------
    async def register_and_start(self, phone: str) -> None:
        self.active_logins.setdefault(phone, asyncio.Queue())

        client = pymax.Client(
            phone=phone,
            session_name=os.path.join(SESSIONS_DIR, f"session_{phone}.db"),
            sms_code_provider=SMSWrapperProvider(self.get_sms_code),
        )
        try:
            await client.start()
            print(f"🎉 {phone}: {client.me.first_name}")
            # TODO: store `client` in a global pool if you want to reuse it
        except Exception as e:
            print(f"[PyMax] Ошибка авторизации {phone}: {e!r}")
        finally:
            self.active_logins.pop(phone, None)

    # ---- external API hook ----------------------------------------------
    async def receive_external_sms(self, phone: str, sms_code: str) -> None:
        q = self.active_logins.get(phone)
        if q is None:
            print(f"[API] Номер {phone} не в процессе авторизации.")
            return
        print(f"[API] Код {sms_code} для {phone} → в очередь.")
        await q.put(sms_code)

    # ---- convenience wrappers -------------------------------------------
    def is_login_in_progress(self, phone: str) -> bool:
        return phone in self.active_logins

    def start_login(self, phone: str) -> None:
        """Create the queue synchronously, then spawn the login task."""
        self.active_logins[phone] = asyncio.Queue()
        self._spawn(self.register_and_start(phone))