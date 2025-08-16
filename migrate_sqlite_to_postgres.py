#!/usr/bin/env python3
"""
Migration script to transfer data from SQLite3 to PostgreSQL
"""

import aiosqlite
import asyncio
from sqlmodel import SQLModel, create_engine, Session, select
from database import File, User, engine as postgres_engine

# SQLite database path
SQLITE_DB_PATH = "db.sqlite3"

async def migrate_data():
    # Create tables in PostgreSQL
    SQLModel.metadata.create_all(postgres_engine)
    
    # Connect to SQLite database
    async with aiosqlite.connect(SQLITE_DB_PATH) as sqlite_conn:
        # Migrate files table
        await migrate_files(sqlite_conn)
        
        # Migrate users table
        await migrate_users(sqlite_conn)
        
    print("Migration completed successfully!")

async def migrate_files(sqlite_conn):
    print("Migrating files...")
    
    # Get all files from SQLite
    async with sqlite_conn.execute("SELECT * FROM files") as cursor:
        rows = await cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
    
    # Create a session for PostgreSQL
    with Session(postgres_engine) as session:
        for row in rows:
            # Create a dictionary from row data
            row_dict = dict(zip(column_names, row))
            
            # Create File object
            file = File(
                id=row_dict['id'],
                video_id=row_dict['video_id'],
                uses_count=row_dict['uses_count'] or 0,
                duration=row_dict['duration'],
                thumbnail=row_dict['thumbnail'],
                title=row_dict['title'],
                uploader=row_dict['uploader'],
                downloaded=bool(row_dict['downloaded']) if row_dict['downloaded'] is not None else False
            )
            
            # Add to session
            session.add(file)
        
        # Commit all files
        session.commit()
    
    print(f"Migrated {len(rows)} files")

async def migrate_users(sqlite_conn):
    print("Migrating users...")
    
    # Get all users from SQLite
    async with sqlite_conn.execute("SELECT * FROM users") as cursor:
        rows = await cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
    
    # Create a session for PostgreSQL
    with Session(postgres_engine) as session:
        for row in rows:
            # Create a dictionary from row data
            row_dict = dict(zip(column_names, row))
            
            # Create User object
            user = User(
                id=row_dict['id'],
                sent_videos_count=row_dict['sent_videos_count'] or 0
            )
            
            # Add to session
            session.add(user)
        
        # Commit all users
        session.commit()
    
    print(f"Migrated {len(rows)} users")

if __name__ == "__main__":
    asyncio.run(migrate_data())
