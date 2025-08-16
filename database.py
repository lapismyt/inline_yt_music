from sqlmodel import SQLModel, create_engine, Session, select, Field, Column, Integer, String, Boolean, BigInteger
from loguru import logger
import os
from dataclasses import dataclass
from config import DATABASE_URL

# Database Models
class File(SQLModel, table=True):
    id: int | None = Field(default=None, sa_column=Column(BigInteger(), primary_key=True, autoincrement=True))
    video_id: str = Field(sa_column_kwargs={"unique": True}, max_length=255)
    uses_count: int = Field(default=0)
    duration: int | None = None
    thumbnail: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    uploader: str | None = Field(default=None, max_length=255)
    downloaded: bool = Field(default=False)

class User(SQLModel, table=True):
    id: int | None = Field(default=None, sa_column=Column(BigInteger(), primary_key=True))
    sent_videos_count: int = Field(default=0)

# Database engine
engine = create_engine(DATABASE_URL, echo=True)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)

# Bot Stats dataclass
@dataclass
class BotStats:
    users_count: int
    sent_videos_total: int
    sent_videos_user: int
    cached_files: int
    downloaded: int

async def prepare_db():
    # This function doesn't need to be async, but we'll keep it for compatibility
    create_db_and_tables()

async def add_use(video_id: str, user_id: int):
    try:
        with get_session() as session:
            # Get or create file
            statement = select(File).where(File.video_id == video_id)
            file = session.exec(statement).first()
            
            if not file:
                file = File(video_id=video_id)
                session.add(file)
            
            # Increment uses count
            file.uses_count += 1
            
            # Get or create user
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).first()
            
            if not user:
                user = User(id=user_id, sent_videos_count=1)
                session.add(user)
            else:
                user.sent_videos_count += 1
            
            session.commit()
    except Exception as e:
        logger.error(f"Ошибка в add_use: {str(e)}")
        session.rollback()

async def add_file(
    video_id: str, title: str, uploader: str, thumbnail: str, duration: int
):
    with get_session() as session:
        statement = select(File).where(File.video_id == video_id)
        file = session.exec(statement).first()
        
        if not file:
            file = File(
                video_id=video_id,
                title=title,
                uploader=uploader,
                thumbnail=thumbnail,
                duration=duration
            )
            session.add(file)
        else:
            file.title = title
            file.uploader = uploader
            file.thumbnail = thumbnail
            file.duration = duration
        
        session.commit()

async def get_user(user_id: int):
    with get_session() as session:
        statement = select(User).where(User.id == user_id)
        user = session.exec(statement).first()
        
        if not user:
            user = User(id=user_id, sent_videos_count=0)
            session.add(user)
            session.commit()
            session.refresh(user)
        
        return user

async def get_file(video_id: str):
    with get_session() as session:
        statement = select(File).where(File.video_id == video_id)
        file = session.exec(statement).first()
        
        if file:
            thumbnail = file.thumbnail
            if thumbnail is not None:
                if not (thumbnail.startswith("https://") or thumbnail.startswith("http://")):
                    if thumbnail.startswith("//"):
                        thumbnail = f"https:{thumbnail}"
                    else:
                        thumbnail = f"https://{thumbnail}"
            
            return {
                "id": file.id,
                "video_id": file.video_id,
                "uses_count": file.uses_count,
                "duration": file.duration,
                "thumbnail": thumbnail,
                "title": file.title,
                "uploader": file.uploader,
                "downloaded": file.downloaded,
            }
        else:
            return None

async def set_downloaded(video_id: str, value: int = 1):
    with get_session() as session:
        statement = select(File).where(File.video_id == video_id)
        file = session.exec(statement).first()
        
        if file:
            file.downloaded = bool(value)
            session.commit()

async def get_user_ids() -> list[int]:
    with get_session() as session:
        statement = select(User.id)
        user_ids = session.exec(statement).all()
        return list(user_ids)

async def get_stats(user_id: int) -> BotStats:
    with get_session() as session:
        # Get users count
        statement = select(User)
        users_count = len(session.exec(statement).all())
        
        # Get total sent videos
        statement = select(User.sent_videos_count)
        sent_videos_total = sum(session.exec(statement).all())
        
        # Get user's sent videos count
        statement = select(User.sent_videos_count).where(User.id == user_id)
        sent_videos_user = session.exec(statement).first() or 0
        
        # Get cached files count
        statement = select(File)
        cached_files = len(session.exec(statement).all())
        
        # Get downloaded files count
        downloaded = len(os.listdir("audio")) - 1 if os.path.exists("audio") else 0

    return BotStats(
        users_count=users_count,
        sent_videos_total=sent_videos_total,
        sent_videos_user=sent_videos_user,
        cached_files=cached_files,
        downloaded=downloaded,
    )
