import pytest

from copiloto.classify import carregar_cardapio
from copiloto.llm.base import EntradaAvaliacao
from copiloto.llm.rules import ProvedorRegras
from copiloto.validacao import comparar


@pytest.fixture(scope="module")
def classificar(con_classificada):
    cardapio = carregar_cardapio(con_classificada)
    regras = ProvedorRegras()

    def _classificar(texto: str, nota: int = 3):
        return regras.classificar([EntradaAvaliacao("av_0", nota, texto, ())], cardapio)[0]

    return _classificar


def test_problema_atribuido_ao_prato(classificar):
    r = classificar("A batata chegou fria e murcha.", nota=2)
    assert r.sentimento == "negativo"
    assert set(r.temas) == {"temperatura", "textura"}
    assert [(p.prato, set(p.problemas)) for p in r.pratos] == [("Batata Frita", {"temperatura", "textura"})]


def test_elogio_nao_vira_problema(classificar):
    r = classificar("Chegou rápido e quentinho! A batata estava crocante, adorei.", nota=5)
    assert r.sentimento == "positivo"
    assert r.temas == ()
    assert [(p.prato, p.problemas) for p in r.pratos] == [("Batata Frita", ())]


@pytest.mark.parametrize(
    "texto,tema",
    [
        ("Não demorou nada, chegou no prazo.", "atraso"),
        ("Sem nenhum atraso, tudo certo.", "atraso"),
        ("Nada frio, veio na temperatura certa.", "temperatura"),
        ("Pizza sem problema nenhum de textura, nada mole.", "textura"),
    ],
)
def test_negacao_desfaz_o_problema(classificar, texto, tema):
    assert tema not in classificar(texto, nota=5).temas


@pytest.mark.parametrize(
    "texto,tema",
    [
        ("Não chegou quente.", "temperatura"),
        ("A batata veio sem nenhuma crocância.", "textura"),
        ("Nada crocante essa batata.", "textura"),
    ],
)
def test_palavra_positiva_negada_vira_problema(classificar, texto, tema):
    assert tema in classificar(texto).temas


def test_funciona_sem_acentos_e_com_girias(classificar):
    r = classificar("pedido atrasou mt e a pizza de calabresa veio gelada, nao recomendo", nota=1)
    assert {"atraso", "temperatura"} <= set(r.temas)
    assert r.sentimento == "negativo"
    assert [p.prato for p in r.pratos] == ["Pizza Calabresa"]


def test_acuracia_contra_o_gabarito(con_classificada, dados):
    m = comparar(con_classificada, dados[1])
    assert m["acuracia_sentimento"] >= 0.85
    assert m["temas"]["f1"] >= 0.90
    assert m["pratos_mencionados"]["f1"] >= 0.95
    assert m["problema_por_prato"]["f1"] >= 0.88
