"""Carregamento da base analítica: avaliações já classificadas e pedidos."""
from __future__ import annotations

import json
import sqlite3

import pandas as pd

from copiloto import db


def carregar_pedidos(con: sqlite3.Connection) -> pd.DataFrame:
    """Todos os pedidos, com `itens` (tupla de nomes do cardápio, em ordem alfabética)."""
    pedidos = db.consultar(
        con,
        """SELECT pedido_id, cliente_id, criado_em, dia_semana, hora, turno,
                  tempo_preparo_min, tempo_entrega_min, distancia_km, valor_total
           FROM pedidos ORDER BY criado_em""",
    )
    itens = db.consultar(
        con, "SELECT pi.pedido_id, c.nome FROM pedido_itens pi JOIN cardapio c ON c.item_id = pi.item_id"
    )
    por_pedido = {pid: tuple(sorted(g["nome"])) for pid, g in itens.groupby("pedido_id")}
    pedidos["criado_em"] = pd.to_datetime(pedidos["criado_em"])
    pedidos["itens"] = pedidos["pedido_id"].map(lambda pid: por_pedido.get(pid, ()))
    return pedidos


def carregar_avaliacoes(con: sqlite3.Connection) -> pd.DataFrame:
    """Avaliações classificadas, com os atributos do pedido quando existir.

    Colunas extras: `temas` (lista), `pratos` (lista de {prato, problemas}), `tem_pedido`,
    `itens` (itens do pedido; tupla vazia quando a avaliação não tem pedido), `conta_criada_em`
    e `pedidos_da_conta` (pedidos da conta até o momento da avaliação, inclusive).
    """
    df = db.consultar(
        con,
        """SELECT a.avaliacao_id, a.pedido_id, a.cliente_id, a.criado_em, a.nota, a.texto,
                  k.sentimento, k.temas, k.pratos, k.injecao, k.provedor,
                  p.dia_semana, p.hora, p.turno, p.tempo_preparo_min, p.tempo_entrega_min, p.distancia_km,
                  c.criado_em AS conta_criada_em,
                  (SELECT COUNT(*) FROM pedidos p2
                    WHERE p2.cliente_id = a.cliente_id AND p2.criado_em <= a.criado_em) AS pedidos_da_conta
           FROM avaliacoes a
           JOIN classificacoes k ON k.avaliacao_id = a.avaliacao_id
           JOIN clientes c ON c.cliente_id = a.cliente_id
           LEFT JOIN pedidos p ON p.pedido_id = a.pedido_id
           ORDER BY a.criado_em""",
    )
    df["criado_em"] = pd.to_datetime(df["criado_em"])
    df["conta_criada_em"] = pd.to_datetime(df["conta_criada_em"])
    df["temas"] = df["temas"].map(json.loads)
    df["pratos"] = df["pratos"].map(json.loads)
    df["tem_pedido"] = df["pedido_id"].notna()
    df["injecao"] = df["injecao"].astype(bool)
    itens_do_pedido = carregar_pedidos(con).set_index("pedido_id")["itens"].to_dict()
    df["itens"] = [itens_do_pedido.get(int(p), ()) if pd.notna(p) else () for p in df["pedido_id"]]
    return df
