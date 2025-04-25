import io
import os
import time
import asyncio
from typing import Awaitable, Callable
from urllib.parse import unquote
from hashlib import sha256
import random
import re
import unicodedata

import aiohttp
import yt_dlp
import aiosqlite
from PIL import Image

from aiogram import Bot, Dispatcher, types, F
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineQueryResultArticle,
    Message,
    InlineQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    URLInputFile,
    ChosenInlineResult,
    InputTextMessageContent,
    LinkPreviewOptions,
    InputMediaAudio
)

from loguru import logger
from dotenv import load_dotenv

from text import STATS_TEXT
import re
from const import REMIX_KEYWORDS

load_dotenv()


BOT_TOKEN = os.getenv('BOT_TOKEN')
SEARCH_LIMIT = int(os.getenv('SEARCH_LIMIT'))
LENGTH_LIMIT = int(os.getenv('LENGTH_LIMIT')) # in minutes
CACHE_SIZE_LIMIT = int(os.getenv('CACHE_SIZE_LIMIT')) # in seconds
ADMIN_ID = int(os.getenv('ADMIN_ID'))
# LOADING_GIF_URL = os.getenv('LOADING_GIF_URL')
CHAT_ID = int(os.getenv('CHAT_ID'))


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
queued = set()


def safe_filename(title: str, max_length=64) -> str:
    safe = re.sub(r'[\\/*?:"<>|\x00-\x1F]', '', title)
    return safe.strip()


async def search(query: str) -> list:
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'force_generic_extractor': True,
        'noplaylist': True,
        'ignoreerrors': True,
    }

    search_results = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f'ytsearch{SEARCH_LIMIT * 2}:{query}'
        result = ydl.extract_info(search_query, download=False)

        if not result or 'entries' not in result:
            return []

        for entry in result['entries']:
            if entry and len(search_results) < SEARCH_LIMIT:
                thumbnails = entry.get('thumbnails', [])
                thumbnail = next(
                    (t['url'] for t in reversed(thumbnails) if t.get('url')),
                    'https://i.ytimg.com/vi/{}/hqdefault.jpg'.format(entry.get('id', ''))
                )

                if not (thumbnail.startswith('https://' or thumbnail.startswith('http://'))):
                    if thumbnail.startswith('//'):
                        thumbnail = f'https:{thumbnail}'
                    else:
                        thumbnail = f'https://{thumbnail}'

                video_data = {
                    'title': entry.get('title', 'Без названия'),
                    'duration': (entry.get('duration', 0)) or 0,
                    'thumbnail': thumbnail,
                    'uploader': entry.get('uploader', 'Неизвестный автор'),
                    'url': entry.get('url', ''),
                    'view_count': entry.get('view_count', 0),
                    'id': entry.get('id', '')
                }

                uploader = video_data['uploader']
                title = video_data['title']

                for kw in REMIX_KEYWORDS:
                    if kw in title.lower():
                        break
                else:
                    for sep in (' — ', ' - '):
                        # maybe_uploader = title.split(sep, 1)[1]
                        # if ', ' in maybe_uploader or uploader.lower() in maybe_uploader.lower():
                        #     uploader = title.split(sep, 1)[0]
                        #     title = title.split(sep, 1)[1]
                        if sep not in title:
                            continue
                        if uploader in title.split(sep, 1)[1]:
                            continue
                        uploader = title.split(sep, 1)[0]
                        title = title.split(sep, 1)[1]

                # chars_to_strip = len(uploader) + 3
                # if title.lower().startswith(f'{uploader.lower()} - '):
                #     title = title[chars_to_strip:]
                # elif title.lower().endswith(f'{uploader.lower()} - '):
                #     title = title[:len(title) - chars_to_strip]

                title = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()
                title = re.sub(r',\s*\d{4}\s*$', '', title).strip()

                if uploader.endswith('- Topic'):
                    uploader = uploader.removesuffix(' - Topic')

                video_data['title'] = title
                video_data['uploader'] = uploader

                if video_data['duration'] > LENGTH_LIMIT:
                    continue
                await add_file(video_data['id'], video_data['title'], video_data['uploader'], video_data['thumbnail'], video_data['duration'])
                search_results.append(video_data)

        return search_results
    

def default_progress_callback(current, total, speed):
    logger.info(f'Downloading {current} of {total} bytes ({speed} bytes/sec)')

def default_complete_callback(filename):
    logger.info(f'Download complete: {filename}')

def default_error_callback(error, url):
    logger.info(f'Error: {repr(error)} for {url}')

