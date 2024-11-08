# 베이스 이미지
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 파일 복사
COPY requirements.txt .

# 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# .env 파일을 Docker 이미지에 포함하지 않고, 나중에 크레덴셜을 설정해 사용할 예정
EXPOSE 9002

# uvicorn을 이용해 FastAPI 앱 실행
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9002", "--reload"]
