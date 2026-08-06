"""RAG Forge configuration — reads from environment and .env file."""

import os
from dataclasses import dataclass, field

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Config:
    embedding_provider: str = "local"  # local | lmstudio | siliconflow | openai
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_endpoint: str = "https://api.siliconflow.cn/v1/embeddings"
    embedding_api_key: str = ""
    llm_provider: str = "deepseek"  # deepseek | lmstudio
    llm_model: str = "deepseek-chat"
    llm_endpoint: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    reranker_model: str = "BAAI/bge-reranker-base"

    @classmethod
    def from_env(cls) -> "Config":
        provider = os.getenv("RAGFORGE_EMBED_PROVIDER", "local")
        # LM Studio defaults
        if provider == "lmstudio":
            return cls(
                embedding_provider="lmstudio",
                embedding_endpoint="http://localhost:1234/v1/embeddings",
                embedding_model="text-embedding-nomic-embed-text-v1.5",
                embedding_api_key="lm-studio",
                llm_provider=os.getenv("RAGFORGE_LLM_PROVIDER", "lmstudio"),
                llm_endpoint=os.getenv("RAGFORGE_LLM_ENDPOINT", "http://localhost:1234/v1"),
                llm_model=os.getenv("RAGFORGE_LLM_MODEL", "qwen3.6-35b-a3b"),
                llm_api_key="lm-studio",
            )
        return cls(
            embedding_provider=provider,
            embedding_model=os.getenv("RAGFORGE_EMBED_MODEL", "BAAI/bge-small-zh-v1.5"),
            embedding_endpoint=os.getenv("RAGFORGE_EMBED_ENDPOINT", "https://api.siliconflow.cn/v1/embeddings"),
            embedding_api_key=os.getenv("RAGFORGE_EMBED_API_KEY", os.getenv("SILICONFLOW_API_KEY", "")),
            llm_provider=os.getenv("RAGFORGE_LLM_PROVIDER", "deepseek"),
            llm_model=os.getenv("RAGFORGE_LLM_MODEL", "deepseek-chat"),
            llm_endpoint=os.getenv("RAGFORGE_LLM_ENDPOINT", "https://api.deepseek.com/v1"),
            llm_api_key=os.getenv("RAGFORGE_LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")),
            reranker_model=os.getenv("RAGFORGE_RERANKER_MODEL", "BAAI/bge-reranker-base"),
        )


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
