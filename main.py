"""Ponto de entrada do agente, com dois modos de execucao.

  python -m src.main open   -> na ABERTURA do mercado: analisa, seleciona as
                               melhores oportunidades do dia e as coloca em
                               acompanhamento (registra o preco de entrada).

  python -m src.main close  -> no FECHAMENTO do mercado: pega as indicacoes
                               em acompanhamento e mostra a evolucao em %
                               (valorizou / desvalorizou), tanto no dia quanto
                               desde a indicacao. Encerra as que passaram do
                               prazo e guarda tudo no historico.

Assim voce acompanha cada indicacao por alguns dias e avalia se e rentavel.
"""
import sys
from datetime import datetime, timezone

import config
import storage
from analyzer import analyze, evaluate_exit
from data_fetcher import fetch_history, fetch_last_price, load_tickers
from telegram_notifier import (
    build_alert_message,
    build_close_message,
    build_open_message,
    build_weekly_message,
    send_message,
)


def _now_ref() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def run_open() -> int:
    print("== Abertura: buscando oportunidades ==")
    tickers = load_tickers(config.TICKERS_FILE)
    print(f"Analisando {len(tickers)} ativos...")

    signals = []
    for t in tickers:
        df = fetch_history(t, config.HISTORY_PERIOD, config.DATA_INTERVAL)
        sig = analyze(t, df)
        if sig is None:
            continue
        signals.append(sig)

    signals.sort(key=lambda s: s.score, reverse=True)
    selecionados = [s for s in signals if s.score >= config.MIN_SCORE][: config.TOP_N]

    picks = [
        {
            "ticker": s.ticker,
            "price": s.price,
            "score": s.score,
            "rating": s.rating,
            "stop": s.stop_sugerido,
            "target": s.alvo_sugerido,
            "rsi": s.rsi,
            "trend": s.trend,
        }
        for s in selecionados
    ]

    portfolio = storage.load_portfolio()
    today = storage.today_str()
    # Novo pregao: zera os alertas intradiarios ja enviados das posicoes antigas
    for pos in portfolio.get("positions", []):
        pos["alerts_sent"] = []
    novas = storage.add_positions(portfolio, picks, today)
    storage.save_portfolio(portfolio)

    em_acompanhamento = len(portfolio.get("positions", []))
    print(f"Novas indicacoes: {len(novas)} | Total em acompanhamento: {em_acompanhamento}")

    message = build_open_message(picks, novas, em_acompanhamento, _now_ref())
    _report_and_send(message)
    return 0


def run_close() -> int:
    print("== Fechamento: avaliando evolucao das indicacoes ==")
    portfolio = storage.load_portfolio()
    posicoes = portfolio.get("positions", [])
    today = storage.today_str()

    if not posicoes:
        message = build_close_message([], [], {}, _now_ref())
        _report_and_send(message)
        return 0

    resultados = []
    history_rows = []
    encerradas = []

    for pos in posicoes:
        df = fetch_history(pos["ticker"], config.HISTORY_PERIOD, config.DATA_INTERVAL)
        if df.empty:
            continue
        price = float(df["Close"].iloc[-1])
        open_today = float(df["Open"].iloc[-1])
        entry = float(pos["entry_price"])
        pct_total = (price / entry - 1) * 100 if entry else 0.0
        pct_dia = (price / open_today - 1) * 100 if open_today else 0.0
        dias = storage.days_since(pos["date_indicated"], today)

        # Analisa a hora certa de vender / sair da operacao
        decisao = evaluate_exit(
            df, entry, float(pos.get("stop", 0) or 0), float(pos.get("target", 0) or 0)
        )
        # Encerra se bateu stop/alvo/reversao OU se passou do prazo de acompanhamento
        vai_encerrar = decisao.encerrar or dias >= config.HOLD_DAYS
        if not decisao.encerrar and dias >= config.HOLD_DAYS:
            decisao_label = decisao.label + "  (prazo de acompanhamento encerrado)"
        else:
            decisao_label = decisao.label

        # Se a decisao for proteger lucro, atualiza o stop na posicao
        if decisao.action == "PROTEGER" and decisao.trailing_stop:
            pos["stop"] = decisao.trailing_stop

        item = {
            "ticker": pos["ticker"],
            "date_indicated": pos["date_indicated"],
            "dias": dias,
            "entry_price": round(entry, 2),
            "price": round(price, 2),
            "pct_total": round(pct_total, 2),
            "pct_dia": round(pct_dia, 2),
            "rating": pos.get("rating", ""),
            "score": pos.get("score", ""),
            "encerrada": vai_encerrar,
            "acao": decisao.action,
            "acao_label": decisao_label,
            "acao_motivos": decisao.reasons,
        }
        resultados.append(item)
        history_rows.append(
            {
                "snapshot_date": today,
                "ticker": pos["ticker"],
                "date_indicated": pos["date_indicated"],
                "dias": dias,
                "entry_price": round(entry, 2),
                "price": round(price, 2),
                "pct_total": round(pct_total, 2),
                "pct_dia": round(pct_dia, 2),
                "status": ("ENCERRADA:" + decisao.action) if vai_encerrar else "ABERTA",
            }
        )
        if vai_encerrar:
            encerradas.append(pos)

    storage.append_history(history_rows)
    storage.archive_and_prune(portfolio, encerradas)
    storage.save_portfolio(portfolio)

    resultados.sort(key=lambda r: r["pct_total"], reverse=True)
    resumo = _resumo(resultados)

    message = build_close_message(resultados, encerradas, resumo, _now_ref())
    _report_and_send(message)
    return 0


