from copiloto.analytics.causa_raiz import Padrao
from copiloto.analytics.impacto import Candidato
from copiloto.dominio import TEMAS
from copiloto.stats import pct_com_n
from copiloto.sugestoes import (
    AVISO,
    CATEGORIAS,
    EXTRAS_PICO,
    LIMITE_POR_ACAO,
    OPERACAO,
    PRATOS,
    sugestoes_para,
)

CATEGORIAS_DO_CARDAPIO = {"Batata Frita": "Porções", "Açaí 500ml": "Sobremesas", "Pizza Calabresa": "Pizzas",
                          "Pudim": "Sobremesas"}


def padrao(*condicoes: str) -> Padrao:
    p = pct_com_n(10, 20)
    return Padrao(condicoes, p, p, p, None, 2.0, 5.0, 0.001)


def candidato_prato(prato: str, *temas: str) -> Candidato:
    return Candidato("prato", f"Melhorar {prato}", frozenset(), temas=temas, prato=prato)


def test_todo_tema_tem_sugestao_de_operacao_completa():
    assert set(OPERACAO) == set(TEMAS)
    todas = [s for lista in (*OPERACAO.values(), *PRATOS.values(), *CATEGORIAS.values()) for s in lista]
    for s in todas:
        assert s.texto and s.porque and s.como_medir     # nenhuma sugestão sem motivo nem indicador


def test_batata_murcha_recebe_ventilacao_molho_a_parte_e_fritura():
    textos = " ".join(s.texto.lower() for s in sugestoes_para(candidato_prato("Batata Frita", "textura"), CATEGORIAS_DO_CARDAPIO))
    assert "furos de ventilação" in textos and "molho" in textos and "fritura" in textos


def test_acai_derretido_recebe_embalagem_termica():
    textos = " ".join(s.texto.lower() for s in sugestoes_para(candidato_prato("Açaí 500ml", "temperatura"), CATEGORIAS_DO_CARDAPIO))
    assert "térmica" in textos


def test_prato_sem_catalogo_proprio_usa_a_categoria_e_depois_a_operacao():
    pizza = sugestoes_para(candidato_prato("Pizza Calabresa", "temperatura"), CATEGORIAS_DO_CARDAPIO)
    assert pizza == CATEGORIAS[("Pizzas", "temperatura")]
    pudim = sugestoes_para(candidato_prato("Pudim", "sabor"), CATEGORIAS_DO_CARDAPIO)
    assert pudim == OPERACAO["sabor"][:1]


def test_segmento_de_pico_traz_primeiro_a_ideia_especifica_do_horario():
    cand = Candidato("segmento", "x", frozenset(), temas=("atraso", "temperatura"),
                     padroes=(("atraso", padrao("de sexta-feira", "à noite")),
                              ("temperatura", padrao("de sexta-feira", "à noite"))))
    lista = sugestoes_para(cand)
    assert lista[0] == EXTRAS_PICO[0]
    assert len(lista) <= LIMITE_POR_ACAO and len(set(lista)) == len(lista)


def test_distancia_longa_traz_embalagem_termica_e_raio():
    cand = Candidato("segmento", "x", frozenset(), temas=("temperatura",),
                     padroes=(("temperatura", padrao("a mais de 5 km de distância")),))
    assert any("5 km" in s.texto for s in sugestoes_para(cand))


def test_problema_sem_segmento_recebe_as_ideias_do_tema():
    cand = Candidato("residual", "x", frozenset(), temas=("pedido_errado",))
    assert sugestoes_para(cand) == OPERACAO["pedido_errado"][:2]


def test_aviso_deixa_claro_que_e_sugestao_a_avaliar_sem_garantia():
    assert "Sugestões a avaliar" in AVISO and "Não são garantia de resultado" in AVISO


def test_toda_acao_do_plano_real_tem_sugestoes(df_avaliacoes, con_classificada):
    from copiloto.analytics.base import carregar_pedidos
    from copiloto.analytics.impacto import montar_plano

    categorias = {r["nome"]: r["categoria"] for r in con_classificada.execute("SELECT nome, categoria FROM cardapio")}
    plano = montar_plano(df_avaliacoes, carregar_pedidos(con_classificada))
    assert plano.acoes
    for acao in plano.acoes:
        assert sugestoes_para(acao.candidato, categorias), acao.titulo
