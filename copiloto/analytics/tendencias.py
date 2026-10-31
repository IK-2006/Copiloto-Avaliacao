"""Alertas de tendência: temas de reclamação que cresceram na janela mais recente."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from scipy.stats import fisher_exact

from copiloto.dominio import ROTULO_TEMA, TEMAS
from copiloto.stats import Proporcao, formatar_pct, pct_com_n

MIN_RECLAMACOES_RECENTES = 6
AUMENTO_MINIMO = 0.40
ALFA = 0.05


@dataclass(frozen=True)
class Alerta:
    tema: str
    recente: Proporcao       # avaliações da janela recente que citam o tema
    anterior: Proporcao      # idem, em todo o período anterior
    aumento_pct: float       # variação relativa da taxa, em %
    p_valor: float
    dias: int

    def texto(self) -> str:
        return (
            f"Reclamações de {ROTULO_TEMA[self.tema].lower()} subiram {formatar_pct(self.aumento_pct)}: "
            f"{self.recente.texto()} nos últimos {self.dias} dias, "
            f"contra {self.anterior.texto()} no período anterior."
        )


def alertas_tendencia(df: pd.DataFrame, *, dias: int = 28) -> list[Alerta]:
    """Temas cuja taxa de citação subiu pelo menos 40% na janela recente, de forma estatisticamente consistente."""
    if df.empty:
        return []
    corte = df["criado_em"].max().normalize() - pd.Timedelta(days=dias - 1)
    recente, anterior = df[df["criado_em"] >= corte], df[df["criado_em"] < corte]
    if recente.empty or anterior.empty:
        return []

    alertas = []
    for tema in TEMAS:
        k_r = int(recente["temas"].map(lambda ts, t=tema: t in ts).sum())
        k_a = int(anterior["temas"].map(lambda ts, t=tema: t in ts).sum())
        n_r, n_a = len(recente), len(anterior)
        if k_r < MIN_RECLAMACOES_RECENTES or k_a == 0:
            continue
        taxa_r, taxa_a = k_r / n_r, k_a / n_a
        aumento = taxa_r / taxa_a - 1
        if aumento < AUMENTO_MINIMO:
            continue
        p = float(fisher_exact([[k_r, n_r - k_r], [k_a, n_a - k_a]], alternative="greater").pvalue)
        if p < ALFA:
            alertas.append(Alerta(tema, pct_com_n(k_r, n_r), pct_com_n(k_a, n_a), 100 * aumento, p, dias))
    return sorted(alertas, key=lambda a: a.p_valor)
