"""Causa raiz: acha os padrões plantados e não inventa padrão onde só há acaso."""
import numpy as np
import pandas as pd
import pytest

from copiloto.analytics.base import carregar_pedidos
from copiloto.analytics.causa_raiz import (
    DIMENSOES_QUANDO_ONDE,
    buscar_padroes,
    causas_da_entrega_lenta,
    causas_do_prato,
    causas_por_tema,
    comparar_tempos,
    evolucao_do_padrao,
    evolucao_tempos,
    mascara_do_padrao,
    rotulo_evento_tema,
)

ENTREGA_40 = "com entrega acima de 40 min"
SEXTA = "de sexta-feira"
NOITE = "à noite"


@pytest.fixture(scope="module")
def pedidos(con_classificada):
    return carregar_pedidos(con_classificada)


@pytest.fixture(scope="module")
def mecanismo(df_avaliacoes, pedidos):
    return causas_por_tema(df_avaliacoes, pedidos)


@pytest.fixture(scope="module")
def quando_onde(df_avaliacoes, pedidos):
    return causas_por_tema(df_avaliacoes, pedidos, dimensoes=DIMENSOES_QUANDO_ONDE)


# --- Dados sintéticos com resposta conhecida ---------------------------------------------------
def tabela(rng: np.random.Generator, n: int = 600) -> pd.DataFrame:
    return pd.DataFrame({
        "dia_semana": rng.integers(0, 7, n),
        "turno": rng.choice(["almoço", "tarde", "noite"], n, p=[0.3, 0.1, 0.6]),
        "tempo_entrega_min": rng.uniform(20, 60, n),
        "distancia_km": rng.uniform(0.5, 9, n),
        "tempo_preparo_min": rng.uniform(10, 35, n),
    })


def test_acha_a_regra_conhecida():
    rng = np.random.default_rng(1)
    base = tabela(rng)
    evento = pd.Series(np.where(base["tempo_entrega_min"] > 40, rng.random(len(base)) < 0.6, rng.random(len(base)) < 0.03))
    [melhor, *_] = buscar_padroes(base, evento)
    assert ENTREGA_40 in melhor.condicoes
    assert melhor.parcela_das_reclamacoes.pct > 80
    assert melhor.lift > 5 and melhor.p_ajustado < 0.001


def test_sem_relacao_nao_aparece_padrao_quase_nunca():
    """Evento sorteado sem relação com os pedidos: o teste com correção quase nunca deve acusar padrão."""
    com_padrao = 0
    for semente in range(40):
        rng = np.random.default_rng(1000 + semente)
        base = tabela(rng)
        evento = pd.Series(rng.random(len(base)) < 0.15)
        com_padrao += bool(buscar_padroes(base, evento))
    assert com_padrao <= 4  # nível de 5% por evento, com folga para as 40 repetições


def test_poucos_eventos_nao_geram_padrao():
    rng = np.random.default_rng(3)
    base = tabela(rng)
    evento = pd.Series(np.arange(len(base)) < 5)
    assert buscar_padroes(base, evento) == []


def test_numeros_do_padrao_batem_com_a_tabela():
    rng = np.random.default_rng(4)
    base = tabela(rng)
    evento = pd.Series(np.where(base["distancia_km"] > 5, rng.random(len(base)) < 0.5, rng.random(len(base)) < 0.05))
    [p, *_] = buscar_padroes(base, evento, pedidos=base)
    dentro = mascara_do_padrao(base, p.condicoes)
    ev = evento.to_numpy()
    assert p.no_segmento.n == dentro.sum() and p.no_segmento.k == (dentro & ev).sum()
    assert p.fora_do_segmento.n == (~dentro).sum() and p.fora_do_segmento.k == (~dentro & ev).sum()
    assert p.parcela_das_reclamacoes.k == p.no_segmento.k and p.parcela_das_reclamacoes.n == ev.sum()
    assert p.pedidos_no_segmento.k == dentro.sum() and p.pedidos_no_segmento.n == len(base)


