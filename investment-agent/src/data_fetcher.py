"""Coleta de dados de mercado via yfinance."""
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf


def load_tickers(tickers_file: str) -> List[str]:
    """Le a watchlist, ignorando comentarios e linhas vazias."""
    path = Path(tickers_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / tickers_file
    tickers = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tickers.append(line.upper())
    # remove duplicados preservando ordem
    seen = set()
    unique = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def fetch_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Baixa o historico OHLCV de um ticker. Retorna DataFrame vazio em caso de falha."""
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        # yfinance pode retornar colunas MultiIndex quando ha 1 ticker
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        return df
    except Exception as exc:  # pragma: no cover
        print(f"[aviso] falha ao baixar {ticker}: {exc}")
        return pd.DataFrame()


def fetch_last_price(ticker: str):
    """Retorna o ultimo preco (quase em tempo real) para alertas intradiarios.

    Tenta, em ordem: fast_info -> candles de 1 minuto do dia -> ultimo fechamento.
    Retorna float ou None.
    """
    try:
        tk = yf.Ticker(ticker)
        try:
            price = float(tk.fast_info["last_price"])
            if price and price > 0:
                return price
        except Exception:
            pass

        intraday = tk.history(period="1d", interval="1m", auto_adjust=True)
        if intraday is not None and not intraday.empty:
            return float(intraday["Close"].dropna().iloc[-1])

        daily = tk.history(period="5d", interval="1d", auto_adjust=True)
        if daily is not None and not daily.empty:
            return float(daily["Close"].dropna().iloc[-1])
    except Exception as exc:  # pragma: no cover
        print(f"[aviso] falha ao obter ultimo preco de {ticker}: {exc}")
    return None
