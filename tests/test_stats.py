import pytest

from copiloto.stats import LIMIAR_BAIXA_CONFIANCA, formatar_nota, formatar_pct, pct_com_n


def test_percentual_e_base():
    p = pct_com_n(78, 120)
    assert p.k == 78 and p.n == 120
    assert p.pct == pytest.approx(65.0)


def test_texto_sempre_mostra_a_base():
    assert pct_com_n(78, 120).texto() == "65% de 120 avaliações"
    assert pct_com_n(1, 3).texto(casas=1) == "33,3% de 3 avaliações (baixa confiança)"


@pytest.mark.parametrize("n,esperado", [(0, True), (19, True), (20, False), (500, False)])
def test_baixa_confianca_abaixo_de_20(n, esperado):
    assert LIMIAR_BAIXA_CONFIANCA == 20
    assert pct_com_n(0, n).baixa_confianca is esperado


def test_base_zero_nao_divide_por_zero():
    assert pct_com_n(0, 0).pct == 0.0


@pytest.mark.parametrize("k,n", [(-1, 10), (11, 10), (1, -2)])
def test_proporcao_invalida_e_rejeitada(k, n):
    with pytest.raises(ValueError):
        pct_com_n(k, n)


def test_formato_brasileiro():
    assert formatar_pct(72.0) == "72%"
    assert formatar_pct(72.5, 1) == "72,5%"
    assert formatar_nota(4.26) == "4,3"
