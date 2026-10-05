import secrets
import aiohttp_jinja2
import jinja2
from aiohttp import web

from database import create_client, get_client_by_id
from login_manager import LoginManager


def new_client_id() -> str:
    return secrets.token_urlsafe(8)


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

@aiohttp_jinja2.template("template.html")
async def page_client(request: web.Request):
    client_id = request.match_info["client_id"]
    row = await get_client_by_id(client_id)
    if not row:
        raise web.HTTPNotFound()
    return {"phone": row[1]}


async def process_code_send(request: web.Request) -> web.Response:
    manager: LoginManager = request.app["manager"]

    client_id = request.match_info["client_id"]
    row = await get_client_by_id(client_id)
    if not row:
        # intentionally vague for security
        return web.json_response({"status": "ok", "received": True})

    phone = f"+{row[1]}"

    if manager.is_login_in_progress(phone):
        return web.json_response({"status": "already_in_progress"}, status=409)

    manager.start_login(phone)
    return web.json_response({"status": "ok"})


async def process_received_code(request: web.Request) -> web.Response:
    manager: LoginManager = request.app["manager"]

    client_id = request.match_info["client_id"]
    row = await get_client_by_id(client_id)
    if not row:
        return web.json_response({"status": "ok", "received": True})

    data = await request.json()
    code = data.get("code")
    await manager.receive_external_sms(f"+{row[1]}", code)

    return web.json_response({"status": "ok"})


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------
def create_app(manager: LoginManager) -> web.Application:
    app = web.Application()
    app["manager"] = manager

    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("templates"))

    app.router.add_get("/{client_id}", page_client)
    app.router.add_post("/{client_id}/send-code", process_code_send)
    app.router.add_post("/{client_id}/code", process_received_code)

    return app