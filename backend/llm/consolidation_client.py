import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()


def get_consolidation_client():
    """Initialize consolidation LLM (4th model) via GitHub Models."""
    provider = (os.getenv("CONSOLIDATION_PROVIDER", "github") or "github").strip().lower()
    if provider != "github":
        raise ValueError(f"Unsupported CONSOLIDATION_PROVIDER='{provider}'. Supported: github")

    api_key = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_MODELS_API_KEY")
    if not api_key:
        raise ValueError("GITHUB_TOKEN (or GITHUB_MODELS_API_KEY) not set in environment")

    # GitHub Models naming style uses provider-prefixed model ids like openai/gpt-4o.
    model_name = os.getenv("GITHUB_MODEL") or os.getenv("CONSOLIDATION_MODEL", "openai/gpt-4o")
    max_tokens = int(os.getenv("CONSOLIDATION_MAX_TOKENS", "16384"))

    return ChatOpenAI(
        model=model_name,
        base_url="https://models.github.ai/inference",
        api_key=api_key,
        temperature=0,
        max_tokens=max_tokens,
    )
