import pytest

from copiloto.analytics.pratos import analise_por_prato, ranking_pratos
from copiloto.analytics.series import nota_por_semana, ranking_temas, resumo_geral, temas_por_semana
from copiloto.stats import LIMIAR_BAIXA_CONFIANCA


@pytest.fixture(scope="module")
def analises(con_classificada, df_avaliacoes):
    return analise_por_prato(con_classificada, df_avaliacoes)


def test_batata_frita_lidera_o_ranking_entre_pratos_com_amostra_suficiente(analises):
    ranking = ranking_pratos(analises)
    confiaveis = [a for a in ranking if not a.baixa_confianca]
    assert confiaveis[0].prato == "Batata Frita"
    assert 45 <= confiaveis[0].com_problema.pct <= 80
    assert confiaveis[0].mencoes >= 60
    segundo = confiaveis[1]
    assert confiaveis[0].com_problema.pct - segundo.com_problema.pct >= 15


def test_batata_frita_reclama_de_textura_e_temperatura(analises):
    batata = next(a for a in analises if a.prato == "Batata Frita")
    principais = [t for t, _ in batata.problemas[:2]]
    assert set(principais) == {"textura", "temperatura"}


def test_toda_proporcao_traz_sua_base(analises):
    for a in analises:
        assert a.com_problema.n == a.mencoes
        assert a.com_problema.k <= a.mencoes
        for _, p in a.problemas:
            assert p.n == a.mencoes and 0 < p.k <= p.n


def test_pratos_raros_tem_aviso_de_baixa_confianca_e_ficam_no_fim(analises):
    por_nome = {a.prato: a for a in analises}
    assert por_nome["Pudim"].baixa_confianca and por_nome["Salada Caesar"].baixa_confianca
    ranking = ranking_pratos(analises)
    flags = [a.baixa_confianca for a in ranking]
    assert flags == sorted(flags)  # todos os confiáveis (False) antes dos de baixa confiança (True)
    assert all(a.mencoes < LIMIAR_BAIXA_CONFIANCA for a in ranking if a.baixa_confianca)


def test_acai_aparece_com_problema_relevante(analises):
    acai = next(a for a in analises if a.prato == "Açaí 500ml")
    assert acai.com_problema.pct >= 25 and acai.problemas[0][0] == "temperatura"


def test_resumo_e_series(df_avaliacoes):
    geral = resumo_geral(df_avaliacoes)
    assert geral["avaliacoes"] == len(df_avaliacoes)
    assert 3.0 <= geral["nota_media"] <= 4.5
    semanal = nota_por_semana(df_avaliacoes)
    assert semanal["avaliacoes"].sum() == len(df_avaliacoes)
    temas = temas_por_semana(df_avaliacoes)
    assert (temas["k"] <= temas["n"]).all()
    ranking = ranking_temas(df_avaliacoes)
    assert [p.k for _, p in ranking] == sorted((p.k for _, p in ranking), reverse=True)
