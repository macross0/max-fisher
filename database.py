import aiosqlite
from config import DB_FILE


async def init_db() -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY,
                client_id TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY,
                phone TEXT NOT NULL,
                logged_in_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_file TEXT NOT NULL
            )
        ''')
        await db.commit()


async def create_client(client_id: str, phone: str) -> None:
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO urls (client_id, phone) VALUES (?, ?)",
            (client_id, phone),
        )
        await db.commit()


async def get_client_by_id(client_id: str):
    """Returns (id, phone) or None."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT id, phone FROM urls WHERE client_id = ?",
            (client_id,),
        )
        return await cursor.fetchone()