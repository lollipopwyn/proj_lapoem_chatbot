# models.py: 데이터베이스 모델 및 쿼리 로직 정의
from dotenv import load_dotenv
import os
from databases import Database
from sqlalchemy import MetaData, Table, Column, Integer, String, Text

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
database = Database(DATABASE_URL)
metadata = MetaData()

# Define database tables if using SQLAlchemy
chating_content = Table(
    "chating_content", metadata,
    Column("chat_id", Integer),
    Column("chat_content", Text),
    Column("sender_id", String),
)

chatbot = Table(
    "chatbot", metadata,
    Column("chat_id", Integer, primary_key=True),
    Column("member_num", Integer),
    Column("book_id", Integer)
)

async def get_chat_history(book_id: int, member_num: int):
    query = """
    SELECT cc.chat_content, cc.sender_id
    FROM chating_content cc
    JOIN chatbot cb ON cb.chat_id = cc.chat_id
    WHERE cb.book_id = :book_id AND cb.member_num = :member_num
    ORDER BY cc.timestamp ASC
    """
    rows = await database.fetch_all(query, values={"book_id": book_id, "member_num": member_num})
    return [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
