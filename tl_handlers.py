from email import message
from telethon import (
    TelegramClient,
    types as tl_types,
    functions as tl_functions,
    events as tl_events,
    hints as tl_hints,
    utils as tl_utils
)
from telethon.errors import FloodWaitError, RPCError
from telethon.extensions import html as tl_html
from telethon.custom import Message, Button
from tl_client import tl_bot
import os
import random
import re
from yt_utils import search, download
from loguru import logger
from config import queued, CHAT_ID, ADMIN_ID
from const import REMIX_KEYWORDS
from utils import (
    download_and_crop_thumbnail,
    safe_filename,
    hide_link,
    extract_performer_title,
)
from database import add_file, get_file, add_use, get_user_ids, get_stats
from text import STATS_TEXT
import asyncio


@tl_bot.on(tl_events.NewMessage(pattern="/start"))
async def tl_start_handler(event: tl_events.NewMessage.Event):
    me = await tl_bot.get_me()
    # user = await get_user(message.from_user.id)
    await event.respond(
        f"Hi! I will help you search, send and download music from YouTube! "
        f"Just type <code>@{me.username} [query]</code> and wait a few seconds.",
        parse_mode="html",
    )


@tl_bot.on(tl_events.InlineQuery())
async def tl_inline_query_handler(
    event: tl_events.InlineQuery.Event,
):
    # user = await get_user(query.from_user.id)
    query: tl_types.UpdateBotInlineQuery = event.query
    results = await search(query.query)

    if not results:
        builder = event.builder
        return await event.answer(
            results=[
                await builder.article(
                    title="No results",
                    text="No results found :(",
                )
            ],
            cache_time=3600,
        )

    inline_results = []
    builder = event.builder
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
            await builder.article(
                # content=tl_types.InputMediaWebPage(
                #     url=result["thumbnail"],
                #     force_large_media=True
                # ),
                title=result["title"],
                description=result["uploader"],
                # type="article",
                # attributes=[],
                # mime_type="text/html",
                id=result["id"],
                text=f"{hide_link(result['thumbnail'])}{result['uploader']} — {result['title']}",
                buttons=Button.inline("Downloading, please wait..."),
                thumb=tl_types.InputWebDocument(
                    url=result["thumbnail"],
                    size=0,
                    mime_type="image/jpeg",
                    attributes=[]
                ),
                url=result["url"],
                
            )
        )

    logger.info(results)

    await event.answer(results=inline_results, cache_time=86400)
    return None


@tl_bot.on(tl_events.Raw(tl_types.UpdateBotInlineSend))
async def tl_chosen_inline_result_handler(event: tl_types.UpdateBotInlineSend):
    logger.info("chosen inline result")
    me = await tl_bot.get_me()
    if event.user_id in queued:
        await tl_bot.edit_message(
            text="Sorry, but you must wait for previous download first :(",
            message=event.msg_id,
            link_preview=False,
        )
        return

    queued.add(event.user_id)

    result_id = event.id

    file = await get_file(result_id)
    logger.info(result_id)
    file_path = f"audio/{result_id}.mp3"
    filename = f"{safe_filename(file['title'])}_{result_id}.mp3"
    logger.info(f"filename: {filename}")
    logger.info(file)

    performer, title = extract_performer_title(file["uploader"], file["title"])

    logger.info("get thumbnail")
    thumb = await download_and_crop_thumbnail(file["thumbnail"], result_id)

    if os.path.exists(file_path):
        logger.info("File already exists")
        input_file = await tl_bot.upload_file(
            file=file_path,
            file_name=filename
        )
        logger.info("edit message")
        await tl_bot(tl_functions.messages.EditInlineBotMessageRequest(
            id=event.msg_id,
            media=tl_types.InputMediaUploadedDocument(
                file=input_file,
                mime_type='audio/mpeg',
                attributes=[
                    tl_types.DocumentAttributeAudio(
                        duration=file["duration"], title=title, performer=performer
                    ),
                    tl_types.DocumentAttributeFilename(file_name=filename)
                ],
            thumb=thumb if thumb is not None else None,
            reply_markup=tl_types.ReplyInlineMarkup([
                tl_types.KeyboardButtonRow(
                    tl_types.KeyboardButtonUrl("YouTube", f"https://www.youtube.com/watch?v={event.id}")
                ),
                tl_types.KeyboardButtonRow(
                    tl_types.KeyboardButtonUrl(f"@{me.username}", f"https://t.me/{me.username}")
                )
            ]),
            )
        ))
        queued.remove(event.user_id)
        logger.info("add use")
        await add_use(event.id, event.user_id)
        logger.info("done")
        return

    # info_dict = await download(f'https://www.youtube.com/watch?v={inline_result.result_id}', progress_callback=default_progress_callback, complete_callback=default_complete_callback, error_callback=default_error_callback)
    info_dict = await download(f"https://www.youtube.com/watch?v={event.id}")
    queued.remove(event.user_id)

    if not info_dict or not os.path.exists(file_path):
        logger.info(f"info dict: {info_dict}")
        await tl_bot.edit_message(
            entity=event.user_id,
            message=event.msg_id,
            text="Failed to download the audio.",
        )
        return

    input_file = await tl_bot.upload_file(
        file=file_path,
        file_name=filename
    )

    await tl_bot(tl_functions.messages.EditInlineBotMessageRequest(
        id=event.msg_id,
        media=tl_types.InputMediaUploadedDocument(
            file=input_file,
            mime_type='audio/mpeg',
            attributes=[
                tl_types.DocumentAttributeAudio(
                    duration=file["duration"], title=title, performer=performer
                ),
                tl_types.DocumentAttributeFilename(file_name=filename)
            ],
        thumb=thumb if thumb is not None else None,
        reply_markup=tl_types.ReplyInlineMarkup([
            tl_types.KeyboardButtonRow(
                tl_types.KeyboardButtonUrl("YouTube", f"https://www.youtube.com/watch?v={event.id}")
            ),
            tl_types.KeyboardButtonRow(
                tl_types.KeyboardButtonUrl(f"@{me.username}", f"https://t.me/{me.username}")
            )
        ]),
        )
    ))
    await add_use(event.id, event.user_id)
    logger.info("File downloaded")


@tl_bot.on(tl_events.NewMessage(pattern=r"^@all"))
async def tl_mail_handler(event: tl_events.NewMessage.Event):
    if event.sender_id != ADMIN_ID:
        return
    text = tl_html.unparse(event.raw_text, event.entities)[4:]
    user_ids = await get_user_ids()
    for user_id in user_ids:
        await asyncio.sleep(0.05)
        try:
            await tl_bot.send_message(user_id, text, parse_mode="HTML")
        except FloodWaitError as e:
            await asyncio.sleep(e.retry_after)
            await tl_bot.send_message(user_id, text, parse_mode="HTML")
        except RPCError:
            pass


@tl_bot.on(tl_events.NewMessage(pattern="/stats"))
async def tl_stats_handler(event: tl_events.NewMessage.Event):
    stats = await get_stats(event.sender_id)
    await event.respond(
        STATS_TEXT.format(
            users=stats.users_count,
            cached=stats.cached_files,
            sent_user=stats.sent_videos_user,
            sent_total=stats.sent_videos_total,
            downloaded=stats.downloaded,
        )
    )
