"""Os dados fictícios devem conter os padrões prometidos no README."""
import json
from datetime import date

import pandas as pd

from copiloto import db
from copiloto.datagen.gerador import ATAQUE_DIAS, SEED_PADRAO, gerar


def test_volumes_dentro_do_combinado(dados):
    con = db.conectar(dados[0])
    assert 15 <= con.execute("SELECT COUNT(*) FROM cardapio").fetchone()[0] <= 20
    assert 2800 <= con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] <= 3200
    assert 500 <= con.execute("SELECT COUNT(*) FROM avaliacoes").fetchone()[0] <= 800


def test_mesma_seed_gera_os_mesmos_dados(dados, tmp_path):
    gerar(tmp_path / "outro.db", tmp_path / "outro.json", seed=SEED_PADRAO)
    a, b = db.conectar(dados[0]), db.conectar(tmp_path / "outro.db")
    consulta = "SELECT avaliacao_id, criado_em, nota, texto FROM avaliacoes ORDER BY avaliacao_id"
    assert [tuple(r) for r in a.execute(consulta)] == [tuple(r) for r in b.execute(consulta)]


def test_p1_batata_tem_muito_mais_problemas_com_entrega_longa(dados):
    con = db.conectar(dados[0])
    gab = {int(k): v for k, v in json.loads(dados[1].read_text(encoding="utf-8"))["avaliacoes"].items()}
    menc = [(p["problemas"] != []) for g in gab.values() for p in g["pratos"] if p["prato"] == "Batata Frita"]
    assert len(menc) >= 60
    assert 0.50 <= sum(menc) / len(menc) <= 0.80


def test_p2_sexta_a_noite_demora_mais_e_piora_em_outubro(dados):
    pedidos = db.consultar(db.conectar(dados[0]), "SELECT criado_em, dia_semana, hora, tempo_entrega_min FROM pedidos")
    pedidos["criado_em"] = pd.to_datetime(pedidos["criado_em"])
    pico = (pedidos["dia_semana"] == 4) & pedidos["hora"].between(18, 22)
    antes = pedidos["criado_em"] < "2026-10-01"
    media_pico_antes = pedidos[pico & antes]["tempo_entrega_min"].mean()
    media_pico_out = pedidos[pico & ~antes]["tempo_entrega_min"].mean()
    media_resto = pedidos[~pico]["tempo_entrega_min"].mean()
    assert media_pico_antes - media_resto >= 10
    assert media_pico_out - media_pico_antes >= 8


def test_p3_ataque_de_avaliacoes_falsas(dados):
    con = db.conectar(dados[0])
    gab = {int(k): v for k, v in json.loads(dados[1].read_text(encoding="utf-8"))["avaliacoes"].items()}
    ids = [i for i, g in gab.items() if g["falsa"]]
    assert len(ids) == 46
    linhas = db.consultar(
        con,
        f"""SELECT a.criado_em, a.nota, a.pedido_id, c.criado_em AS conta_criada
            FROM avaliacoes a JOIN clientes c USING (cliente_id) WHERE a.avaliacao_id IN ({",".join(map(str, ids))})""",
    )
    datas = pd.to_datetime(linhas["criado_em"]).dt.date
    assert set(datas) <= set(ATAQUE_DIAS)
    assert (linhas["nota"] <= 2).all()
    assert linhas["pedido_id"].isna().mean() >= 0.5
    idade = pd.to_datetime(linhas["criado_em"]) - pd.to_datetime(linhas["conta_criada"])
    assert (idade < pd.Timedelta(days=5)).all()  # contas criadas pouco antes do ataque


def test_p6_duas_avaliacoes_trazem_injecao(dados):
    resumo = json.loads(dados[1].read_text(encoding="utf-8"))["resumo"]
    assert len(resumo["avaliacoes_com_injecao"]) == 2


def test_periodo_de_seis_meses(dados):
    con = db.conectar(dados[0])
    primeiro, ultimo = con.execute("SELECT MIN(criado_em), MAX(criado_em) FROM pedidos").fetchone()
    assert primeiro.startswith("2026-05") and ultimo.startswith("2026-10")
    assert date.fromisoformat(ultimo[:10]) <= date(2026, 10, 31)
