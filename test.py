from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from fastapi.middleware.cors import CORSMiddleware
from database import database, metadata
from typing import List, Dict
from dotenv import load_dotenv
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

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.chat_histories: Dict[int, List[str]] = {}

    async def connect(self, websocket: WebSocket, member_num: int, book_id: int):
        await websocket.accept()
        print(f"[WebSocket 연결] member_num: {member_num}, book_id: {book_id}")
        
        self.active_connections.append(websocket)
        
        # 기존 채팅 내역을 불러와서 클라이언트에 전송
        chat_id = await self.get_or_create_chat_id(member_num, book_id)
        if chat_id not in self.chat_histories:
            # 데이터베이스에서 채팅 내역을 직접 가져오기
            query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
            rows = await database.fetch_all(query, values={"chat_id": chat_id})
            
            # 가져온 채팅 내역을 chat_histories에 저장
            self.chat_histories[chat_id] = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
            print(f"[기존 채팅 불러오기] chat_id: {chat_id}, history: {self.chat_histories[chat_id]}")

            # 기존 대화 내역을 WebSocket 연결 시 한 번만 클라이언트로 전송
            try:
                for entry in self.chat_histories[chat_id]:
                    await websocket.send_json(entry)
            except WebSocketDisconnect:
                print(f"[WebSocket 연결 끊김] member_num: {member_num}, book_id: {book_id}")
                self.disconnect(websocket, chat_id)

        return chat_id

    # load_chat_history 함수는 그대로 유지하되, connect에서만 호출
    async def load_chat_history(self, chat_id: int) -> List[dict]:
        query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
        rows = await database.fetch_all(query, values={"chat_id": chat_id})
        history = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
        print(f"[채팅 내역 불러오기] chat_id: {chat_id}, history: {history}")
        return history


    def disconnect(self, websocket: WebSocket, chat_id: int):
        self.active_connections.remove(websocket)
        print(f"[WebSocket 연결 해제] chat_id: {chat_id}")
        # `chat_histories` 삭제를 하지 않음으로써 대화 내역을 유지


    async def broadcast(self, websocket: WebSocket, message: dict):
        print(f"[메시지 브로드캐스트] message: {message}")
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            self.active_connections.remove(websocket)

    async def get_or_create_chat_id(self, member_num: int, book_id: int) -> int:
        # 기존의 chat_id 조회
        query = "SELECT chat_id FROM chatbot WHERE member_num = :member_num AND book_id = :book_id"
        result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})

        # chat_id가 이미 존재하는 경우 바로 반환
        if result:
            print(f"[기존 chat_id 확인] chat_id: {result['chat_id']}")
            return result["chat_id"]
        
        # 존재하지 않는 경우 새로운 chat_id 생성
        create_query = """
        INSERT INTO chatbot (book_id, member_num) 
        VALUES (:book_id, :member_num) 
        ON CONFLICT DO NOTHING 
        RETURNING chat_id
        """
        chat_id = await database.execute(create_query, values={"book_id": book_id, "member_num": member_num})

        # INSERT 실패 시 다시 chat_id 조회
        if chat_id is None:
            result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})
            if result:
                print(f"[중복 데이터로 인해 기존 chat_id 반환] chat_id: {result['chat_id']}")
                return result["chat_id"]
            else:
                raise ValueError("chat_id 생성 또는 조회에 실패했습니다.")
        
        print(f"[새로운 chat_id 생성] chat_id: {chat_id}")
        return chat_id



    async def load_chat_history(self, chat_id: int) -> List[dict]:
        query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
        rows = await database.fetch_all(query, values={"chat_id": chat_id})
        history = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
        print(f"[채팅 내역 불러오기] chat_id: {chat_id}, history: {history}")
        return history


manager = ConnectionManager()
chat_model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o-mini")

prompt_template = """
You are a book expert. Maintain an ongoing conversation with the user about the book they are discussing, providing detailed insights and encouraging follow-up questions. Answer in hangul.

대화 기록:
{chat_history}

사용자: {user_message}
book expert:
"""

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket, member_num: int, book_id: int):
    # 연결할 때마다 콘솔에 출력
    print(f"[WebSocket 요청 수신] member_num: {member_num}, book_id: {book_id}")
    chat_id = await manager.connect(websocket, member_num, book_id)
    try:
        while True:
            data = await websocket.receive_text()
            if not data.strip():  # 빈 메시지 무시
                continue

            chat_history = "\n".join([entry["message"] for entry in manager.chat_histories.get(chat_id, [])])
            prompt = PromptTemplate(input_variables=["chat_history", "user_message"], template=prompt_template)
            formatted_prompt = prompt.format(chat_history=chat_history, user_message=data)
            
            response = await chat_model.agenerate([formatted_prompt])
            bot_message_content = response.generations[0][0].text.strip()  # 응답 내용만 추출

            # 사용자와 Stella의 메시지를 각각 sender_id와 함께 저장
            user_message = {"sender_id": "user", "message": data}
            stella_message = {"sender_id": "stella", "message": bot_message_content}
            manager.chat_histories[chat_id].append(user_message)
            manager.chat_histories[chat_id].append(stella_message)
            
            save_query = "INSERT INTO chating_content (chat_id, chat_content, sender_id) VALUES (:chat_id, :chat_content, :sender_id)"
            await database.execute(save_query, values={"chat_id": chat_id, "chat_content": data, "sender_id": "user"})
            await database.execute(save_query, values={"chat_id": chat_id, "chat_content": bot_message_content, "sender_id": "stella"})

            # Stella의 메시지를 클라이언트에 전송
            await manager.broadcast(websocket, stella_message)
    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)

@app.get("/api/chat/{book_id}/{member_num}")
async def get_chat_history(book_id: int, member_num: int):
    query = """
    SELECT cc.chat_content, cc.sender_id
    FROM chating_content cc
    JOIN chatbot cb ON cb.chat_id = cc.chat_id
    WHERE cb.book_id = :book_id AND cb.member_num = :member_num
    ORDER BY cc.timestamp ASC
    """
    rows = await database.fetch_all(query, values={"book_id": book_id, "member_num": member_num})
    chat_history = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
    return chat_history

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