async def download(
        url: str,
        progress_callback: Callable = default_complete_callback, 
        complete_callback: Callable = default_complete_callback,
        error_callback: Callable = default_error_callback
    ):
    output_dir = 'audio'
    os.makedirs(output_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            },
            {
                'key': 'EmbedThumbnail',
                'already_have_thumbnail': False
            },
            {
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            }
        ],
        'postprocessor_args': {
            'embedthumbnail+ffmpeg_o': [
                '-c:v',
                    'png',
                '-vf',
                    "crop='if(gt(ih,iw),iw,ih)':'if(gt(iw,ih),ih,iw)'"
            ]
        },
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'embedthumbnail': True,
        'writethumbnail': True,
        'keepvideo': False,
        'quiet': True,
        'noprogress': True,
        'no_warnings': True,
        'progress_hooks': [],
        'restrictfilenames': True,
        'clean_infojson': True,
    }

    last_progress_time = 0
    final_filename = None

    def progress_hook(d):
        nonlocal last_progress_time, final_filename
        if d['status'] == 'downloading':
            current_time = time.time()
            if current_time - last_progress_time >= 1:
                last_progress_time = current_time
                if progress_callback:
                    current = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0)
                    progress_callback(current, total, speed)
                    
        elif d['status'] == 'finished':
            video_id = d['info_dict'].get('id', 'unknown')
            final_filename = os.path.join(output_dir, f"{video_id}.mp3")
    ydl_opts['progress_hooks'].append(progress_hook)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict: dict = ydl.extract_info(url, download=False)
            video_id = info_dict.get('id', 'unknown')
            predicted_filename = os.path.join(output_dir, f"{video_id}.mp3")
            
            if os.path.exists(predicted_filename):
                logger.info(f"Файл уже существует: {predicted_filename}")
                if complete_callback:
                    complete_callback(predicted_filename)
                return predicted_filename
            
            ydl.download([url])
            
            if complete_callback and final_filename:
                complete_callback(final_filename)

            async with aiosqlite.connect('db.sqlite3') as db:
                await db.execute('UPDATE files SET downloaded = 1 WHERE video_id = ?', (video_id,))
            return info_dict

    except Exception as e:
        if error_callback:
            error_callback(e, url)
        else:
            logger.error(f"Ошибка при обработке {url}: {str(e)}")
        return None
    

