import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_fireworks():
    """Initialize Fireworks LLM client for generation."""
    api_key = os.getenv("FIREWORKS_API_KEY")
    if not api_key:
        raise ValueError("FIREWORKS_API_KEY not set in environment")

    model_name = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/minimax-m2p5")
    max_tokens = int(os.getenv("FIREWORKS_MAX_TOKENS", "24576"))

    return ChatOpenAI(
        model=model_name,
        base_url="https://api.fireworks.ai/inference/v1",
        api_key=api_key,
        temperature=0,
        max_tokens=max_tokens,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

