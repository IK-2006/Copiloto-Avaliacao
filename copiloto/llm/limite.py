"""Limite diário de chamadas ao Claude, para o demo público não gerar custo sem controle."""
from __future__ import annotations

import sqlite3
from datetime import date


def _dia(hoje: date | None) -> str:
    return (hoje or date.today()).isoformat()


def usadas_hoje(con: sqlite3.Connection, hoje: date | None = None) -> int:
    linha = con.execute("SELECT chamadas FROM uso_llm WHERE dia = ?", (_dia(hoje),)).fetchone()
    return int(linha["chamadas"]) if linha else 0


def pode_usar(con: sqlite3.Connection, limite: int, hoje: date | None = None) -> bool:
    return usadas_hoje(con, hoje) < limite


def registrar(con: sqlite3.Connection, chamadas: int = 1, hoje: date | None = None) -> None:
    con.execute(
        "INSERT INTO uso_llm (dia, chamadas) VALUES (?, ?) "
        "ON CONFLICT(dia) DO UPDATE SET chamadas = chamadas + excluded.chamadas",
        (_dia(hoje), chamadas),
    )
    con.commit()
