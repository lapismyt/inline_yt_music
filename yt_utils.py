from loguru import logger
import yt_dlp
from config import SEARCH_LIMIT, LENGTH_LIMIT
from const import REMIX_KEYWORDS
from database import set_downloaded, add_file
import os
from typing import Callable
import time
import re


async def search(query: str) -> list:
    ydl_opts = {
        "extract_flat": True,
        "force_generic_extractor": True,
        "verbose": True,
        "noplaylist": True,
        "ignoreerrors": True,
        # 'cookiefile': os.getenv('COOKIEFILE')
    }

    search_results = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch{SEARCH_LIMIT * 2}:{query}"
        result = ydl.extract_info(search_query, download=False)

        logger.info(result)

        if not result or "entries" not in result:
            logger.info(f"No results for {query} #1")
            return []

        for entry in result["entries"]:
            if entry and len(search_results) < SEARCH_LIMIT:
                thumbnails = entry.get("thumbnails", [])
                thumbnail = next(
                    (t["url"] for t in reversed(thumbnails) if t.get("url")),
                    "https://i.ytimg.com/vi/{}/hqdefault.jpg".format(
                        entry.get("id", "")
                    ),
                )

                if not (
                    thumbnail.startswith("https://" or thumbnail.startswith("http://"))
                ):
                    if thumbnail.startswith("//"):
                        thumbnail = f"https:{thumbnail}"
                    else:
                        thumbnail = f"https://{thumbnail}"

                video_data = {
                    "title": entry.get("title", "Без названия"),
                    "duration": (entry.get("duration", 0)) or 0,
                    "thumbnail": thumbnail,
                    "uploader": entry.get("uploader", "Неизвестный автор"),
                    "url": entry.get("url", ""),
                    "view_count": entry.get("view_count", 0),
                    "id": entry.get("id", ""),
                }

                uploader = video_data["uploader"]
                title = video_data["title"]

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
                        if uploader in title.split(sep, 1)[1]:
                            continue
                        uploader = title.split(sep, 1)[0]
                        title = title.split(sep, 1)[1]

                # chars_to_strip = len(uploader) + 3
                # if title.lower().startswith(f'{uploader.lower()} - '):
                #     title = title[chars_to_strip:]
                # elif title.lower().endswith(f'{uploader.lower()} - '):
                #     title = title[:len(title) - chars_to_strip]

                title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
                title = re.sub(r",\s*\d{4}\s*$", "", title).strip()

                if uploader.endswith("- Topic"):
                    uploader = uploader.removesuffix(" - Topic")

                video_data["title"] = title
                video_data["uploader"] = uploader

                if video_data["duration"] > LENGTH_LIMIT * 60:
                    logger.info("Skip result #1")
                    continue
                await add_file(
                    video_data["id"],
                    video_data["title"],
                    video_data["uploader"],
                    video_data["thumbnail"],
                    video_data["duration"],
                )
                search_results.append(video_data)

        logger.info(search_results)

        return search_results


def default_progress_callback(current, total, speed):
    logger.info(f"Downloading {current} of {total} bytes ({speed} bytes/sec)")


def default_complete_callback(filename):
    logger.info(f"Download complete: {filename}")


def default_error_callback(error, url):
    logger.info(f"Error: {repr(error)} for {url}")


async def download(
    url: str,
    progress_callback: Callable = default_complete_callback,
    complete_callback: Callable = default_complete_callback,
    error_callback: Callable = default_error_callback,
):
    output_dir = "audio"
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "external_downloader": "aria2c",
        "nocheckcertificate": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
        ],
        "postprocessor_args": {
            "embedthumbnail+ffmpeg_o": [
                "-c:v",
                "png",
                "-vf",
                "crop='if(gt(ih,iw),iw,ih)':'if(gt(iw,ih),ih,iw)'",
                "-preset",
                "veryfast",
            ]
        },
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "embedthumbnail": True,
        "writethumbnail": True,
        "keepvideo": False,
        "quiet": True,
        "http_chunk_size": 2621440,
        "noprogress": True,
        "no_warnings": True,
        "progress_hooks": [],
        "restrictfilenames": True,
        "clean_infojson": True,
    }

    last_progress_time = 0
    final_filename = None

    def progress_hook(d):
        nonlocal last_progress_time, final_filename
        if d["status"] == "downloading":
            current_time = time.time()
            if current_time - last_progress_time >= 1:
                last_progress_time = current_time
                if progress_callback:
                    current = d.get("downloaded_bytes", 0)
                    total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    speed = d.get("speed", 0)
                    progress_callback(current, total, speed)

        elif d["status"] == "finished":
            video_id = d["info_dict"].get("id", "unknown")
            final_filename = os.path.join(output_dir, f"{video_id}.mp3")

    ydl_opts["progress_hooks"].append(progress_hook)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict: dict = ydl.extract_info(url, download=False)
            video_id = info_dict.get("id", "unknown")
            predicted_filename = os.path.join(output_dir, f"{video_id}.mp3")

            if os.path.exists(predicted_filename):
                logger.info(f"Файл уже существует: {predicted_filename}")
                if complete_callback:
                    complete_callback(predicted_filename)
                return predicted_filename

            ydl.download([url])

            if complete_callback and final_filename:
                complete_callback(final_filename)

            await set_downloaded(video_id)
            return info_dict

    except Exception as e:
        if error_callback:
            error_callback(e, url)
        else:
            logger.error(f"Ошибка при обработке {url}: {str(e)}")
        return None
