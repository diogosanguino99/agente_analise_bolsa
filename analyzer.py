"""Motor de analise: calcula indicadores e gera um score de oportunidade.

A estrategia usa CONFLUENCIA de sinais (tendencia + momentum + volume + rompimento).
O score vai de 0 a 100. Quanto maior, mais sinais de alta alinhados.

IMPORTANTE: isto e uma ferramenta de apoio. Nao e recomendacao de investimento.
"""
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

import indicators as ind


@dataclass
class Signal:
    ticker: str
    price: float
    score: int
    rating: str
    reasons: List[str] = field(default_factory=list)
    rsi: float = 0.0
    trend: str = ""
    stop_sugerido: float = 0.0
    alvo_sugerido: float = 0.0
    var_pct_dia: float = 0.0


def _rating_from_score(score: int) -> str:
    if score >= 80:
        return "FORTE"
    if score >= 65:
        return "BOA"
    if score >= 50:
        return "NEUTRA"
    return "FRACA"


def analyze(ticker: str, df: pd.DataFrame) -> Optional[Signal]:
    """Analisa um ativo e retorna um Signal (ou None se dados insuficientes)."""
    if df.empty or len(df) < 60:
        return None

    close = df["Close"]
    volume = df["Volume"]

    sma20 = ind.sma(close, 20)
    sma50 = ind.sma(close, 50)
    sma200 = ind.sma(close, 200) if len(df) >= 200 else None
    ema9 = ind.ema(close, 9)
    ema21 = ind.ema(close, 21)
    rsi14 = ind.rsi(close, 14)
    macd_line, signal_line, hist = ind.macd(close)
    atr14 = ind.atr(df, 14)

    price = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else price
    var_dia = (price / prev - 1) * 100 if prev else 0.0

    score = 0
    reasons: List[str] = []

    # 1) Tendencia de medio prazo (preco acima das medias)
    if price > float(sma20.iloc[-1]):
        score += 12
        reasons.append("Preco acima da media de 20 periodos (tendencia curta positiva)")
    if price > float(sma50.iloc[-1]):
        score += 12
        reasons.append("Preco acima da media de 50 periodos (tendencia media positiva)")
    if sma200 is not None and not pd.isna(sma200.iloc[-1]) and price > float(sma200.iloc[-1]):
        score += 10
        reasons.append("Preco acima da media de 200 (tendencia primaria de alta)")

    # 2) Cruzamento de medias curtas (gatilho de momentum)
    if float(ema9.iloc[-1]) > float(ema21.iloc[-1]):
        score += 10
        reasons.append("EMA9 acima da EMA21 (momentum de curto prazo positivo)")
        if float(ema9.iloc[-2]) <= float(ema21.iloc[-2]):
            score += 8
            reasons.append("Cruzamento recente de alta das EMAs (gatilho fresco)")

    # 3) RSI em zona saudavel (nem sobrecomprado extremo, nem fraco)
    rsi_val = float(rsi14.iloc[-1])
    if 50 <= rsi_val <= 68:
        score += 12
        reasons.append(f"RSI em {rsi_val:.0f} (forca compradora saudavel)")
    elif 40 <= rsi_val < 50:
        score += 5
        reasons.append(f"RSI em {rsi_val:.0f} (recuperando)")
    elif rsi_val > 72:
        reasons.append(f"RSI em {rsi_val:.0f} (sobrecomprado - cautela)")

    # 4) MACD acima da linha de sinal e histograma subindo
    if float(macd_line.iloc[-1]) > float(signal_line.iloc[-1]):
        score += 10
        reasons.append("MACD acima da linha de sinal (momentum confirmado)")
    if float(hist.iloc[-1]) > float(hist.iloc[-2]):
        score += 5
        reasons.append("Histograma do MACD em aceleracao")

    # 5) Volume acima da media (interesse comprador)
    vol_med = float(volume.tail(20).mean())
    if vol_med > 0 and float(volume.iloc[-1]) > 1.2 * vol_med:
        score += 8
        reasons.append("Volume acima da media de 20 dias (confirmacao)")

    # 6) Rompimento de maxima recente (20 dias)
    rolling_high = float(close.tail(21).iloc[:-1].max())
    if price >= rolling_high:
        score += 8
        reasons.append("Rompimento da maxima dos ultimos 20 periodos")

    score = max(0, min(100, score))

    atr_val = float(atr14.iloc[-1]) if not pd.isna(atr14.iloc[-1]) else price * 0.02
    stop = round(price - 1.5 * atr_val, 2)
    alvo = round(price + 3.0 * atr_val, 2)  # alvo com relacao risco/retorno ~1:2

    if sma200 is not None and not pd.isna(sma200.iloc[-1]):
        trend = "ALTA" if price > float(sma200.iloc[-1]) else "BAIXA"
    else:
        trend = "ALTA" if price > float(sma50.iloc[-1]) else "BAIXA"

    return Signal(
        ticker=ticker,
        price=round(price, 2),
        score=int(score),
        rating=_rating_from_score(score),
        reasons=reasons,
        rsi=round(rsi_val, 1),
        trend=trend,
        stop_sugerido=stop,
        alvo_sugerido=alvo,
        var_pct_dia=round(var_dia, 2),
    )


