import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
load_dotenv()

def get_groq():
    """Initialize Groq LLM client (FREE: 14,400 req/day, ultra-fast)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment")
    
    model_name = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    
    # 163-field chunk generation still needs a large completion budget.
    # Keep this at provider-safe upper bound and allow .env override.
    max_tokens = int(os.getenv("GROQ_MAX_TOKENS", "8192"))
    
    return ChatOpenAI(
        model=model_name,
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
        temperature=0,
        max_tokens=max_tokens,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
