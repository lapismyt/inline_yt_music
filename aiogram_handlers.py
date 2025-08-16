from aiogram_client import aiogram_bot, aiogram_dp
import os
import random
import re
from aiogram.filters import Command, CommandStart
from aiogram import F
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    FSInputFile,
    LinkPreviewOptions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChosenInlineResult,
    InputMediaAudio,
)
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from yt_utils import search, download
from loguru import logger
from config import queued, CHAT_ID
from const import REMIX_KEYWORDS
from utils import download_and_crop_thumbnail, safe_filename
from database import add_file, get_file, add_use, get_user_ids, get_stats
from text import STATS_TEXT
import asyncio
from audio_manager import cleanup_audio_folder


@aiogram_dp.message(CommandStart())
async def start(message: Message):
    me = await aiogram_bot.get_me()
    # user = await get_user(message.from_user.id)
    await message.answer(
        f"Hi! I will help you search, send and download music from YouTube! "
        f"Just type <code>@{me.username} [query]</code> and wait a few seconds.",
        parse_mode="html",
    )


@aiogram_dp.inline_query()
async def inline_query_handler(query: InlineQuery, *args, **kwargs):
    # user = await get_user(query.from_user.id)
    results = await search(query.query)

    if not results:
        return await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(random.randint(10000, 99999)),
                    title="No results",
                    input_message_content=InputTextMessageContent(
                        message_text="No results found :("
                    ),
                )
            ],
            cache_time=3600,
            is_personal=False,
        )

    inline_results = []
    for result in results:
        logger.info(result["id"])
        await add_file(
            result["id"],
            result["title"],
            result["uploader"],
            result["thumbnail"],
            result["duration"],
        )
        inline_results.append(
            InlineQueryResultArticle(
                id=result["id"],
                title=result["title"],
                input_message_content=InputTextMessageContent(
                    # message_text=f'{result["title"]} by {result["uploader"]}, {int(result["duration"] // 60)}:{int(result["duration"] % 60):02}',
                    message_text=f"{result['uploader']} — {result['title']}",
                    link_preview_options=LinkPreviewOptions(
                        show_above_text=True,
                        url=result["thumbnail"],
                        prefer_large_media=True,
                        is_disabled=False,
                    ),
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Downloading, please wait...",
                                callback_data="downloading",
                            )
                        ]
                    ]
                ),
                thumbnail_url=result["thumbnail"],
                url=result["url"],
                description=result["uploader"],
            )
        )

    logger.info(results)

    results = await query.answer(
        results=inline_results, cache_time=86400, is_personal=False
    )
    return None


