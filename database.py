# database.py
import os
from dotenv import load_dotenv
import databases
import sqlalchemy
from sqlalchemy import create_engine, MetaData

# 환경 변수 로드
load_dotenv()

# 환경 변수에서 DATABASE_URL 가져오기
DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL:", DATABASE_URL)  # 로드된 DATABASE_URL 값 확인

# 데이터베이스 연결 및 메타데이터 객체 생성
database = databases.Database(DATABASE_URL)
engine = create_engine(DATABASE_URL)
metadata = MetaData()
