"""Séries temporais e resumos gerais para o dashboard."""
from __future__ import annotations

import pandas as pd

from copiloto.dominio import TEMAS
from copiloto.stats import Proporcao, pct_com_n


def resumo_geral(df: pd.DataFrame) -> dict:
    n = len(df)
    return {
        "avaliacoes": n,
        "nota_media": float(df["nota"].mean()) if n else None,
        "negativas": pct_com_n(int((df["sentimento"] == "negativo").sum()), n),
        "com_pedido": pct_com_n(int(df["tem_pedido"].sum()), n),
    }


def nota_por_semana(df: pd.DataFrame) -> pd.DataFrame:
    """Nota média e quantidade de avaliações por semana (segunda a domingo)."""
    semana = df["criado_em"].dt.to_period("W").dt.start_time
    out = df.groupby(semana)["nota"].agg(nota_media="mean", avaliacoes="count").reset_index()
    return out.rename(columns={"criado_em": "semana"})


def temas_por_semana(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada semana e tema: avaliações que o citam (k) e total de avaliações da semana (n)."""
    semana = df["criado_em"].dt.to_period("W").dt.start_time
    total = df.groupby(semana).size()
    linhas = []
    for tema in TEMAS:
        cita = df["temas"].map(lambda ts, t=tema: t in ts)
        k = df[cita].groupby(semana[cita]).size()
        for sem, n in total.items():
            kk = int(k.get(sem, 0))
            linhas.append({"semana": sem, "tema": tema, "k": kk, "n": int(n), "pct": 100 * kk / n})
    return pd.DataFrame(linhas)


def ranking_temas(df: pd.DataFrame) -> list[tuple[str, Proporcao]]:
    """Temas de reclamação, do mais ao menos citado, como parcela de todas as avaliações."""
    n = len(df)
    itens = [(t, pct_com_n(int(df["temas"].map(lambda ts, t=t: t in ts).sum()), n)) for t in TEMAS]
    return sorted(itens, key=lambda x: -x[1].k)
