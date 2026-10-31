"""Detecção de avaliações suspeitas: cada sinal, a soma em níveis e o resultado nos dados fictícios."""
import numpy as np
import pandas as pd
import pytest

from copiloto.analytics.base import carregar_pedidos
from copiloto.analytics.impacto import montar_plano
from copiloto.analytics.suspeitas import (
    MODOS,
    analisar_suspeitas,
    com_suspeitas,
    comparar_metricas,
    contagem_de_sinais,
    dias_de_rajada,
    episodios_suspeitos,
    filtrar_suspeitas,
    nivel_da,
)
from copiloto.analytics.tendencias import alertas_tendencia
from copiloto.validacao import comparar_suspeitas

PALAVRAS = [f"palavra{i}x" for i in range(300)]
FIM = pd.Timestamp("2026-10-31 12:00")


def normais(n: int = 200, seed: int = 0) -> pd.DataFrame:
    """Avaliações comuns: contas antigas, com pedido, textos longos e diferentes, notas altas."""
    rng = np.random.default_rng(seed)
    quando = FIM - pd.to_timedelta(rng.uniform(0, 100, n), unit="D")
    return pd.DataFrame({
        "cliente_id": np.arange(1, n + 1),
        "pedido_id": np.arange(1, n + 1, dtype=float),
        "criado_em": quando,
        "nota": rng.choice([5, 4, 3, 2], n, p=[0.6, 0.25, 0.1, 0.05]),
        "texto": [" ".join(rng.choice(PALAVRAS, 9)) for _ in range(n)],
        "conta_criada_em": quando - pd.Timedelta(days=200),
        "pedidos_da_conta": 4,
    })


def ataque(n: int = 15, primeiro_cliente: int = 1000) -> pd.DataFrame:
    """n avaliações copiadas, nota 1, de contas novas e sem pedido, no mesmo dia."""
    quando = pd.Timestamp("2026-10-14 10:00") + pd.to_timedelta(np.linspace(0, 11, n), unit="h")
    return pd.DataFrame({
        "cliente_id": np.arange(primeiro_cliente, primeiro_cliente + n),
        "pedido_id": np.nan,
        "criado_em": quando,
        "nota": 1,
        "texto": "Péssimo restaurante! Comida horrível, passei mal depois de comer. Não recomendo a ninguém!",
        "conta_criada_em": quando - pd.Timedelta(days=1),
        "pedidos_da_conta": 0,
    })


