import aiosqlite
from loguru import logger
import os
from dataclasses import dataclass


@dataclass
class BotStats:
    users_count: int
    sent_videos_total: int
    sent_videos_user: int
    cached_files: int
    downloaded: int


async def prepare_db():
    async with aiosqlite.connect("db.sqlite3") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE NOT NULL,
            uses_count INTEGER DEFAULT 0,
            duration INTEGER,
            thumbnail TEXT,
            title TEXT,
            uploader TEXT,
            downloaded BOOLEAN DEFAULT 0
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            sent_videos_count INTEGER
        )""")
        await db.commit()


async def add_use(video_id: str, user_id: int):
    try:
        async with aiosqlite.connect("db.sqlite3") as db:
            await db.execute(
                "INSERT OR IGNORE INTO files (video_id) VALUES (?)", (video_id,)
            )

            await db.execute(
                "UPDATE files SET uses_count = uses_count + 1 WHERE video_id = ?",
                (video_id,),
            )

            await db.execute(
                """
                INSERT INTO users (id, sent_videos_count) 
                VALUES (?, 1) 
                ON CONFLICT(id) DO UPDATE SET 
                    sent_videos_count = sent_videos_count + 1
            """,
                (user_id,),
            )

            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка в add_use: {str(e)}")
        await db.rollback()


async def add_file(
    video_id: str, title: str, uploader: str, thumbnail: str, duration: int
):
    async with aiosqlite.connect("db.sqlite3") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """
            INSERT INTO files (video_id, title, uploader, thumbnail, duration) 
            VALUES (?, ?, ?, ?, ?) 
            ON CONFLICT(video_id) DO UPDATE SET 
                title = excluded.title,
                uploader = excluded.uploader,
                thumbnail = excluded.thumbnail,
                duration = excluded.duration
        """,
            (video_id, title, uploader, thumbnail, duration),
        )
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect("db.sqlite3") as db:
        cursor = await db.cursor()
        await cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return row
        else:
            await cursor.execute(
                "INSERT INTO users (id, sent_videos_count) VALUES (?, 0)", (user_id,)
            )
            await db.commit()
            return await get_user(user_id)


async def get_file(video_id: str):
    async with aiosqlite.connect("db.sqlite3") as db:
        cursor = await db.cursor()
        await cursor.execute("SELECT * FROM files WHERE video_id = ?", (video_id,))
        row = await cursor.fetchone()
        logger.info(row)
        thumbnail = row[4]
        if thumbnail is not None:
            if not (
                thumbnail.startswith("https://" or thumbnail.startswith("http://"))
            ):
                if thumbnail.startswith("//"):
                    thumbnail = f"https:{thumbnail}"
                else:
                    thumbnail = f"https://{thumbnail}"
        if row:
            return {
                "id": row[0],
                "video_id": row[1],
                "uses_count": row[2],
                "duration": row[3],
                "thumbnail": thumbnail,
                "title": row[5],
                "uploader": row[6],
                "downloaded": row[7],
            }
        else:
            return None


async def set_downloaded(video_id: str, value: int = 1):
    async with aiosqlite.connect("db.sqlite3") as db:
        await db.execute(
            "UPDATE files SET downloaded = 1 WHERE video_id = ?", (video_id,)
        )
        await db.commit()


async def get_user_ids() -> list[int]:
    async with aiosqlite.connect("db.sqlite3") as conn:
        async with conn.execute("SELECT id FROM users") as cursor:
            rows = await cursor.fetchall()
            user_ids = [row[0] for row in rows]
    return user_ids


async def get_stats(user_id: int) -> BotStats:
    async with aiosqlite.connect("db.sqlite3") as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            users_count = (await cursor.fetchone())[0]
        async with conn.execute("SELECT SUM(sent_videos_count) FROM users") as cursor:
            sent_videos_total = (await cursor.fetchone())[0]
        async with conn.execute(
            "SELECT sent_videos_count FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            sent_videos_user = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM files") as cursor:
            cached_files = (await cursor.fetchone())[0]
        downloaded = len(os.listdir("audio")) - 1

    return BotStats(
        users_count=users_count,
        sent_videos_total=sent_videos_total,
        sent_videos_user=sent_videos_user,
        cached_files=cached_files,
        downloaded=downloaded,
    )
