from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from fastapi.middleware.cors import CORSMiddleware
from database import database, metadata
from typing import List, Dict
from dotenv import load_dotenv
import os
import re

# 환경 변수 로드
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# FastAPI 앱 생성 및 CORS 설정
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인에서 요청 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# WebSocket 연결을 관리하는 클래스
class ConnectionManager:
    def __init__(self):
        # 활성 WebSocket 연결 리스트 및 채팅 기록 관리용 딕셔너리
        self.active_connections: List[WebSocket] = []
        self.chat_histories: Dict[int, List[str]] = {}

    # WebSocket 연결을 수락하고 기존 채팅 내역을 불러와 클라이언트로 전송
    async def connect(self, websocket: WebSocket, member_num: int, book_id: int):
        await websocket.accept()  # WebSocket 연결 수락
        print(f"[WebSocket 연결] member_num: {member_num}, book_id: {book_id}")
        
        # WebSocket 연결을 active_connections에 추가
        self.active_connections.append(websocket)
        
        # member_num과 book_id로 chat_id 생성 또는 조회
        chat_id = await self.get_or_create_chat_id(member_num, book_id)
        if chat_id not in self.chat_histories:
            # 데이터베이스에서 채팅 내역 가져오기
            query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
            rows = await database.fetch_all(query, values={"chat_id": chat_id})
            
            # 채팅 내역을 chat_histories에 저장
            self.chat_histories[chat_id] = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
            print(f"[기존 채팅 불러오기] chat_id: {chat_id}, history: {self.chat_histories[chat_id]}")

            # 클라이언트에 기존 대화 내역 전송
            try:
                for entry in self.chat_histories[chat_id]:
                    await websocket.send_json(entry)
            except WebSocketDisconnect:
                # 연결이 끊어지면 해당 WebSocket 연결을 해제
                print(f"[WebSocket 연결 끊김] member_num: {member_num}, book_id: {book_id}")
                self.disconnect(websocket, chat_id)

        return chat_id

    # 채팅 내역을 데이터베이스에서 로드 (connect 함수 내에서 호출)
    async def load_chat_history(self, chat_id: int) -> List[dict]:
        query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
        rows = await database.fetch_all(query, values={"chat_id": chat_id})
        history = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
        print(f"[채팅 내역 불러오기] chat_id: {chat_id}, history: {history}")
        return history

    # WebSocket 연결 해제 및 대화 내역 삭제 방지
    def disconnect(self, websocket: WebSocket, chat_id: int):
        self.active_connections.remove(websocket)
        print(f"[WebSocket 연결 해제] chat_id: {chat_id}")
        # chat_histories는 삭제하지 않아 대화 내역을 유지

    # 모든 연결된 WebSocket 클라이언트에 메시지 전송
    async def broadcast(self, websocket: WebSocket, message: dict):
        print(f"[메시지 브로드캐스트] message: {message}")
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            # 연결이 끊어진 경우 active_connections에서 제거
            self.active_connections.remove(websocket)

    # member_num과 book_id를 통해 chat_id를 조회 또는 생성
    async def get_or_create_chat_id(self, member_num: int, book_id: int) -> int:
        if book_id == 0:
            print("[일회성 채팅] book_id가 0이므로 chat_id를 생성하지 않습니다.")
            return 0  # 임시로 일회성 채팅임을 나타내기 위해 0 반환
        
        # 기존의 chat_id 조회
        query = "SELECT chat_id FROM chatbot WHERE member_num = :member_num AND book_id = :book_id"
        result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})

        if result:
            print(f"[기존 chat_id 확인] chat_id: {result['chat_id']}")
            return result["chat_id"]
        
        # chat_id가 없는 경우 새로운 chat_id 생성
        create_query = """
        INSERT INTO chatbot (book_id, member_num) 
        VALUES (:book_id, :member_num) 
        ON CONFLICT DO NOTHING 
        RETURNING chat_id
        """
        chat_id = await database.execute(create_query, values={"book_id": book_id, "member_num": member_num})

        # 중복 데이터로 인해 chat_id가 생성되지 않았을 경우 조회
        if chat_id is None:
            result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})
            if result:
                print(f"[중복 데이터로 인해 기존 chat_id 반환] chat_id: {result['chat_id']}")
                return result["chat_id"]
            else:
                raise ValueError("chat_id 생성 또는 조회에 실패했습니다.")
        
        print(f"[새로운 chat_id 생성] chat_id: {chat_id}")
        return chat_id


# ConnectionManager 및 Chat 모델 초기화
manager = ConnectionManager()
chat_model = ChatOpenAI(api_key=openai_api_key, model="gpt-4o-mini")

# 프롬프트 템플릿 설정
prompt_template = """
You are a knowledgeable and engaging book expert. Your goal is to assist the user with detailed insights and thoughtful questions related to their book discussion. Respond naturally, in Hangul, using polite and friendly language to create a welcoming conversation.

Follow these guidelines:
- Provide information about the book’s themes, plot, and characters, or any specific aspects the user asks about.
- Offer interpretations, analysis, or context when relevant, and connect the book's elements to broader topics when possible.
- Ask follow-up questions that encourage the user to share more of their thoughts or to dive deeper into the book’s themes and ideas.
- Use simple, clear language that suits a conversational setting, and keep responses concise yet informative.
- If the user shifts the topic away from the book, gently guide the conversation back to the book with phrases like, "책에 대해 좀 더 이야기를 나눠볼까요?" or "이 책과 관련해서도 흥미로운 이야기가 많습니다."

Example format:
[User’s question or topic]
1. Provide an insightful response.
2. Encourage engagement with a follow-up question.

Respond only in Hangul.

대화 기록:
{chat_history}

사용자: {user_message}
book expert:
"""