@aiogram_dp.chosen_inline_result()
async def chosen_inline_result_handler(inline_result: ChosenInlineResult):
    logger.info("chosen inline result")
    me = await aiogram_bot.get_me()
    if inline_result.from_user.id in queued:
        await aiogram_bot.edit_message_text(
            text="Sorry, but you must wait for previous download first :(",
            inline_message_id=inline_result.inline_message_id,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    queued.add(inline_result.from_user.id)

    file = await get_file(inline_result.result_id)
    logger.info(inline_result.result_id)
    file_path = f"audio/{inline_result.result_id}.mp3"
    filename = f"{safe_filename(file['title'])}_{inline_result.result_id}.mp3"
    logger.info(f"filename: {filename}")
    logger.info(file)

    performer = file["uploader"]
    title = file["title"]

    for kw in REMIX_KEYWORDS:
        if kw in title.lower():
            break
    else:
        for sep in (" — ", " - "):
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

    title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    title = re.sub(r",\s*\d{4}\s*$", "", title).strip()

    if performer.endswith("- Topic"):
        performer = performer.removesuffix(" - Topic")

    logger.info("get thumbnail")
    thumb = await download_and_crop_thumbnail(
        file["thumbnail"], inline_result.result_id
    )

    if os.path.exists(file_path):
        logger.info("File already exists")
        logger.info("send audio")
        sent_message = await aiogram_bot.send_audio(
            chat_id=CHAT_ID,
            audio=FSInputFile(file_path, filename),
            thumbnail=FSInputFile(thumb) if thumb is not None else None,
            title=title,
            performer=performer,
        )
        logger.info("delete message")
        file_id = sent_message.audio.file_id
        await aiogram_bot.delete_message(
            chat_id=CHAT_ID, message_id=sent_message.message_id
        )
        logger.info("edit message")
        await aiogram_bot.edit_message_media(
            media=InputMediaAudio(
                media=file_id,
                thumbnail=FSInputFile(thumb) if thumb is not None else None,
                title=title,
                performer=performer,
                filename=filename,
            ),
            inline_message_id=inline_result.inline_message_id,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="YouTube",
                            url=f"https://www.youtube.com/watch?v={inline_result.result_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text=f"@{me.username}", url=f"https://t.me/{me.username}"
                        )
                    ],
                ]
            ),
        )
        queued.remove(inline_result.from_user.id)
        logger.info("add use")
        await add_use(inline_result.result_id, inline_result.from_user.id)
        logger.info("done")
        return

    # info_dict = await download(f'https://www.youtube.com/watch?v={inline_result.result_id}', progress_callback=default_progress_callback, complete_callback=default_complete_callback, error_callback=default_error_callback)
    info_dict = await download(
        f"https://www.youtube.com/watch?v={inline_result.result_id}"
    )
    queued.remove(inline_result.from_user.id)

    if not info_dict or not os.path.exists(file_path):
        logger.info(f"info dict: {info_dict}")
        await aiogram_bot.edit_message_text(
            text="Failed to download the audio.",
            inline_message_id=inline_result.inline_message_id,
        )
        return

    sent_message = await aiogram_bot.send_audio(
        chat_id=CHAT_ID,
        audio=FSInputFile(file_path, filename),
        thumbnail=FSInputFile(thumb) if thumb is not None else None,
        title=title,
        performer=performer,
    )
    file_id = sent_message.audio.file_id
    await aiogram_bot.delete_message(
        chat_id=CHAT_ID, message_id=sent_message.message_id
    )

    media = InputMediaAudio(
        media=file_id,
        thumbnail=FSInputFile(thumb) if thumb is not None else None,
        title=title,
        performer=performer,
        filename=filename,
    )

    await aiogram_bot.edit_message_media(
        media=media,
        inline_message_id=inline_result.inline_message_id,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="YouTube",
                        url=f"https://www.youtube.com/watch?v={inline_result.result_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=f"@{me.username}", url=f"https://t.me/{me.username}"
                    )
                ],
            ]
        ),
    )
    await add_use(inline_result.result_id, inline_result.from_user.id)
    logger.info("File downloaded")
    
    # Clean up audio folder if needed
    try:
        deleted_files = cleanup_audio_folder()
        if deleted_files:
            logger.info(f"Cleaned up audio folder, deleted {len(deleted_files)} files")
    except Exception as e:
        logger.error(f"Error during audio folder cleanup: {str(e)}")


@aiogram_dp.message(
    F.text.startswith("@all") & F.from_user.id == int(os.getenv("ADMIN_ID"))
)
async def mail(message: Message):
    text = message.html_text[4:]
    user_ids = await get_user_ids()
    for user_id in user_ids:
        await asyncio.sleep(0.05)
        try:
            await aiogram_bot.send_message(user_id, text, parse_mode="HTML")
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await aiogram_bot.send_message(user_id, text, parse_mode="HTML")
        except TelegramAPIError:
            pass


@aiogram_dp.message(Command("stats"))
async def stats_handler(message: Message):
    stats = await get_stats(message.from_user.id)
    await message.answer(
        STATS_TEXT.format(
            users=stats.users_count,
            cached=stats.cached_files,
            sent_user=stats.sent_videos_user,
            sent_total=stats.sent_videos_total,
            downloaded=stats.downloaded,
        )
    )
