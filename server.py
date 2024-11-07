from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from models import database, get_chat_history
from connection_manager import ConnectionManager
from chat import chat_model, create_prompt

import os

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()

@app.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket, 
    member_num: int, 
    book_id: Optional[int] = Query(None)
):
    # WebSocket 연결을 수락합니다.
    await websocket.accept()
    
    # book_id가 없을 때를 대비하여 chat_id를 생성
    chat_id = await manager.connect(websocket, member_num, book_id)

    try:
        while True:
            data = await websocket.receive_text()
            if not data.strip():
                continue

            chat_history = "\n".join([entry["message"] for entry in manager.chat_histories.get(chat_id, [])])
            prompt = create_prompt(chat_history, data)
            
            response = await chat_model.agenerate([prompt])
            bot_message_content = response.generations[0][0].text.strip()

            user_message = {"sender_id": "user", "message": data}
            stella_message = {"sender_id": "stella", "message": bot_message_content}
            manager.chat_histories[chat_id].append(user_message)
            manager.chat_histories[chat_id].append(stella_message)
            
            # book_id가 있을 경우에만 메시지 저장
            if book_id is not None:
                await manager.save_message(chat_id, data, "user")
                await manager.save_message(chat_id, bot_message_content, "stella")

            await manager.broadcast(websocket, stella_message)
    except WebSocketDisconnect:
        print("[WebSocket 연결 끊김] 클라이언트가 연결을 종료했습니다.")
        manager.disconnect(websocket, chat_id)
    
@app.get("/")
async def root():
    return {"message": "서버가 정상적으로 실행 중입니다."}

@app.get("/api/chat/{book_id}/{member_num}")
async def api_get_chat_history(book_id: int, member_num: int):
    return await get_chat_history(book_id, member_num)

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