# --- Padrões plantados nos dados fictícios --------------------------------------------------------
def test_comida_fria_vem_de_entregas_acima_de_40_min(mecanismo):
    [melhor, *_] = mecanismo["temperatura"]
    assert ENTREGA_40 in melhor.condicoes
    assert melhor.parcela_das_reclamacoes.pct >= 60 and melhor.lift >= 5
    assert melhor.pedidos_no_segmento.pct <= 20      # concentra muito com pouco do movimento


def test_comida_fria_acontece_sexta_a_noite(quando_onde):
    [melhor, *_] = quando_onde["temperatura"]
    assert {SEXTA, NOITE} <= set(melhor.condicoes)
    assert melhor.parcela_das_reclamacoes.pct >= 55
    assert melhor.no_segmento.pct >= 4 * melhor.fora_do_segmento.pct


def test_atraso_acontece_sexta_a_noite(quando_onde):
    [melhor, *_] = quando_onde["atraso"]
    assert {SEXTA, NOITE} <= set(melhor.condicoes)
    assert melhor.parcela_das_reclamacoes.pct >= 40


def test_temas_sem_padrao_plantado_nao_recebem_causa(mecanismo, quando_onde):
    for tema in ("sabor", "embalagem", "quantidade", "pedido_errado"):
        assert mecanismo[tema] == [] and quando_onde[tema] == []


def test_batata_frita_piora_com_entrega_acima_de_40_min(df_avaliacoes, pedidos):
    [melhor, *_] = causas_do_prato(df_avaliacoes, pedidos, "Batata Frita")
    assert ENTREGA_40 in melhor.condicoes
    assert melhor.parcela_das_reclamacoes.pct >= 60
    assert melhor.no_segmento.pct >= 3 * melhor.fora_do_segmento.pct


def test_acai_derrete_em_distancias_longas_mas_com_aviso_de_amostra_pequena(df_avaliacoes, pedidos):
    [melhor, *_] = causas_do_prato(df_avaliacoes, pedidos, "Açaí 500ml")
    assert "a mais de 5 km de distância" in melhor.condicoes
    assert melhor.baixa_confianca
    assert "Amostra pequena" in melhor.texto("reclamações do prato")


def test_pratos_sem_problema_relevante_nao_recebem_causa(df_avaliacoes, pedidos):
    assert causas_do_prato(df_avaliacoes, pedidos, "Pudim") == []
    assert causas_do_prato(df_avaliacoes, pedidos, "Refrigerante Lata") == []


def test_entregas_lentas_se_concentram_na_sexta_a_noite(pedidos):
    padroes = causas_da_entrega_lenta(pedidos)
    sexta = next(p for p in padroes if {SEXTA, NOITE} <= set(p.condicoes))
    assert sexta.lift >= 3
    tempos = comparar_tempos(pedidos, sexta.condicoes)
    assert tempos["entrega"]["no_segmento"] - tempos["entrega"]["demais"] >= 8
    assert tempos["deslocamento"]["no_segmento"] > tempos["deslocamento"]["demais"]


def test_piora_de_outubro_aparece_na_evolucao_da_sexta_a_noite(pedidos):
    mensal = evolucao_tempos(pedidos, (SEXTA, NOITE))
    sexta = mensal[mensal["grupo"] == "No segmento"].set_index("mes")["entrega_media"]
    demais = mensal[mensal["grupo"] == "Demais pedidos"].set_index("mes")["entrega_media"]
    out, antes = pd.Timestamp("2026-10-01"), sexta.drop(pd.Timestamp("2026-10-01"))
    assert sexta[out] - antes.mean() >= 8
    assert abs(demais[out] - demais.drop(out).mean()) < 3


def test_evolucao_do_padrao_soma_as_avaliacoes(df_avaliacoes):
    base = df_avaliacoes[df_avaliacoes["tem_pedido"]]
    evento = base["temas"].map(lambda ts: "atraso" in ts)
    mensal = evolucao_do_padrao(base, evento, (SEXTA, NOITE))
    assert mensal["n"].sum() == len(base) and mensal["k"].sum() == evento.sum()


def test_texto_traz_numeros_e_base(mecanismo):
    frase = mecanismo["temperatura"][0].texto(rotulo_evento_tema("temperatura"))
    assert "reclamações de comida fria" in frase and "avaliações" in frase and "× mais" in frase
    assert "%" in frase and " de " in frase
