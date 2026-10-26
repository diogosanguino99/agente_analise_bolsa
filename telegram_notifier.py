"""Montagem e envio das mensagens para o canal do Telegram."""
from typing import Dict, List

import requests

_EMOJI = {"FORTE": "\U0001F7E2", "BOA": "\U0001F535", "NEUTRA": "\U0001F7E1", "FRACA": "\u26AA"}


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _arrow(pct: float) -> str:
    if pct > 0:
        return "\U0001F4C8"  # grafico subindo
    if pct < 0:
        return "\U0001F4C9"  # grafico caindo
    return "\u27A1\uFE0F"


_DISCLAIMER = (
    "<i>\u26A0\uFE0F Ferramenta de analise tecnica automatizada. "
    "NAO e recomendacao de investimento. Faca sua propria pesquisa e "
    "gerencie o risco.</i>"
)

# Ordem e rotulos das secoes por mercado (com bandeira)
_MARKETS = [
    ("US", "\U0001F1FA\U0001F1F8 A\u00e7\u00f5es EUA"),
    ("BR", "\U0001F1E7\U0001F1F7 A\u00e7\u00f5es Brasil (B3)"),
]


def _market_of(ticker: str) -> str:
    return "BR" if str(ticker).upper().endswith(".SA") else "US"


def _cur(market: str) -> str:
    """Simbolo da moeda conforme o mercado."""
    return "R$" if market == "BR" else "$"


