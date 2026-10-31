import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # hireguard/
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("HG_DB_PATH", ROOT / "backend" / "hireguard.db"))
UPLOAD_DIR = Path(os.getenv("HG_UPLOAD_DIR", ROOT / "backend" / "uploads"))

OLLAMA_URLS = [u.strip() for u in os.getenv("HG_OLLAMA_URLS", "http://localhost:11434").split(",") if u.strip()]
OLLAMA_MODEL = os.getenv("HG_OLLAMA_MODEL", "qwen3:8b")
# Groq fallback: fictional data only, OFF by default
GROQ_FALLBACK = os.getenv("HG_GROQ_FALLBACK", "0") == "1"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("HG_GROQ_MODEL", "qwen/qwen3-32b")

PROMPT_GUARD = os.getenv("HG_PROMPT_GUARD", "0") == "1"

SESSION_TTL_MIN = int(os.getenv("HG_SESSION_TTL_MIN", "480"))          # absolute session lifetime
SESSION_IDLE_MIN = int(os.getenv("HG_SESSION_IDLE_MIN", "30"))         # signed out after this much inactivity
LOGIN_IP_MAX_FAILED = int(os.getenv("HG_LOGIN_IP_MAX_FAILED", "20"))   # per IP per 15 min (call centers share NAT)
API_DOCS = os.getenv("HG_API_DOCS", "1") == "1"                        # Swagger UI: set 0 in production
# Reverse proxies allowed to set X-Forwarded-For (IPs or CIDRs, comma-separated). Empty = trust no header.
TRUSTED_PROXIES = [x.strip() for x in os.getenv("HG_TRUSTED_PROXIES", "").split(",") if x.strip()]
COOKIE_SECURE = os.getenv("HG_COOKIE_SECURE", "0") == "1"
CORS_ORIGINS = [o.strip() for o in os.getenv("HG_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

MAX_UPLOAD_BYTES = int(os.getenv("HG_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_PDF_PAGES = int(os.getenv("HG_MAX_PDF_PAGES", "6"))

CANARY_EVERY = int(os.getenv("HG_CANARY_EVERY", "20"))
