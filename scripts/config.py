"""
config.py — Machine-specific settings for nutanix_rag_search.py
Copy this file alongside nutanix_rag_search.py on each machine.
Keep this file PRIVATE — it contains API keys.
"""
from pathlib import Path

# ── LanceDB ──────────────────────────────────────────────────────────────────
DB_PATH = Path("/Users/ipccheng/.openclaw/memory/lancedb-pro")

# ── Jina AI (embeddings + reranker) ──────────────────────────────────────────
JINA_API_KEY = "jina_277850c64424480882ff80d08eddb1a1kOssRCm4jHMUlrGt06mnmQG62EdT"
JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"
JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"

# ── Topic Classifier ────────────────────────────────────────────────────────
# Options: "gemma" (local LM Studio on MacBook) or "deepseek" (cloud API)
CLASSIFIER_MODEL = "deepseek"  # Set to "gemma" if MacBook is available

# Gemma 4 31B (local — via LM Studio on MacBook)
GEMMA_URL = "http://100.74.228.94:1234/v1/chat/completions"
GEMMA_MODEL = "gemma4"
GEMMA_TIMEOUT = 3  # seconds — fail fast to keyword fallback

# DeepSeek (cloud — fast, cheap, follows instructions well)
DEEPSEEK_API_KEY = "sk-0e3a6d6f8e4d4b9aa0c8d4e6f8a4b2c1d3e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9"  # placeholder — set in env if needed
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TIMEOUT = 10  # seconds