def _group_by_market(items: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = {"US": [], "BR": []}
    for it in items:
        m = it.get("market") or _market_of(it.get("ticker", ""))
        groups.setdefault(m, [])
        groups[m].append(it)
    return groups


def build_open_message(
    picks: List[Dict], novas: List[Dict], em_acompanhamento: int, data_ref: str
) -> str:
    lines = [
        "<b>\U0001F514 ABERTURA \u2014 Oportunidades do dia</b>",
        f"<i>{_escape(data_ref)}</i>",
        "",
    ]
    if not picks:
        lines.append(
            "Nenhuma oportunidade acima do score minimo na abertura de hoje. "
            "Dia de observar."
        )
        lines.append("")
        lines.append(f"Em acompanhamento: <b>{em_acompanhamento}</b> indicacao(oes).")
        lines.append("")
        lines.append(_DISCLAIMER)
        return "\n".join(lines)

    novos_tickers = {n["ticker"] for n in novas}
    groups = _group_by_market(picks)
    for market, label in _MARKETS:
        grupo = groups.get(market) or []
        if not grupo:
            continue
        cur = _cur(market)
        lines.append(f"<b>{label}</b>")
        for i, p in enumerate(grupo, 1):
            dot = _EMOJI.get(p["rating"], "\u26AA")
            tag = " \U0001F195" if p["ticker"] in novos_tickers else " \U0001F501"
            lines.append(
                f"{dot} <b>{i}. {_escape(p['ticker'])}</b>{tag}  "
                f"(score <b>{p['score']}</b> \u00b7 {p['rating']})"
            )
            lines.append(
                f"    Entrada: {cur}{p['price']}  |  RSI: {p.get('rsi','-')}  |  "
                f"Tend.: {p.get('trend','-')}"
            )
            lines.append(
                f"    \U0001F3AF Alvo: {cur}{p['target']}   \U0001F6D1 Stop: {cur}{p['stop']}"
            )
            lines.append("")

    lines.append(
        f"\U0001F195 = nova indicacao  \u00b7  \U0001F501 = ja em acompanhamento"
    )
    lines.append(
        f"Total em acompanhamento: <b>{em_acompanhamento}</b> indicacao(oes)."
    )
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def build_close_message(
    resultados: List[Dict], encerradas: List[Dict], resumo: Dict, data_ref: str
) -> str:
    lines = [
        "<b>\U0001F4CA FECHAMENTO \u2014 Evolucao das indicacoes</b>",
        f"<i>{_escape(data_ref)}</i>",
        "",
    ]
    if not resultados:
        lines.append("Nenhuma indicacao em acompanhamento no momento.")
        lines.append("")
        lines.append(_DISCLAIMER)
        return "\n".join(lines)

    groups = _group_by_market(resultados)
    for market, label in _MARKETS:
        grupo = groups.get(market) or []
        if not grupo:
            continue
        cur = _cur(market)
        lines.append(f"<b>{label}</b>")
        for i, r in enumerate(grupo, 1):
            arrow = _arrow(r["pct_total"])
            lines.append(
                f"{arrow} <b>{i}. {_escape(r['ticker'])}</b>  "
                f"<b>{r['pct_total']:+.2f}%</b> desde a indicacao"
            )
            lines.append(
                f"    Entrada {cur}{r['entry_price']} \u2192 agora {cur}{r['price']}  |  "
                f"dia {r['pct_dia']:+.2f}%  |  ha {r['dias']} dia(s)"
            )
            # Recomendacao de venda / saida
            if r.get("acao_label"):
                lines.append(f"    \U0001F449 {_escape(r['acao_label'])}")
            for motivo in (r.get("acao_motivos") or [])[:2]:
                lines.append(f"       \u2022 {_escape(motivo)}")
            lines.append("")

    if resumo:
        melhor, pior = resumo["melhor"], resumo["pior"]
        lines.append("<b>\u2500\u2500 Resumo do acompanhamento \u2500\u2500</b>")
        lines.append(
            f"Indicacoes: <b>{resumo['total']}</b>  |  "
            f"no positivo: <b>{resumo['positivos']}</b> "
            f"(taxa de acerto {resumo['win_rate']}%)"
        )
        lines.append(f"Retorno medio: <b>{resumo['media']:+.2f}%</b>")
        lines.append(
            f"Melhor: {_escape(melhor['ticker'])} {melhor['pct_total']:+.2f}%  |  "
            f"Pior: {_escape(pior['ticker'])} {pior['pct_total']:+.2f}%"
        )
        lines.append("")

    lines.append(_DISCLAIMER)
    return "\n".join(lines)


_MOTIVO_LABEL = {
    "ALVO": "\U0001F3AF alvo atingido",
    "STOP": "\U0001F6D1 stop atingido",
    "SAIR": "\u26A0\uFE0F reversao de tendencia",
    "PRAZO": "\u23F3 fim do prazo",
    "MANTER": "\u23F3 fim do prazo",
    "PROTEGER": "\u23F3 fim do prazo",
}


def build_weekly_message(
    encerradas: List[Dict], abertas: List[Dict], resumo: Dict, data_ref: str
) -> str:
    lines = [
        "<b>\U0001F4C5 RELATORIO SEMANAL \u2014 Desempenho consolidado</b>",
        f"<i>{_escape(data_ref)} \u00b7 ultimos 7 dias</i>",
        "",
    ]

    if not encerradas and not abertas:
        lines.append("Nenhuma operacao registrada na semana.")
        lines.append("")
        lines.append(_DISCLAIMER)
        return "\n".join(lines)

    if resumo:
        melhor, pior = resumo["melhor"], resumo["pior"]
        soma = resumo["soma"]
        emoji_soma = "\U0001F4C8" if soma >= 0 else "\U0001F4C9"
        lines.append("<b>\u2500\u2500 Operacoes encerradas na semana \u2500\u2500</b>")
        lines.append(
            f"Total: <b>{resumo['total']}</b>  |  vencedoras: <b>{resumo['vencedoras']}</b>  "
            f"(taxa de acerto <b>{resumo['win_rate']}%</b>)"
        )
        lines.append(f"Retorno medio por operacao: <b>{resumo['media']:+.2f}%</b>")
        lines.append(f"{emoji_soma} Resultado acumulado: <b>{soma:+.2f}%</b>")
        lines.append(
            f"Melhor: {_escape(melhor['ticker'])} {melhor['pct_total']:+.2f}%  |  "
            f"Pior: {_escape(pior['ticker'])} {pior['pct_total']:+.2f}%"
        )
        motivos = "  \u00b7  ".join(
            f"{_MOTIVO_LABEL.get(m, m)}: {q}" for m, q in resumo["por_motivo"].items()
        )
        if motivos:
            lines.append(f"Saidas: {motivos}")
        lines.append("")

        lines.append("<b>Detalhe das encerradas:</b>")
        grupos_enc = _group_by_market(encerradas)
        for market, label in _MARKETS:
            grupo = grupos_enc.get(market) or []
            if not grupo:
                continue
            lines.append(f"<i>{label}</i>")
            for e in sorted(grupo, key=lambda x: x["pct_total"], reverse=True):
                arrow = _arrow(e["pct_total"])
                lines.append(
                    f"{arrow} {_escape(e['ticker'])}  <b>{e['pct_total']:+.2f}%</b>  "
                    f"({_MOTIVO_LABEL.get(e['motivo'], e['motivo'])}, {e['dias']}d)"
                )
        lines.append("")
    else:
        lines.append("Nenhuma operacao encerrada nesta semana.")
        lines.append("")

    if abertas:
        em_lucro = sum(1 for a in abertas if a["pct_total"] > 0)
        media_ab = sum(a["pct_total"] for a in abertas) / len(abertas)
        lines.append("<b>\u2500\u2500 Ainda em acompanhamento \u2500\u2500</b>")
        lines.append(
            f"Abertas: <b>{len(abertas)}</b>  |  no lucro: <b>{em_lucro}</b>  |  "
            f"resultado medio atual: <b>{media_ab:+.2f}%</b>"
        )
        grupos_ab = _group_by_market(abertas)
        for market, label in _MARKETS:
            grupo = grupos_ab.get(market) or []
            if not grupo:
                continue
            lines.append(f"<i>{label}</i>")
            for a in sorted(grupo, key=lambda x: x["pct_total"], reverse=True):
                arrow = _arrow(a["pct_total"])
                lines.append(
                    f"{arrow} {_escape(a['ticker'])}  <b>{a['pct_total']:+.2f}%</b>  "
                    f"({a['dias']}d)"
                )
        lines.append("")

    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def build_alert_message(alerts: List[Dict], data_ref: str) -> str:
    """Mensagem de alerta intradiario quando um ativo bate o stop ou o alvo."""
    lines = [
        "<b>\U0001F6A8 ALERTA INTRADIARIO</b>",
        f"<i>{_escape(data_ref)}</i>",
        "",
    ]
    groups = _group_by_market(alerts)
    for market, label in _MARKETS:
        grupo = groups.get(market) or []
        if not grupo:
            continue
        cur = _cur(market)
        lines.append(f"<b>{label}</b>")
        for a in grupo:
            if a["tipo"] == "ALVO":
                head = f"\U0001F3AF <b>{_escape(a['ticker'])}</b> bateu o ALVO \u2014 realize o lucro"
            else:
                head = f"\U0001F6D1 <b>{_escape(a['ticker'])}</b> bateu o STOP \u2014 corte a perda"
            lines.append(head)
            lines.append(
                f"    Preco agora {cur}{a['price']:.2f}  (nivel {cur}{a['level']:.2f})  |  "
                f"entrada {cur}{a['entry']:.2f}  |  <b>{a['pct']:+.2f}%</b>"
            )
            lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


def send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Envia a mensagem, dividindo em partes se exceder o limite do Telegram."""
    if not bot_token or not chat_id:
        print("[erro] TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nao configurados.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    ok = True
    for chunk in _split(text, 3900):
        try:
            resp = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[erro] Telegram respondeu {resp.status_code}: {resp.text}")
                ok = False
        except Exception as exc:
            print(f"[erro] falha ao enviar para o Telegram: {exc}")
            ok = False
    return ok


def _split(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            parts.append(current)
            current = ""
        current += line + "\n"
    if current:
        parts.append(current)
    return parts
