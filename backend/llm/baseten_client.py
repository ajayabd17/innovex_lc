import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_baseten():
    """Initialize Baseten OpenAI-compatible client for generation."""
    api_key = os.getenv("BASETEN_API_KEY")
    if not api_key:
        raise ValueError("BASETEN_API_KEY not set in environment")

    model_name = os.getenv("BASETEN_MODEL", "openai/gpt-oss-120b")
    max_tokens = int(os.getenv("BASETEN_MAX_TOKENS", "16384"))

    return ChatOpenAI(
        model=model_name,
        base_url="https://inference.baseten.co/v1",
        api_key=api_key,
        temperature=0,
        max_tokens=max_tokens,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
