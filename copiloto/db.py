"""Banco SQLite: esquema e utilitários de leitura."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from copiloto import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    cliente_id   INTEGER PRIMARY KEY,
    cliente_ref  TEXT NOT NULL UNIQUE,      -- identificador anônimo, o único que a IA enxerga
    nome         TEXT NOT NULL,             -- dado pessoal (fictício): nunca vai para a IA
    telefone     TEXT NOT NULL,             -- dado pessoal (fictício)
    endereco     TEXT NOT NULL,             -- dado pessoal (fictício)
    criado_em    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cardapio (
    item_id    INTEGER PRIMARY KEY,
    nome       TEXT NOT NULL UNIQUE,
    categoria  TEXT NOT NULL,
    preco      REAL NOT NULL,
    genero     TEXT NOT NULL,               -- 'm' ou 'f'
    aliases    TEXT NOT NULL                -- JSON: como os clientes costumam chamar o item
);

CREATE TABLE IF NOT EXISTS pedidos (
    pedido_id         INTEGER PRIMARY KEY,
    cliente_id        INTEGER NOT NULL REFERENCES clientes(cliente_id),
    criado_em         TEXT NOT NULL,
    dia_semana        INTEGER NOT NULL,     -- 0 = segunda ... 6 = domingo
    hora              INTEGER NOT NULL,
    turno             TEXT NOT NULL,        -- almoço | tarde | noite
    tempo_preparo_min REAL NOT NULL,
    tempo_entrega_min REAL NOT NULL,        -- do pedido até a porta do cliente
    distancia_km      REAL NOT NULL,
    valor_total       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pedido_itens (
    pedido_id   INTEGER NOT NULL REFERENCES pedidos(pedido_id),
    item_id     INTEGER NOT NULL REFERENCES cardapio(item_id),
    quantidade  INTEGER NOT NULL,
    PRIMARY KEY (pedido_id, item_id)
);

CREATE TABLE IF NOT EXISTS avaliacoes (
    avaliacao_id INTEGER PRIMARY KEY,
    pedido_id    INTEGER REFERENCES pedidos(pedido_id),   -- NULL = avaliação sem pedido
    cliente_id   INTEGER NOT NULL REFERENCES clientes(cliente_id),
    criado_em    TEXT NOT NULL,
    nota         INTEGER NOT NULL CHECK (nota BETWEEN 1 AND 5),
    texto        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classificacoes (
    avaliacao_id INTEGER PRIMARY KEY REFERENCES avaliacoes(avaliacao_id),
    sentimento   TEXT NOT NULL,
    temas        TEXT NOT NULL,             -- JSON: lista de temas de problema
    pratos       TEXT NOT NULL,             -- JSON: [{"prato": ..., "problemas": [...]}]
    injecao      INTEGER NOT NULL DEFAULT 0,
    provedor     TEXT NOT NULL,
    modelo       TEXT NOT NULL,
    hash_entrada TEXT NOT NULL,
    criado_em    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_pedidos_criado ON pedidos(criado_em);
CREATE INDEX IF NOT EXISTS ix_avaliacoes_criado ON avaliacoes(criado_em);
"""


def conectar(caminho: str | Path | None = None) -> sqlite3.Connection:
    caminho = Path(caminho) if caminho else config.carregar().db_path
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


def consultar(con: sqlite3.Connection, sql: str, params: tuple | dict = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params)
