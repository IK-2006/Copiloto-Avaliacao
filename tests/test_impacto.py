"""Plano de ação: a conta do impacto na nota e a ordem das ações."""
import json

import numpy as np
import pandas as pd
import pytest

from copiloto.analytics.base import carregar_pedidos
from copiloto.analytics.impacto import (
    Candidato,
    base_do_plano,
    montar_plano,
    nota_referencia,
    ordenar_plano,
)


def base(linhas: list[tuple[int, list[str]]]) -> pd.DataFrame:
    return pd.DataFrame({
        "nota": [n for n, _ in linhas],
        "temas": [t for _, t in linhas],
        "pratos": [[] for _ in linhas],
        "tem_pedido": True,
    })


def candidato(nome: str, *instancias: tuple[int, str]) -> Candidato:
    return Candidato("residual", nome, frozenset(instancias), temas=tuple({t for _, t in instancias}))


def plano(b, candidatos, **kw):
    return ordenar_plano(b, candidatos, min_ganho=0.0, min_instancias=1, **kw)


# --- A conta, com resposta calculada à mão ---------------------------------------------------------
def test_resolver_o_unico_problema_leva_as_avaliacoes_a_nota_de_referencia():
    b = base([(5, [])] * 5 + [(3, ["atraso"])] * 5)
    p = plano(b, [candidato("atrasos", *((i, "atraso") for i in range(5, 10)))])
    assert nota_referencia(b) == 5.0 and p.nota_atual == 4.0
    [a] = p.acoes
    assert a.ganho == pytest.approx(1.0)               # 5 avaliações x 2 pontos / 10
    assert a.ganho_conservador == pytest.approx(0.5)
    assert a.nota_depois == pytest.approx(5.0) and a.nota_depois_conservadora == pytest.approx(4.5)


def test_avaliacao_com_dois_problemas_divide_o_credito_e_nao_conta_duas_vezes():
    b = base([(5, [])] * 9 + [(3, ["atraso", "temperatura"])])
    p = plano(b, [candidato("atrasos", (9, "atraso")), candidato("frio", (9, "temperatura"))])
    assert [a.ganho for a in p.acoes] == pytest.approx([0.1, 0.1])   # metade da distância (2) cada
    assert p.nota_final == pytest.approx(5.0)                         # e não 5,2


def test_resolver_um_dos_dois_problemas_resolve_so_a_metade():
    b = base([(5, [])] * 9 + [(3, ["atraso", "temperatura"])])
    [a] = plano(b, [candidato("atrasos", (9, "atraso"))]).acoes
    assert a.nota_depois == pytest.approx(b["nota"].mean() + 0.1)


def test_nota_nunca_cai_se_a_avaliacao_ja_esta_acima_da_referencia():
    b = base([(4, [])] * 8 + [(5, ["atraso"])] * 2)      # quem reclamou deu 5, acima da referência (4)
    p = plano(b, [candidato("atrasos", (8, "atraso"), (9, "atraso"))])
    assert [a.ganho for a in p.acoes] == [0.0] and p.nota_final == p.nota_atual
    # com o corte padrão de ganho mínimo, uma ação que não muda a nota nem entra no plano
    assert ordenar_plano(b, [candidato("atrasos", (8, "atraso"), (9, "atraso"))], min_instancias=1).acoes == []


def test_sem_avaliacoes_sem_problema_nao_ha_referencia_nem_plano():
    b = base([(3, ["atraso"])] * 4)
    assert np.isnan(nota_referencia(b))
    assert plano(b, [candidato("atrasos", *((i, "atraso") for i in range(4)))]).acoes == []


