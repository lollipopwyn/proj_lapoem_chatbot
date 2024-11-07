from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import os

chat_model = ChatOpenAI(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")

def create_prompt(chat_history: str, user_message: str, max_lines: int = 5) -> str:
    # `chat_history`를 줄 단위로 분할한 다음, 최신 `max_lines` 줄만 남김
    history_lines = chat_history.strip().split("\n")
    recent_history = "\n".join(history_lines[-max_lines:])

    prompt_template = """
    You are a book expert with extensive knowledge of various books, including their themes, characters, plot structures, and historical contexts. Engage in an in-depth conversation with the user about the book they mention, providing insights, context, and interpretations. Encourage follow-up questions and offer related book suggestions if relevant. Answer in hangul.

    대화 기록:
    {chat_history}

    사용자: {user_message}
    book expert:
    """

    prompt = PromptTemplate(input_variables=["chat_history", "user_message"], template=prompt_template)
    return prompt.format(chat_history=recent_history, user_message=user_message)