@dataclass
class ExitDecision:
    action: str          # STOP | ALVO | SAIR | PROTEGER | MANTER
    label: str           # texto amigavel pronto para a mensagem
    reasons: List[str] = field(default_factory=list)
    trailing_stop: float = 0.0   # novo stop sugerido para proteger lucro
    encerrar: bool = False       # True quando a posicao deve ser fechada agora


_EXIT_LABEL = {
    "STOP": "\U0001F6D1 VENDER agora \u2014 stop atingido (corte a perda)",
    "ALVO": "\U0001F3AF VENDER agora \u2014 alvo atingido (realize o lucro)",
    "SAIR": "\u26A0\uFE0F AVALIAR SAIDA \u2014 tendencia enfraquecendo",
    "PROTEGER": "\U0001F512 PROTEGER lucro \u2014 suba o stop",
    "MANTER": "\u2705 MANTER \u2014 tendencia ainda a favor",
}


def evaluate_exit(
    df: pd.DataFrame, entry: float, stop: float, target: float
) -> ExitDecision:
    """Analisa se e hora de vender / sair da operacao.

    Prioridade: stop > alvo > reversao de tendencia > proteger lucro > manter.
    """
    if df.empty or len(df) < 30:
        return ExitDecision("MANTER", _EXIT_LABEL["MANTER"], ["Dados insuficientes para reavaliar"])

    close = df["Close"]
    price = float(close.iloc[-1])
    ema9 = ind.ema(close, 9)
    ema21 = ind.ema(close, 21)
    sma20 = ind.sma(close, 20)
    rsi14 = ind.rsi(close, 14)
    macd_line, signal_line, _ = ind.macd(close)
    atr14 = ind.atr(df, 14)
    atr_val = float(atr14.iloc[-1]) if not pd.isna(atr14.iloc[-1]) else price * 0.02

    lucro = price > entry
    pct = (price / entry - 1) * 100 if entry else 0.0

    # 1) Stop atingido -> sair protegendo capital
    if stop and price <= stop:
        return ExitDecision(
            "STOP",
            _EXIT_LABEL["STOP"],
            [f"Preco ${price:.2f} tocou/rompeu o stop ${stop:.2f} ({pct:+.2f}%)"],
            encerrar=True,
        )

    # 2) Alvo atingido -> realizar lucro
    if target and price >= target:
        return ExitDecision(
            "ALVO",
            _EXIT_LABEL["ALVO"],
            [f"Preco ${price:.2f} alcancou o alvo ${target:.2f} ({pct:+.2f}%)"],
            encerrar=True,
        )

    # 3) Reversao de tendencia (conta sinais contrarios)
    reversao = []
    if float(ema9.iloc[-1]) < float(ema21.iloc[-1]):
        reversao.append("EMA9 cruzou abaixo da EMA21 (momentum virou)")
    if float(macd_line.iloc[-1]) < float(signal_line.iloc[-1]):
        reversao.append("MACD abaixo da linha de sinal")
    if not pd.isna(sma20.iloc[-1]) and price < float(sma20.iloc[-1]):
        reversao.append("Preco perdeu a media de 20 periodos")
    rsi_val = float(rsi14.iloc[-1])
    if rsi_val < 45:
        reversao.append(f"RSI em {rsi_val:.0f} (perdendo forca compradora)")

    if len(reversao) >= 2:
        return ExitDecision("SAIR", _EXIT_LABEL["SAIR"], reversao, encerrar=True)

    # 4) Em lucro mas com 1 sinal de alerta -> proteger (trailing stop)
    novo_stop = round(price - 1.5 * atr_val, 2)
    if lucro and (reversao or pct >= 5):
        trailing = max(float(stop or 0), novo_stop)
        motivo = reversao[0] if reversao else f"Lucro de {pct:+.2f}% \u2014 proteja os ganhos"
        return ExitDecision(
            "PROTEGER",
            _EXIT_LABEL["PROTEGER"],
            [motivo, f"Sugestao: subir o stop para ${trailing:.2f}"],
            trailing_stop=trailing,
        )

    # 5) Caso contrario, segue na operacao
    return ExitDecision(
        "MANTER",
        _EXIT_LABEL["MANTER"],
        [f"Tendencia ainda a favor ({pct:+.2f}% desde a entrada)"],
    )