def _resumo(resultados) -> dict:
    if not resultados:
        return {}
    n = len(resultados)
    positivos = sum(1 for r in resultados if r["pct_total"] > 0)
    media = sum(r["pct_total"] for r in resultados) / n
    melhor = max(resultados, key=lambda r: r["pct_total"])
    pior = min(resultados, key=lambda r: r["pct_total"])
    return {
        "total": n,
        "positivos": positivos,
        "win_rate": round(100 * positivos / n, 1),
        "media": round(media, 2),
        "melhor": melhor,
        "pior": pior,
    }


def _report_and_send(message: str) -> None:
    print("\n--- Mensagem ---")
    print(message)
    print("----------------\n")
    enviado = send_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, message)
    if not enviado:
        print("[aviso] mensagem nao enviada ao Telegram (verifique os segredos).")


def run_watch() -> int:
    """Monitoramento intradiario: alerta quando um ativo bate o stop ou o alvo.

    Pensado para rodar varias vezes durante o pregao. So envia mensagem quando
    ha um disparo novo (nao repete o mesmo alerta no mesmo dia).
    """
    print("== Intradiario: checando stop/alvo ==")
    portfolio = storage.load_portfolio()
    posicoes = portfolio.get("positions", [])
    if not posicoes:
        print("Nenhuma posicao para monitorar.")
        return 0

    alerts = []
    for pos in posicoes:
        price = fetch_last_price(pos["ticker"])
        if price is None:
            continue
        entry = float(pos.get("entry_price", 0) or 0)
        stop = float(pos.get("stop", 0) or 0)
        target = float(pos.get("target", 0) or 0)
        pct = (price / entry - 1) * 100 if entry else 0.0
        enviados = set(pos.get("alerts_sent", []))

        if target and price >= target and "ALVO" not in enviados:
            alerts.append({"ticker": pos["ticker"], "tipo": "ALVO", "price": price,
                           "level": target, "entry": entry, "pct": pct})
            enviados.add("ALVO")
        elif stop and price <= stop and "STOP" not in enviados:
            alerts.append({"ticker": pos["ticker"], "tipo": "STOP", "price": price,
                           "level": stop, "entry": entry, "pct": pct})
            enviados.add("STOP")

        pos["alerts_sent"] = sorted(enviados)

    storage.save_portfolio(portfolio)

    if not alerts:
        print("Sem disparos de stop/alvo neste momento.")
        return 0

    print(f"{len(alerts)} alerta(s) disparado(s).")
    message = build_alert_message(alerts, _now_ref())
    _report_and_send(message)
    return 0


def run_weekly() -> int:
    """Relatorio semanal consolidado de desempenho (ultimos 7 dias).

    Consolida as operacoes ENCERRADAS na semana (resultado realizado) e as
    que seguem ABERTAS (resultado em aberto), com estatisticas agregadas.
    """
    print("== Semanal: consolidando desempenho ==")
    today = storage.today_str()
    history = storage.read_history()

    # Operacoes encerradas na semana (uma linha por operacao, status ENCERRADA:*)
    encerradas = []
    for r in history:
        status = (r.get("status") or "")
        if status.startswith("ENCERRADA") and storage.within_last_days(
            r.get("snapshot_date", ""), today, 7
        ):
            motivo = status.split(":", 1)[1] if ":" in status else "PRAZO"
            encerradas.append(
                {
                    "ticker": r.get("ticker", ""),
                    "pct_total": float(r.get("pct_total") or 0),
                    "dias": r.get("dias", ""),
                    "motivo": motivo,
                    "snapshot_date": r.get("snapshot_date", ""),
                }
            )

    # Operacoes ainda abertas: ultimo snapshot de cada posicao do portfolio
    portfolio = storage.load_portfolio()
    abertos_tickers = {
        (p["ticker"], p["date_indicated"]) for p in portfolio.get("positions", [])
    }
    ultimo_por_pos = {}
    for r in history:
        key = (r.get("ticker", ""), r.get("date_indicated", ""))
        if key in abertos_tickers:
            ultimo_por_pos[key] = r
    abertas = [
        {
            "ticker": r.get("ticker", ""),
            "pct_total": float(r.get("pct_total") or 0),
            "dias": r.get("dias", ""),
        }
        for r in ultimo_por_pos.values()
    ]

    resumo = _resumo_semanal(encerradas)
    message = build_weekly_message(encerradas, abertas, resumo, _now_ref())
    _report_and_send(message)
    return 0


def _resumo_semanal(encerradas) -> dict:
    if not encerradas:
        return {}
    n = len(encerradas)
    vencedoras = sum(1 for e in encerradas if e["pct_total"] > 0)
    soma = sum(e["pct_total"] for e in encerradas)
    media = soma / n
    melhor = max(encerradas, key=lambda e: e["pct_total"])
    pior = min(encerradas, key=lambda e: e["pct_total"])
    por_motivo: dict = {}
    for e in encerradas:
        por_motivo[e["motivo"]] = por_motivo.get(e["motivo"], 0) + 1
    return {
        "total": n,
        "vencedoras": vencedoras,
        "win_rate": round(100 * vencedoras / n, 1),
        "media": round(media, 2),
        "soma": round(soma, 2),
        "melhor": melhor,
        "pior": pior,
        "por_motivo": por_motivo,
    }


def run() -> int:
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "open"
    if mode == "close":
        return run_close()
    if mode == "watch":
        return run_watch()
    if mode == "weekly":
        return run_weekly()
    return run_open()


if __name__ == "__main__":
    sys.exit(run())