def test_ganhos_nao_crescem_ao_longo_do_plano_e_a_soma_fecha_com_a_media():
    rng = np.random.default_rng(7)
    n = 300
    temas = [[t for t in ("atraso", "temperatura", "sabor") if rng.random() < 0.2] for _ in range(n)]
    notas = [int(np.clip(round(4.6 - 1.2 * len(ts) + rng.normal(0, 0.6)), 1, 5)) for ts in temas]
    b = base(list(zip(notas, temas)))
    candidatos = [
        candidato(t, *((i, t) for i, ts in enumerate(temas) if t in ts)) for t in ("atraso", "temperatura", "sabor")
    ] + [candidato("misto", *((i, t) for i, ts in enumerate(temas) if len(ts) > 1 for t in ts))]
    p = plano(b, candidatos)
    ganhos = [a.ganho for a in p.acoes]
    assert ganhos == sorted(ganhos, reverse=True)
    for anterior, atual in zip(p.acoes, p.acoes[1:]):
        assert atual.nota_antes == pytest.approx(anterior.nota_depois)
    # recalculando de forma independente: todas as reclamações resolvidas de uma vez
    ref = nota_referencia(b)
    notas_np = np.array(notas, dtype=float)
    distancia = np.maximum(0, ref - notas_np)
    com_tema = np.array([len(ts) > 0 for ts in temas])
    esperado = (notas_np + np.where(com_tema, distancia, 0)).mean()
    assert p.nota_final == pytest.approx(esperado)


def test_acao_pequena_sobre_o_que_ja_foi_resolvido_nao_vira_item():
    b = base([(5, [])] * 40 + [(2, ["atraso"])] * 10)
    grande = candidato("grande", *((i, "atraso") for i in range(40, 50)))
    quase_igual = candidato("quase igual", *((i, "atraso") for i in range(40, 43)))
    p = ordenar_plano(b, [grande, quase_igual], min_ganho=0.0, min_instancias=2)
    assert [a.titulo for a in p.acoes] == ["grande"]


# --- Dados fictícios -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def plano_real(df_avaliacoes, con_classificada):
    return montar_plano(df_avaliacoes, carregar_pedidos(con_classificada))


def test_base_do_plano_so_tem_avaliacoes_de_pedidos(df_avaliacoes):
    b = base_do_plano(df_avaliacoes)
    assert b["tem_pedido"].all() and len(b) < len(df_avaliacoes)
    assert list(b.index) == list(range(len(b)))


def test_a_sexta_a_noite_e_a_primeira_prioridade(plano_real):
    primeira = plano_real.acoes[0]
    assert "sexta-feira" in primeira.titulo and "à noite" in primeira.titulo
    assert "atrasos" in primeira.titulo and "comida fria" in primeira.titulo
    assert primeira.ganho >= 0.12


def test_batata_frita_entra_no_plano_com_amostra_suficiente(plano_real):
    batata = next(a for a in plano_real.acoes if a.candidato.prato == "Batata Frita")
    assert not batata.baixa_confianca and batata.ganho > 0.03


def test_plano_real_e_coerente(plano_real):
    acoes = plano_real.acoes
    assert [a.prioridade for a in acoes] == list(range(1, len(acoes) + 1))
    assert [a.ganho for a in acoes] == sorted((a.ganho for a in acoes), reverse=True)
    assert plano_real.nota_atual < plano_real.nota_final_conservadora < plano_real.nota_final
    assert plano_real.nota_final <= 5
    for a in acoes:
        assert a.ganho_conservador == pytest.approx(a.ganho / 2)
        assert a.baixa_confianca == (a.avaliacoes_afetadas.k < 20)
        assert a.avaliacoes_afetadas.n == plano_real.avaliacoes


def test_titulos_nao_inventam_demais_casos(plano_real):
    titulos = [a.titulo for a in plano_real.acoes]
    assert "Resolver atrasos (demais casos)" in titulos        # existe ação de atraso por segmento
    assert not any("pedidos errados (demais casos)" in t for t in titulos)


def test_sem_as_avaliacoes_falsas_a_nota_de_hoje_e_maior(df_avaliacoes, con_classificada, dados):
    """O ataque derruba a média e a referência; a Etapa 4 vai permitir tirar as suspeitas do cálculo."""
    gab = json.loads(dados[1].read_text(encoding="utf-8"))["avaliacoes"]
    falsa = df_avaliacoes["avaliacao_id"].map(lambda i: gab[str(i)]["falsa"])
    pedidos = carregar_pedidos(con_classificada)
    com = montar_plano(df_avaliacoes, pedidos)
    sem = montar_plano(df_avaliacoes[~falsa], pedidos)
    assert sem.nota_atual - com.nota_atual >= 0.05
    assert sem.nota_referencia > com.nota_referencia
