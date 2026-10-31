"""Análise por prato: quais problemas cada item do cardápio mais gera."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd

from copiloto import db
from copiloto.dominio import TEMAS
from copiloto.stats import Proporcao, pct_com_n


@dataclass(frozen=True)
class AnalisePrato:
    prato: str
    categoria: str
    pedidos: int                       # pedidos que incluíram o prato
    mencoes: int                       # avaliações que citam o prato
    com_problema: Proporcao            # das menções, quantas relatam algum problema
    problemas: list[tuple[str, Proporcao]] = field(default_factory=list)  # por tema, do mais citado ao menos
    nota_media: float | None = None    # nota média das avaliações que citam o prato

    @property
    def baixa_confianca(self) -> bool:
        return self.com_problema.baixa_confianca


def analise_por_prato(con: sqlite3.Connection, df: pd.DataFrame) -> list[AnalisePrato]:
    """Base = avaliações que citam o prato (citação explícita no texto).

    O percentual é "k de n avaliações que citam o prato". Citar o prato é uma escolha do
    cliente, então a taxa mede o que se diz quando ele é lembrado, não a taxa de falha em todos
    os pedidos; por isso a tabela também traz quantos pedidos tinham o prato.
    """
    cardapio = db.consultar(con, "SELECT item_id, nome, categoria FROM cardapio ORDER BY item_id")
    pedidos = db.consultar(con, "SELECT item_id, COUNT(DISTINCT pedido_id) AS n FROM pedido_itens GROUP BY item_id")
    n_pedidos = dict(zip(pedidos["item_id"], pedidos["n"]))

    linhas = []
    for _, item in cardapio.iterrows():
        problemas_por_mencao = [
            next(set(p["problemas"]) for p in pratos if p["prato"] == item["nome"])
            for pratos in df["pratos"]
            if any(p["prato"] == item["nome"] for p in pratos)
        ]
        mascara = df["pratos"].map(lambda ps, nome=item["nome"]: any(p["prato"] == nome for p in ps))
        n = len(problemas_por_mencao)
        k = sum(1 for s in problemas_por_mencao if s)
        por_tema = [
            (t, pct_com_n(sum(1 for s in problemas_por_mencao if t in s), n)) for t in TEMAS
        ]
        por_tema = sorted((x for x in por_tema if x[1].k > 0), key=lambda x: (-x[1].k, x[0]))
        linhas.append(AnalisePrato(
            prato=item["nome"],
            categoria=item["categoria"],
            pedidos=int(n_pedidos.get(item["item_id"], 0)),
            mencoes=n,
            com_problema=pct_com_n(k, n),
            problemas=por_tema,
            nota_media=float(df.loc[mascara, "nota"].mean()) if n else None,
        ))
    return linhas


def ranking_pratos(analises: list[AnalisePrato], min_mencoes: int = 1) -> list[AnalisePrato]:
    """Pratos ordenados pelo percentual de menções com problema; amostras pequenas vão para o fim."""
    validos = [a for a in analises if a.mencoes >= min_mencoes]
    return sorted(validos, key=lambda a: (a.baixa_confianca, -a.com_problema.pct, -a.mencoes))
