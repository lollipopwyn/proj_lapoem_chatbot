import os
from langchain_openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# OpenAI API 키 설정 (환경 변수에서 가져오기)
openai_api_key = os.getenv("OPENAI_API_KEY")
langchain_api = OpenAI(model="gpt-4o-mini", openai_api_key=openai_api_key)

def generate_response(question: str) -> str:
    prompt = f"질문: {question}\n답변:"
    response = langchain_api(prompt)
    return response
