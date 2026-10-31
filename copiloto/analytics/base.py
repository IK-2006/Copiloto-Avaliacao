"""Carregamento da base analítica: uma linha por avaliação, já classificada."""
from __future__ import annotations

import json
import sqlite3

import pandas as pd

from copiloto import db


def carregar_avaliacoes(con: sqlite3.Connection) -> pd.DataFrame:
    """Avaliações classificadas, com os atributos do pedido quando existir.

    Colunas extras: `temas` (lista), `pratos` (lista de {prato, problemas}), `tem_pedido`.
    """
    df = db.consultar(
        con,
        """SELECT a.avaliacao_id, a.pedido_id, a.cliente_id, a.criado_em, a.nota, a.texto,
                  k.sentimento, k.temas, k.pratos, k.injecao, k.provedor,
                  p.dia_semana, p.hora, p.turno, p.tempo_preparo_min, p.tempo_entrega_min, p.distancia_km
           FROM avaliacoes a
           JOIN classificacoes k ON k.avaliacao_id = a.avaliacao_id
           LEFT JOIN pedidos p ON p.pedido_id = a.pedido_id
           ORDER BY a.criado_em""",
    )
    df["criado_em"] = pd.to_datetime(df["criado_em"])
    df["temas"] = df["temas"].map(json.loads)
    df["pratos"] = df["pratos"].map(json.loads)
    df["tem_pedido"] = df["pedido_id"].notna()
    df["injecao"] = df["injecao"].astype(bool)
    return df
