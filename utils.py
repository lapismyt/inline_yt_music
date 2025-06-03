import os
import aiohttp
from loguru import logger
import io
from PIL import Image
import re
from const import REMIX_KEYWORDS


async def download_and_crop_thumbnail(url: str | None, video_id: str) -> str | None:
    if not url:
        return None

    thumb_dir = "thumbnails"
    os.makedirs(thumb_dir, exist_ok=True)
    filename = os.path.join(thumb_dir, f"{video_id}.jpg")

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
                cropped.save(filename, "JPEG", quality=85)

                return filename
    except Exception as e:
        logger.error(f"Thumbnail error: {str(e)}")
        return None


def safe_filename(title: str, max_length=64) -> str:
    safe = re.sub(r'[\\/*?:"<>|\x00-\x1F]', "", title)
    return safe.strip()


def hide_link(url: str) -> str:
    return f'<a href="{url}">&#8203;</a>'


def extract_performer_title(performer: str, title: str):
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

    return performer, title
