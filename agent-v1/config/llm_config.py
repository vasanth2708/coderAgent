import os
from langchain_openai import ChatOpenAI

_llm_instance = None


def get_llm() -> ChatOpenAI:
    """Get or create the shared LLM instance"""
    global _llm_instance
    if _llm_instance is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set")
        _llm_instance = ChatOpenAI(
            model="deepseek-chat",
            temperature=0,
            openai_api_key=api_key,
            openai_api_base="https://api.deepseek.com/v1",
        )
    return _llm_instance


def initialize_llm() -> ChatOpenAI:
    """Initialize LLM at startup - call this once in main.py"""
    return get_llm()