def junto(*partes: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(partes, ignore_index=True).sort_values("criado_em", ignore_index=True)


# --- Níveis ---------------------------------------------------------------------------------
@pytest.mark.parametrize("pontos,nivel", [(0, "nenhum"), (1, "baixo"), (2, "baixo"), (3, "médio"), (4, "médio"), (5, "alto"), (9, "alto")])
def test_nivel_pela_soma_dos_pontos(pontos, nivel):
    assert nivel_da(pontos) == nivel


def test_ataque_copiado_e_alto_e_avaliacoes_normais_ficam_de_fora():
    df = com_suspeitas(junto(normais(), ataque()))
    falsas = df[df["cliente_id"] >= 1000]
    assert (falsas["suspeita_nivel"] == "alto").all()
    assert set(falsas["suspeita_sinais"].map(tuple)) == {("sem_pedido", "conta_nova", "rajada", "texto_parecido")}
    assert (df[df["cliente_id"] < 1000]["suspeita_nivel"].isin(["nenhum", "baixo"])).all()


def test_cada_alerta_traz_motivos_com_numeros():
    df = com_suspeitas(junto(normais(), ataque()))
    motivos = df[df["cliente_id"] == 1000]["suspeita_motivos"].iloc[0]
    assert len(motivos) == 4
    assert any("Sem pedido correspondente" in m for m in motivos)
    assert any("Conta criada há 1 dia" in m and "sem nenhum pedido" in m for m in motivos)
    assert any("15 avaliações de nota 1–2" in m for m in motivos)
    assert any("outras 14 avaliações" in m and "14 outras contas" in m for m in motivos)


# --- Cada sinal sozinho nunca passa de "médio" -------------------------------------------------
def com_alteracao(**campos) -> pd.Series:
    base = normais()
    base.loc[0, list(campos)] = list(campos.values())
    return com_suspeitas(base).loc[0]


def test_sem_pedido_sozinho_e_baixo():
    r = com_alteracao(pedido_id=np.nan)
    assert r["suspeita_sinais"] == ["sem_pedido"] and r["suspeita_nivel"] == "baixo"


def test_conta_nova_sozinha_e_baixa():
    base = normais()
    base.loc[0, "conta_criada_em"] = base.loc[0, "criado_em"] - pd.Timedelta(hours=3)
    base.loc[0, "pedidos_da_conta"] = 1
    r = com_suspeitas(base).loc[0]
    assert r["suspeita_sinais"] == ["conta_nova"] and r["suspeita_nivel"] == "baixo"
    assert "menos de 1 dia" in r["suspeita_motivos"][0] and "com 1 pedido" in r["suspeita_motivos"][0]


def test_conta_com_historico_nao_e_nova_mesmo_criada_ha_pouco():
    base = normais()
    base.loc[0, "conta_criada_em"] = base.loc[0, "criado_em"] - pd.Timedelta(days=2)
    base.loc[0, "pedidos_da_conta"] = 5
    assert com_suspeitas(base).loc[0, "suspeita_sinais"] == []


def test_sem_pedido_mais_conta_nova_e_so_medio_no_maximo():
    base = normais()
    base.loc[0, ["pedido_id", "pedidos_da_conta"]] = [np.nan, 0]
    base.loc[0, "conta_criada_em"] = base.loc[0, "criado_em"] - pd.Timedelta(days=1)
    r = com_suspeitas(base).loc[0]
    assert r["suspeita_pontos"] == 3 and r["suspeita_nivel"] == "médio"


# --- Textos parecidos ----------------------------------------------------------------------------
TEXTO_LONGO = "Péssimo restaurante! Comida horrível, passei mal depois de comer. Não recomendo a ninguém!"


def copias(n: int, contas: int, dias: float = 2.0, texto: str = TEXTO_LONGO) -> pd.DataFrame:
    df = ataque(n)
    df["criado_em"] = pd.Timestamp("2026-09-01") + pd.to_timedelta(np.linspace(0, dias * 24, n), unit="h")
    df["cliente_id"] = [5000 + (i % contas) for i in range(n)]
    df["pedido_id"] = 9000 + np.arange(n, dtype=float)       # com pedido, para isolar o sinal de texto
    df["conta_criada_em"] = df["criado_em"] - pd.Timedelta(days=300)
    df["pedidos_da_conta"] = 5
    df["nota"] = 5
    df["texto"] = texto
    return df


def sinais_das_copias(df_copias: pd.DataFrame) -> set:
    resultado = com_suspeitas(junto(normais(), df_copias))
    return {s for lista in resultado[resultado["cliente_id"] >= 5000]["suspeita_sinais"] for s in lista}


def test_texto_copiado_por_varias_contas_e_sinalizado_como_medio():
    df = com_suspeitas(junto(normais(), copias(6, contas=6)))
    copiadas = df[df["cliente_id"] >= 5000]
    assert (copiadas["suspeita_sinais"].map(tuple) == ("texto_parecido",)).all()
    assert (copiadas["suspeita_nivel"] == "médio").all()


def test_mesma_conta_repetindo_o_texto_nao_conta_como_coordenacao():
    assert "texto_parecido" not in sinais_das_copias(copias(6, contas=1))


def test_duas_contas_nao_bastam():
    assert "texto_parecido" not in sinais_das_copias(copias(6, contas=2))


def test_textos_curtos_e_genericos_nao_sao_sinalizados():
    assert sinais_das_copias(copias(10, contas=10, texto="Muito bom! Recomendo.")) == set()


def test_texto_igual_espalhado_por_meses_nao_e_sinalizado():
    assert "texto_parecido" not in sinais_das_copias(copias(6, contas=6, dias=24 * 60))


def test_pequenas_variacoes_ainda_contam_como_parecidas():
    variacoes = [TEXTO_LONGO.replace("Péssimo", p).replace("!", "!!" if i % 2 else "!")
                 for i, p in enumerate(["Péssimo", "Horrível", "Terrível", "Péssimo", "Horrível", "Terrível"])]
    df = copias(6, contas=6)
    df["texto"] = variacoes
    assert "texto_parecido" in sinais_das_copias(df)


# --- Rajada --------------------------------------------------------------------------------------
def com_baixas_no_dia(k: int) -> pd.DataFrame:
    base = normais(seed=3)
    base = base[base["nota"] > 2].reset_index(drop=True)            # fundo quase sem notas baixas
    extra = base.sample(k, random_state=1).copy() if k else base.iloc[:0].copy()
    extra["nota"] = 1
    extra["criado_em"] = pd.Timestamp("2026-10-20 10:00") + pd.to_timedelta(np.arange(k), unit="min")
    return junto(base, extra)


def test_dia_com_poucas_notas_baixas_nao_e_rajada():
    assert dias_de_rajada(com_baixas_no_dia(4)) == {}


def test_dia_com_muitas_notas_baixas_e_rajada():
    achados = dias_de_rajada(com_baixas_no_dia(12))
    assert list(achados) == [pd.Timestamp("2026-10-20")] and achados[pd.Timestamp("2026-10-20")][0] == 12


def test_rajada_so_marca_notas_baixas_do_dia():
    df = com_baixas_no_dia(12)
    df.loc[df.index[-1], "nota"] = 5                                # uma avaliação boa no mesmo dia
    r = com_suspeitas(df)
    no_dia = r[r["criado_em"].dt.normalize() == pd.Timestamp("2026-10-20")]
    assert (no_dia[no_dia["nota"] <= 2]["suspeita_sinais"].map(lambda s: "rajada" in s)).all()
    assert not no_dia[no_dia["nota"] > 2]["suspeita_sinais"].map(lambda s: "rajada" in s).any()


def test_tabela_vazia():
    vazio = com_suspeitas(normais().iloc[:0])
    assert vazio.empty and {"suspeita_nivel", "suspeita_motivos"} <= set(vazio.columns)


# --- Com e sem suspeitas ----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def misto():
    df = com_suspeitas(junto(normais(), ataque()))
    df["sentimento"] = np.where(df["nota"] <= 2, "negativo", "positivo")
    return df


def test_filtro_tira_so_o_que_o_modo_pede(misto):
    assert len(filtrar_suspeitas(misto, "todas")) == len(misto)
    assert len(filtrar_suspeitas(misto, "so_altas")) == len(misto) - 15
    assert len(filtrar_suspeitas(misto, "medias_e_altas")) == len(misto) - 15
    assert set(MODOS) == {"todas", "medias_e_altas", "so_altas"}
    assert len(misto) == 215                                           # o filtro não altera a tabela original


def test_comparacao_mostra_nota_e_negativas_com_e_sem(misto):
    c = comparar_metricas(misto)
    assert c.removidas == 15 and c.avaliacoes_sem_suspeitas == 200
    assert c.diferenca_nota > 0.2 and c.nota_sem_suspeitas > c.nota_todas
    assert c.negativas_todas.n == 215 and c.negativas_sem_suspeitas.n == 200
    assert c.negativas_sem_suspeitas.pct < c.negativas_todas.pct


def test_episodio_resume_o_ataque(misto):
    [ep] = episodios_suspeitos(misto)
    assert ep.avaliacoes == 15 and ep.altas == 15 and ep.nota_media == 1.0
    assert ep.inicio.date() == pd.Timestamp("2026-10-14").date()
    texto = ep.texto()
    assert "15 avaliações suspeitas em 14/10" in texto and "15 (100%) não têm pedido" in texto


def test_suspeitas_isoladas_nao_formam_episodio():
    pequeno = com_suspeitas(junto(normais(), ataque(n=4)))
    assert episodios_suspeitos(pequeno) == []


# --- Dados fictícios (comparados ao gabarito do gerador) -------------------------------------------
def test_pega_quase_todas_as_falsas_com_poucos_falsos_alarmes(df_suspeitas, dados):
    m = comparar_suspeitas(df_suspeitas, dados[1])
    assert m["avaliacoes_falsas"] == 46
    assert m["medio_ou_alto"]["revocacao"] >= 0.90
    assert m["medio_ou_alto"]["precisao"] >= 0.90
    assert m["alto"]["precisao"] >= 0.95
    assert m["medio_ou_alto"]["genuinas_acusadas"] <= 3


def test_avaliacoes_genuinas_com_injecao_nao_sao_confundidas_com_ataque(df_suspeitas):
    injecoes = df_suspeitas[df_suspeitas["injecao"]]
    assert len(injecoes) == 2 and injecoes["suspeita_nivel"].isin(["nenhum", "baixo"]).all()


def test_dados_ficticios_tem_um_unico_episodio_no_periodo_do_ataque(df_suspeitas):
    [ep] = episodios_suspeitos(df_suspeitas)
    assert ep.inicio.date() >= pd.Timestamp("2026-10-14").date() and ep.fim.date() <= pd.Timestamp("2026-10-17").date()
    assert ep.avaliacoes >= 40 and ep.nota_media <= 1.3


def test_todo_alerta_tem_motivo_para_cada_sinal(df_suspeitas):
    marcadas = df_suspeitas[df_suspeitas["suspeita_nivel"] != "nenhum"]
    assert len(marcadas) > 0
    assert (marcadas["suspeita_motivos"].map(len) == marcadas["suspeita_sinais"].map(len)).all()
    assert contagem_de_sinais(marcadas)["texto_parecido"] >= 40


def test_sem_as_suspeitas_a_nota_sobe_e_o_alerta_de_atendimento_some(df_suspeitas, con_classificada):
    sem = filtrar_suspeitas(df_suspeitas, "medias_e_altas")
    assert comparar_metricas(df_suspeitas).diferenca_nota >= 0.15
    assert "atendimento" in {a.tema for a in alertas_tendencia(df_suspeitas)}
    assert "atendimento" not in {a.tema for a in alertas_tendencia(sem)}
    pedidos = carregar_pedidos(con_classificada)
    assert montar_plano(sem, pedidos).nota_atual - montar_plano(df_suspeitas, pedidos).nota_atual >= 0.05
