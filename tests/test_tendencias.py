import json

import numpy as np
import pandas as pd

from copiloto.analytics.tendencias import alertas_tendencia


def avaliacoes(n_antes: int, n_depois: int, taxa_antes: float, taxa_depois: float, seed: int = 0) -> pd.DataFrame:
    """Avaliações de 100 dias; nos últimos 28 a taxa de citação de 'atraso' muda."""
    rng = np.random.default_rng(seed)
    fim = pd.Timestamp("2026-10-31 12:00")
    datas = list(fim - pd.to_timedelta(rng.uniform(28, 100, n_antes), unit="D")) + list(
        fim - pd.to_timedelta(rng.uniform(0, 27, n_depois), unit="D")
    )
    taxas = [taxa_antes] * n_antes + [taxa_depois] * n_depois
    temas = [["atraso"] if rng.random() < t else [] for t in taxas]
    return pd.DataFrame({"criado_em": datas, "temas": temas})


def test_alerta_quando_a_taxa_sobe_de_forma_consistente():
    [alerta] = alertas_tendencia(avaliacoes(400, 150, 0.10, 0.25))
    assert alerta.tema == "atraso" and alerta.aumento_pct >= 100
    assert alerta.recente.n == 150 and alerta.anterior.n == 400
    assert "subiram" in alerta.texto() and "de 150 avaliações" in alerta.texto()


def test_sem_alerta_quando_estavel():
    assert alertas_tendencia(avaliacoes(400, 150, 0.15, 0.15)) == []


def test_sem_alerta_quando_poucas_reclamacoes_recentes():
    assert alertas_tendencia(avaliacoes(400, 20, 0.01, 0.20, seed=2)) == []


def test_sem_alerta_com_subida_pequena():
    assert alertas_tendencia(avaliacoes(400, 150, 0.20, 0.24)) == []


def test_tabela_vazia_ou_sem_historico():
    assert alertas_tendencia(avaliacoes(0, 0, 0.1, 0.1)) == []
    assert alertas_tendencia(avaliacoes(0, 100, 0.1, 0.3)) == []


def test_alerta_nos_dados_ficticios_vem_do_ataque_de_avaliacoes_falsas(df_avaliacoes, dados):
    gab = json.loads(dados[1].read_text(encoding="utf-8"))["avaliacoes"]
    falsa = df_avaliacoes["avaliacao_id"].map(lambda i: gab[str(i)]["falsa"])
    com_falsas = {a.tema for a in alertas_tendencia(df_avaliacoes)}
    sem_falsas = {a.tema for a in alertas_tendencia(df_avaliacoes[~falsa])}
    assert "atendimento" in com_falsas      # as falsas dizem "atendimento péssimo"
    assert "atendimento" not in sem_falsas
