"""Persistencia de estado entre as execucoes de abertura e fechamento.

No GitHub Actions os runners sao descartaveis, entao o estado e gravado em
arquivos dentro da pasta data/ e commitado de volta ao repositorio pelo workflow.

- data/portfolio.json : indicacoes em acompanhamento (posicoes abertas)
- data/history.csv    : snapshots de fechamento e posicoes encerradas
"""
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    d = _base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _portfolio_path() -> Path:
    return data_dir() / "portfolio.json"


def _history_path() -> Path:
    return data_dir() / "history.csv"


def load_portfolio() -> Dict:
    path = _portfolio_path()
    if not path.exists():
        return {"positions": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"positions": []}


def save_portfolio(data: Dict) -> None:
    _portfolio_path().write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def add_positions(portfolio: Dict, picks: List[Dict], today: str) -> List[Dict]:
    """Adiciona novas indicacoes que ainda nao estao em acompanhamento.

    Retorna apenas as posicoes NOVAS (para destacar na mensagem de abertura).
    """
    existentes = {p["ticker"] for p in portfolio.get("positions", [])}
    novas = []
    for pick in picks:
        if pick["ticker"] in existentes:
            continue
        pos = {
            "ticker": pick["ticker"],
            "date_indicated": today,
            "entry_price": pick["price"],
            "score": pick["score"],
            "rating": pick["rating"],
            "stop": pick["stop"],
            "target": pick["target"],
        }
        portfolio.setdefault("positions", []).append(pos)
        novas.append(pos)
    return novas


def days_since(date_indicated: str, today: str) -> int:
    try:
        d0 = datetime.strptime(date_indicated, "%Y-%m-%d").date()
        d1 = datetime.strptime(today, "%Y-%m-%d").date()
        return (d1 - d0).days
    except Exception:
        return 0


def archive_and_prune(portfolio: Dict, closed: List[Dict]) -> None:
    """Remove do portfolio as posicoes encerradas (ja gravadas no history)."""
    encerrados = {c["ticker"] + c["date_indicated"] for c in closed}
    portfolio["positions"] = [
        p
        for p in portfolio.get("positions", [])
        if (p["ticker"] + p["date_indicated"]) not in encerrados
    ]


def append_history(rows: List[Dict]) -> None:
    if not rows:
        return
    path = _history_path()
    fields = [
        "snapshot_date",
        "ticker",
        "date_indicated",
        "dias",
        "entry_price",
        "price",
        "pct_total",
        "pct_dia",
        "status",
    ]
    novo = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if novo:
            writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fields})


def today_str() -> str:
    return date.today().isoformat()


def read_history() -> List[Dict]:
    """Le o history.csv como lista de dicionarios (vazio se nao existir)."""
    path = _history_path()
    if not path.exists():
        return []
    rows: List[Dict] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def within_last_days(snapshot_date: str, today: str, days: int) -> bool:
    try:
        d0 = datetime.strptime(snapshot_date, "%Y-%m-%d").date()
        d1 = datetime.strptime(today, "%Y-%m-%d").date()
        return 0 <= (d1 - d0).days < days
    except Exception:
        return False
