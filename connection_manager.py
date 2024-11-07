from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict
from models import database, chatbot, chating_content
import asyncpg
from typing import Optional

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.chat_histories: Dict[int, List[dict]] = {}

    async def connect(self, websocket: WebSocket, member_num: int, book_id: int):
        chat_id = await self.get_or_create_chat_id(member_num, book_id)
        if chat_id not in self.chat_histories:
            query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
            rows = await database.fetch_all(query, values={"chat_id": chat_id})
            self.chat_histories[chat_id] = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
            for entry in self.chat_histories[chat_id]:
                try:
                    await websocket.send_json(entry)
                except WebSocketDisconnect:
                    print("[연결 끊김] 클라이언트가 연결을 종료했습니다.")
                    break
        return chat_id

    async def broadcast(self, websocket: WebSocket, message: dict):
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            print("[브로드캐스트 중 연결 끊김] 클라이언트가 연결을 종료했습니다.")

    def disconnect(self, websocket: WebSocket, chat_id: int):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WebSocket 연결 해제] chat_id: {chat_id}")

    async def get_or_create_chat_id(self, member_num: int, book_id: Optional[int] = None) -> int:
        # **book_id가 None인 경우 0으로 설정**
        if book_id is None:
            book_id = 0

        query = "SELECT chat_id FROM chatbot WHERE member_num = :member_num AND book_id = :book_id"
        result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})

        if result:
            return result["chat_id"]

        # 데이터베이스에 새 chat_id 생성 시도
        try:
            create_query = """
            INSERT INTO chatbot (book_id, member_num)
            VALUES (:book_id, :member_num)
            RETURNING chat_id
            """
            chat_id = await database.execute(create_query, values={"book_id": book_id, "member_num": member_num})
            return chat_id
        except asyncpg.exceptions.UniqueViolationError:
            # 중복된 레코드가 이미 있는 경우 기존 chat_id 반환
            result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})
            if result:
                return result["chat_id"]
            else:
                raise ValueError("chat_id 생성 또는 조회에 실패했습니다.")



    async def save_message(self, chat_id: int, content: str, sender_id: str):
        query = "INSERT INTO chating_content (chat_id, chat_content, sender_id) VALUES (:chat_id, :chat_content, :sender_id)"
        await database.execute(query, values={"chat_id": chat_id, "chat_content": content, "sender_id": sender_id})
