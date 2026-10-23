"""Configuracoes centrais do agente.

Le variaveis de ambiente (localmente via .env, no GitHub via Secrets).
"""
import os

# Tenta carregar .env em execucao local (opcional; nao quebra se nao existir)
try:
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
except Exception:
    pass

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# --- Parametros da analise ---
MIN_SCORE = int(os.getenv("MIN_SCORE", "60"))

# Periodo de historico baixado e intervalo das velas
HISTORY_PERIOD = os.getenv("HISTORY_PERIOD", "1y")   # ex: 6mo, 1y, 2y
DATA_INTERVAL = os.getenv("DATA_INTERVAL", "1d")      # 1d = diario

# Arquivo com a watchlist
TICKERS_FILE = os.getenv("TICKERS_FILE", "tickers.txt")

# Quantos ativos no topo do ranking enviar
TOP_N = int(os.getenv("TOP_N", "10"))

# Por quantos dias (corridos) uma indicacao fica em acompanhamento antes de
# ser encerrada automaticamente e arquivada no historico.
HOLD_DAYS = int(os.getenv("HOLD_DAYS", "7"))