async def prepare_db():
    async with aiosqlite.connect('db.sqlite3') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE NOT NULL,
            uses_count INTEGER DEFAULT 0,
            duration INTEGER,
            thumbnail TEXT,
            title TEXT,
            uploader TEXT,
            downloaded BOOLEAN DEFAULT 0
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            sent_videos_count INTEGER
        )''')
        await db.commit()


async def add_use(video_id: str, user_id: int):
    async with aiosqlite.connect('db.sqlite3') as db:
        cursor = await db.cursor()
        await cursor.execute(f'SELECT * FROM files WHERE video_id = ?', (video_id,))
        row = await cursor.fetchone()
        if row:
            await cursor.execute(f'UPDATE files SET uses_count = uses_count + 1 WHERE video_id = ?', (video_id,))
        else:
            await cursor.execute(f'INSERT INTO files (video_id, uses_count) VALUES (?, 1)', (video_id,))
        await cursor.execute(f'SELECT * FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            await cursor.execute(f'UPDATE users SET sent_videos_count = sent_videos_count + 1 WHERE id = ?', (user_id,))
        else:
            await cursor.execute(f'INSERT INTO users (id, sent_videos_count) VALUES (?, 1)', (user_id,))
        await db.commit()


async def add_file(video_id: str, title: str, uploader: str, thumbnail: str, duration: int):
    async with aiosqlite.connect('db.sqlite3') as db:
        cursor = await db.cursor()
        await cursor.execute('''
            INSERT INTO files (video_id, title, uploader, thumbnail, duration) 
            VALUES (?, ?, ?, ?, ?) 
            ON CONFLICT(video_id) DO UPDATE SET 
                title = excluded.title,
                uploader = excluded.uploader,
                thumbnail = excluded.thumbnail,
                duration = excluded.duration
        ''', (video_id, title, uploader, thumbnail, duration))
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect('db.sqlite3') as db:
        cursor = await db.cursor()
        await cursor.execute(f'SELECT * FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return row
        else:
            await cursor.execute(f'INSERT INTO users (id, sent_videos_count) VALUES (?, 0)', (user_id,))
            await db.commit()
            return await get_user(user_id)
        

async def get_file(video_id: str):
    async with aiosqlite.connect('db.sqlite3') as db:
        cursor = await db.cursor()
        await cursor.execute(f'SELECT * FROM files WHERE video_id = ?', (video_id,))
        row = await cursor.fetchone()
        logger.info(row)
        thumbnail = row[4]
        if thumbnail is not None:
            if not (thumbnail.startswith('https://' or thumbnail.startswith('http://'))):
                if thumbnail.startswith('//'):
                    thumbnail = f'https:{thumbnail}'
                else:
                    thumbnail = f'https://{thumbnail}'
        if row:
            return {
                'id': row[0],
                'video_id': row[1],
                'uses_count': row[2],
                'duration': row[3],
                'thumbnail': thumbnail,
                'title': row[5],
                'uploader': row[6],
                'downloaded': row[7]
            }
        else:
            return None


async def download_and_crop_thumbnail(url: str | None, video_id: str) -> str | None:
    if not url:
        return None

    thumb_dir = 'thumbnails'
    os.makedirs(thumb_dir, exist_ok=True)
    filename = os.path.join(thumb_dir, f'{video_id}.jpg')

    if os.path.exists(filename):
        return filename

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None

                image_data = await response.read()
                image = Image.open(io.BytesIO(image_data))

                width, height = image.size
                size = min(width, height)
                left = (width - size) / 2
                top = (height - size) / 2
                right = (width + size) / 2
                bottom = (height + size) / 2

                cropped = image.crop((left, top, right, bottom))
                cropped.save(filename, 'JPEG', quality=85)

                return filename
    except Exception as e:
        logger.error(f"Thumbnail error: {str(e)}")
        return None


@dp.message(CommandStart())
async def start(message: Message):
    me = await bot.get_me()
    user = await get_user(message.from_user.id)
    await message.answer(
        f'Hi! I will help you search, send and download music from YouTube! '
        f'Just type <code>@{me.username} [query]</code> and wait a few seconds.',
        parse_mode='html'
    )


@dp.inline_query()
async def inline_query_handler(query: InlineQuery, *args, **kwargs):
    user = await get_user(query.from_user.id)
    results = await search(query.query)
    
    if not results:
        return await query.answer(
            results=[InlineQueryResultArticle(
                id=str(random.randint(10000, 99999)),
                title='No results',
                input_message_content=InputTextMessageContent(message_text='No results found :('),
            )],
            cache_time=3600,
            is_personal=False
        )
    
    inline_results = []
    for result in results:
        logger.info(result['id'])
        await add_file(result['id'], result['title'], result['uploader'], result['thumbnail'], result['duration'])
        inline_results.append(InlineQueryResultArticle(
            id=result['id'],
            title=result['title'],
            input_message_content=InputTextMessageContent(
                # message_text=f'{result["title"]} by {result["uploader"]}, {int(result["duration"] // 60)}:{int(result["duration"] % 60):02}',
                message_text=f'{result["uploader"]} — {result["title"]}',
                link_preview_options=LinkPreviewOptions(
                    show_above_text=True,
                    url=result['thumbnail'],
                    prefer_large_media=True,
                    is_disabled=False
                )
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Downloading, please wait...', callback_data='downloading')]]),
            thumbnail_url=result['thumbnail'],
            url=result['url'],
            description=result['uploader'],
        ))

    logger.info(results)
    
    results = await query.answer(
        results=inline_results,
        cache_time=86400,
        is_personal=False
    )
    return None


@dp.chosen_inline_result()
async def chosen_inline_result_handler(inline_result: ChosenInlineResult):
    logger.info('chosen inline result')
    me = await bot.get_me()
    if inline_result.from_user.id in queued:
        await bot.edit_message_text(
            text=f'Sorry, but you must wait for previous download first :(',
            inline_message_id=inline_result.inline_message_id,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        return
    
    queued.add(inline_result.from_user.id)
    
    file = await get_file(inline_result.result_id)
    logger.info(inline_result.result_id)
    file_path = f'audio/{inline_result.result_id}.mp3'
    filename = f'{safe_filename(file["title"])}_{inline_result.result_id}.mp3'
    logger.info(f'filename: {filename}')
    logger.info(file)

    performer = file['uploader']
    title = file['title']

    for kw in REMIX_KEYWORDS:
        if kw in title.lower():
            break
    else:
        for sep in (' — ', ' - '):
            # maybe_uploader = title.split(sep, 1)[1]
            # if ', ' in maybe_uploader or uploader.lower() in maybe_uploader.lower():
            #     uploader = title.split(sep, 1)[0]
            #     title = title.split(sep, 1)[1]
            if sep not in title:
                continue
            if performer in title.split(sep, 1)[1]:
                continue
            performer = title.split(sep, 1)[0]
            title = title.split(sep, 1)[1]

    # chars_to_strip = len(performer) + 3
    # if title.lower().startswith(f'{performer.lower()} - '):
    #     title = title[chars_to_strip:]
    # elif title.lower().endswith(f'{performer.lower()} - '):
    #     title = title[:len(title) - chars_to_strip]

    title = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()
    title = re.sub(r',\s*\d{4}\s*$', '', title).strip()

    if performer.endswith('- Topic'):
        performer = performer.removesuffix(' - Topic')

    thumb = await download_and_crop_thumbnail(file['thumbnail'], inline_result.result_id)

    if os.path.exists(file_path):
        sent_message = await bot.send_audio(
            chat_id=CHAT_ID,
            audio=FSInputFile(file_path, filename),
            thumbnail=FSInputFile(thumb) if thumb is not None else None,
            title=title,
            performer=performer,
        )
        file_id = sent_message.audio.file_id
        await bot.delete_message(chat_id=CHAT_ID, message_id=sent_message.message_id)
        await bot.edit_message_media(
            media=InputMediaAudio(
                media=file_id,
                thumbnail=FSInputFile(thumb) if thumb is not None else None,
                title=title,
                performer=performer,
                filename=filename
            ),
            inline_message_id=inline_result.inline_message_id,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text='YouTube', url=f'https://www.youtube.com/watch?v={inline_result.result_id}')],
                    [InlineKeyboardButton(text=f'@{me.username}', url=f'https://t.me/{me.username}')],
                ]
            )
        )
        logger.info('File already exists')
        queued.remove(inline_result.from_user.id)
        await add_use(inline_result.result_id, inline_result.from_user.id)
        return
    
    info_dict = await download(f'https://www.youtube.com/watch?v={inline_result.result_id}', progress_callback=default_progress_callback, complete_callback=default_complete_callback, error_callback=default_error_callback)
    queued.remove(inline_result.from_user.id)
    
    if not info_dict or not os.path.exists(file_path):
        logger.info(f'info dict: {info_dict}')
        await bot.edit_message_text(
            text='Failed to download the audio.',
            inline_message_id=inline_result.inline_message_id
        )
        return

    sent_message = await bot.send_audio(
        chat_id=CHAT_ID,
        audio=FSInputFile(file_path, filename),
        thumbnail=FSInputFile(thumb) if thumb is not None else None,
        title=title,
        performer=performer,
    )
    file_id = sent_message.audio.file_id
    await bot.delete_message(chat_id=CHAT_ID, message_id=sent_message.message_id)
    
    media = InputMediaAudio(
        media=file_id,
        thumbnail=FSInputFile(thumb) if thumb is not None else None,
        title=title,
        performer=performer,
        filename=filename
    )
    
    await bot.edit_message_media(
        media=media,
        inline_message_id=inline_result.inline_message_id,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='YouTube', url=f'https://www.youtube.com/watch?v={inline_result.result_id}')],
                [InlineKeyboardButton(text=f'@{me.username}', url=f'https://t.me/{me.username}')],
            ]
        )
    )
    await add_use(inline_result.result_id, inline_result.from_user.id)
    logger.info('File downloaded')

@dp.message(F.text.startswith('@all') & F.from_user.id == int(os.getenv('ADMIN_ID')))
async def mail(message: Message):
    text = message.html_text[4:]
    async with aiosqlite.connect("db.sqlite3") as conn:
        async with conn.execute("SELECT id FROM users") as cursor:
            rows = await cursor.fetchall()
            user_ids = [row[0] for row in rows]
    for user_id in user_ids:
        await asyncio.sleep(0.05)
        try:
            await bot.send_message(user_id, text, parse_mode='HTML')
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramAPIError as e:
            pass

@dp.message(Command('stats'))
async def stats_handler(message: Message):
    async with aiosqlite.connect('db.sqlite3') as conn:
        async with conn.execute('SELECT COUNT(*) FROM users') as cursor:
            users_count = (await cursor.fetchone())[0]
        async with conn.execute('SELECT SUM(sent_videos_count) FROM users') as cursor:
            sent_videos_total = (await cursor.fetchone())[0]
        async with conn.execute('SELECT sent_videos_count FROM users WHERE id = ?', (message.from_user.id,)) as cursor:
            sent_videos_user = (await cursor.fetchone())[0]
        async with conn.execute('SELECT COUNT(*) FROM files') as cursor:
            cached_files = (await cursor.fetchone())[0]
    await message.answer(STATS_TEXT.format(users=users_count, cached=cached_files, sent_user=sent_videos_user, sent_total=sent_videos_total))
    
async def main():
    # results = await search(input('Запрос: '))
    # logger.info(results)
    # choose = input('Выберите вариант для скачивания: ')
    # item = results[int(choose)]
    # logger.info(f'Скачиваем {item["title"]}')
    # await download(item['url'], on_progress, on_complete, on_error)
    await prepare_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