# 채팅 리스트 엔드포인트
@app.get("/chat-list/{member_num}")
async def get_chat_rooms(member_num: int):
    query = """
    SELECT cb.book_id, b.book_title
    FROM chatbot cb
    JOIN book b ON cb.book_id = b.book_id
    WHERE cb.member_num = :member_num
    """
    rows = await database.fetch_all(query, values={"member_num": member_num})
    chat_rooms = [{"book_id": row["book_id"], "book_title": row["book_title"]} for row in rows]
    return chat_rooms

# WebSocket 엔드포인트 - 채팅
@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket, member_num: int, book_id: int = 0):
    print(f"[WebSocket 요청 수신] member_num: {member_num}, book_id: {book_id}")
    
    if book_id == 0:
        await websocket.accept()
        chat_id = 0
        print(f"[일회성 채팅] member_num: {member_num}, book_id: {book_id}, chat_id: {chat_id}")
    else:
        chat_id = await manager.connect(websocket, member_num, book_id)
        print(f"[지속적 채팅] member_num: {member_num}, book_id: {book_id}, chat_id: {chat_id}")

    try:
        while True:
            data = await websocket.receive_json()
            print(f"[메시지 수신] data: {data}")
            if not data.get("message", "").strip():
                continue

            user_message = data["message"]

            # 다양한 요청 감지 (정규 표현식 사용)
            if re.search(r"(이\s*책\s*설명해줘|책\s*(에\s*(대해|관해|관한)?\s*)?(내용|설명|소개|이야기|알려줘|알려\s*줄래|어떤\s*(책|내용)|무엇|뭐야|해줘|얘기해줘|알고\s*싶어|얘기해볼까|뭘까|설명해줘|얘기할\s*수\s*있어|알려줄래|얘기해\s*줄\s*수\s*있어|어떤\s*내용이야|어떤\s*내용|어떤\s*내용인지|어떤\s*내용일까|내용을\s*알려줘|설명을\s*알려줘))", user_message, re.IGNORECASE):
                if book_id != 0:
                    # 책 제목만 가져와서 GPT 모델로 설명 생성
                    book_title_query = "SELECT book_title FROM book WHERE book_id = :book_id"
                    book_title = await database.fetch_one(book_title_query, values={"book_id": book_id})

                    if book_title:
                        title_text = book_title['book_title']
                        prompt_message = f"{title_text}라는 책에 대해 설명해줘."
                        response = await chat_model.agenerate([prompt_message])
                        bot_message_content = response.generations[0][0].text.strip()
                    else:
                        bot_message_content = "죄송합니다, 해당 책에 대한 정보를 찾을 수 없습니다."
                else:
                    # 일반 요청 처리 (책 ID가 없는 경우)
                    response = await chat_model.agenerate([user_message])
                    bot_message_content = response.generations[0][0].text.strip()

                stella_message = {"sender_id": "stella", "message": bot_message_content}
                
                # 데이터베이스 저장 조건
                if chat_id != 0:
                    manager.chat_histories[chat_id].append(data)
                    manager.chat_histories[chat_id].append(stella_message)

                    save_query = "INSERT INTO chating_content (chat_id, chat_content, sender_id) VALUES (:chat_id, :chat_content, :sender_id)"
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": user_message, "sender_id": "user"})
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": bot_message_content, "sender_id": "stella"})
                
                # 클라이언트로 Stella의 응답 전송
                await websocket.send_json(stella_message)
            else:
                # 일반 메시지 처리
                chat_history = "\n".join([entry["message"] for entry in manager.chat_histories.get(chat_id, [])])
                prompt = PromptTemplate(input_variables=["chat_history", "user_message"], template=prompt_template)
                formatted_prompt = prompt.format(chat_history=chat_history, user_message=user_message)
                
                response = await chat_model.agenerate([formatted_prompt])
                bot_message_content = response.generations[0][0].text.strip()

                user_message = {"sender_id": "user", "message": user_message}
                stella_message = {"sender_id": "stella", "message": bot_message_content}
                
                if chat_id != 0:
                    manager.chat_histories[chat_id].append(user_message)
                    manager.chat_histories[chat_id].append(stella_message)
                    
                    # 데이터베이스에 메시지 저장
                    save_query = "INSERT INTO chating_content (chat_id, chat_content, sender_id) VALUES (:chat_id, :chat_content, :sender_id)"
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": user_message["message"], "sender_id": "user"})
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": bot_message_content, "sender_id": "stella"})

                # 클라이언트로 메시지 전송
                await manager.broadcast(websocket, stella_message)
    except WebSocketDisconnect:
        print(f"[WebSocket 연결 끊김] chat_id: {chat_id}, member_num: {member_num}, book_id: {book_id}")
        if book_id != 0:
            manager.disconnect(websocket, chat_id)


# HTTP 엔드포인트 - 채팅 내역 가져오기
@app.get("/chat/{book_id}/{member_num}")
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

@app.get("/")
async def root():
    return {"message": "Chatbot server is running"}


# 데이터베이스 연결 관리
@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
