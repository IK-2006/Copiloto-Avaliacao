from datetime import date

import pytest

from copiloto.analytics.base import carregar_pedidos
from copiloto.analytics.variacao import explicar_variacao, rotulo_mes
from copiloto.llm.limite import pode_usar, registrar, usadas_hoje


@pytest.fixture(scope="module")
def outubro(df_suspeitas, con_classificada):
    return explicar_variacao(df_suspeitas, carregar_pedidos(con_classificada), "2026-10")


def test_a_queda_de_outubro_vem_sobretudo_das_suspeitas(outubro):
    nota = outubro["nota"]
    assert nota["todas"]["queda"] >= 0.8
    assert nota["efeito_das_suspeitas"] >= 0.6
    assert 0.05 <= nota["sem_suspeitas"]["queda"] <= 0.35
    # as partes fecham com a queda total (com folga de arredondamento)
    assert nota["efeito_das_suspeitas"] + nota["sem_suspeitas"]["queda"] == pytest.approx(nota["todas"]["queda"], abs=0.011)


def test_suspeitas_do_mes_batem_com_o_episodio(outubro):
    susp = outubro["suspeitas_no_mes"]
    assert susp["avaliacoes"]["k"] >= 40 and susp["avaliacoes"]["n"] > susp["avaliacoes"]["k"]
    assert susp["nota_media"] <= 1.3


def test_piora_na_entrega_aparece_na_sexta_a_noite(outubro):
    [segmento, *_] = outubro["entrega"]["segmentos"]
    assert segmento["segmento"] == "pedidos de sexta-feira, à noite"
    assert segmento["diferenca_min"] >= 10 and segmento["no_mes"] > segmento["meses_anteriores"]


def test_nenhum_tema_e_apontado_como_crescente_sem_prova(outubro):
    """O aumento de atraso em outubro (+34%) não passa no teste, então não é afirmado."""
    assert not any(t["significativo"] for t in outubro["temas"])
    atraso = next(t for t in outubro["temas"] if t["tema"] == "atraso")
    assert atraso["no_mes"]["k"] <= atraso["no_mes"]["n"]


@pytest.mark.parametrize("mes", ["2026-05", "2026-11", "2027-01"])
def test_mes_sem_historico_ou_sem_avaliacoes_diz_que_nao_ha_dados(df_suspeitas, con_classificada, mes):
    r = explicar_variacao(df_suspeitas, carregar_pedidos(con_classificada), mes)
    assert r["sem_dados"] and "pelo menos 20" in r["motivo"]


def test_rotulo_do_mes():
    assert rotulo_mes("2026-10") == "outubro de 2026" and rotulo_mes("2026-03") == "março de 2026"


# --- Limite diário de chamadas ----------------------------------------------------------------------------
def test_limite_conta_por_dia(con_classificada, tmp_path):
    from copiloto import db

    con = db.conectar(tmp_path / "l.db")
    hoje, amanha = date(2026, 10, 31), date(2026, 11, 1)
    assert usadas_hoje(con, hoje) == 0 and pode_usar(con, 3, hoje)
    registrar(con, 2, hoje)
    registrar(con, 1, hoje)
    assert usadas_hoje(con, hoje) == 3 and not pode_usar(con, 3, hoje)
    assert pode_usar(con, 3, amanha) and usadas_hoje(con, amanha) == 0
    con.close()
