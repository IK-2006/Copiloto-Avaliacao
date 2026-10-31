"""Fixtures compartilhadas: um banco fictício gerado uma vez por sessão de testes."""
from __future__ import annotations

import pytest

from copiloto import db
from copiloto.analytics.base import carregar_avaliacoes
from copiloto.classify import classificar_pendentes
from copiloto.datagen.gerador import SEED_PADRAO, gerar
from copiloto.llm.rules import ProvedorRegras


@pytest.fixture(scope="session")
def dados(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("dados")
    caminho_db, caminho_gab = pasta / "teste.db", pasta / "plantados.json"
    gerar(caminho_db, caminho_gab, seed=SEED_PADRAO)
    return caminho_db, caminho_gab


@pytest.fixture(scope="session")
def con_classificada(dados):
    con = db.conectar(dados[0])
    classificar_pendentes(con, ProvedorRegras())
    yield con
    con.close()


@pytest.fixture(scope="session")
def df_avaliacoes(con_classificada):
    return carregar_avaliacoes(con_classificada)
