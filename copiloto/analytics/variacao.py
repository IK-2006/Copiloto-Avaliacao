"""Por que a nota mudou em um mês? Separa o efeito das avaliações suspeitas do restante e aponta o que mudou.

Compara o mês com todos os meses anteriores e responde, só com contas:
1. quanto da variação vem das avaliações suspeitas e quanto sobra sem elas;
2. quais temas de reclamação ficaram mais frequentes (teste de Fisher), já sem as suspeitas;
3. em que parte da operação o tempo de entrega piorou (teste t de Welch), nos segmentos de pedido
   encontrados pela causa raiz.

É descrição de coincidências no tempo, não prova de causa.
"""
from __future__ import annotations

import pandas as pd
from scipy.stats import fisher_exact, ttest_ind

from copiloto.analytics.causa_raiz import causas_da_entrega_lenta, mascara_do_padrao
from copiloto.analytics.suspeitas import filtrar_suspeitas
from copiloto.dominio import ROTULO_TEMA, TEMAS
from copiloto.stats import pct_com_n

MIN_AVALIACOES = 20
MIN_RECLAMACOES = 6
AUMENTO_MINIMO = 0.40
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]


def rotulo_mes(mes: str) -> str:
    ano, numero = mes.split("-")
    return f"{MESES[int(numero) - 1]} de {ano}"


def _prop(k: int, n: int) -> dict:
    p = pct_com_n(int(k), int(n))
    return {"k": p.k, "n": p.n, "pct": round(p.pct, 1)}


def _nota(d: pd.DataFrame) -> float:
    return round(float(d["nota"].mean()), 2)


def explicar_variacao(todas: pd.DataFrame, pedidos: pd.DataFrame, mes: str) -> dict:
    """`todas`: avaliações com as colunas de suspeitas. `mes`: 'AAAA-MM'. Sempre devolve um dict."""
    inicio = pd.Timestamp(f"{mes}-01")
    fim = inicio + pd.offsets.MonthBegin(1)
    no_mes = todas[(todas["criado_em"] >= inicio) & (todas["criado_em"] < fim)]
    antes = todas[todas["criado_em"] < inicio]
    if len(no_mes) < MIN_AVALIACOES or len(antes) < MIN_AVALIACOES:
        return {
            "mes": mes, "sem_dados": True,
            "motivo": f"Há {len(no_mes)} avaliações em {rotulo_mes(mes)} e {len(antes)} nos meses anteriores; "
                      f"são necessárias pelo menos {MIN_AVALIACOES} em cada período.",
        }

    sem_no_mes, sem_antes = filtrar_suspeitas(no_mes, "medias_e_altas"), filtrar_suspeitas(antes, "medias_e_altas")
    queda_total = _nota(antes) - _nota(no_mes)
    queda_sem = _nota(sem_antes) - _nota(sem_no_mes)
    suspeitas_mes = no_mes[no_mes["suspeita_nivel"].isin(["médio", "alto"])]
    resultado = {
        "mes": mes, "sem_dados": False,
        "nota": {
            "todas": {"meses_anteriores": _nota(antes), "no_mes": _nota(no_mes), "queda": round(queda_total, 2)},
            "sem_suspeitas": {"meses_anteriores": _nota(sem_antes), "no_mes": _nota(sem_no_mes), "queda": round(queda_sem, 2)},
            "efeito_das_suspeitas": round(queda_total - queda_sem, 2),
        },
        "suspeitas_no_mes": {
            "avaliacoes": _prop(len(suspeitas_mes), len(no_mes)),
            "nota_media": _nota(suspeitas_mes) if len(suspeitas_mes) else None,
        },
    }

    temas = []
    for tema in TEMAS:
        k_m = int(sem_no_mes["temas"].map(lambda ts, t=tema: t in ts).sum())
        k_a = int(sem_antes["temas"].map(lambda ts, t=tema: t in ts).sum())
        n_m, n_a = len(sem_no_mes), len(sem_antes)
        if not n_m or not n_a or not k_a:
            continue
        aumento = (k_m / n_m) / (k_a / n_a) - 1
        p = float(fisher_exact([[k_m, n_m - k_m], [k_a, n_a - k_a]], alternative="greater").pvalue)
        temas.append({
            "tema": tema, "rotulo": ROTULO_TEMA[tema], "no_mes": _prop(k_m, n_m), "meses_anteriores": _prop(k_a, n_a),
            "aumento_pct": round(100 * aumento, 0),
            "significativo": bool(p < 0.05 and k_m >= MIN_RECLAMACOES and aumento >= AUMENTO_MINIMO),
        })
    resultado["temas"] = sorted(temas, key=lambda t: -t["aumento_pct"])

    tirados = set(todas["pedido_id"].dropna().astype(int)) - set(filtrar_suspeitas(todas, "medias_e_altas")["pedido_id"].dropna().astype(int))
    reais = pedidos[~pedidos["pedido_id"].isin(tirados)]
    ped_mes = reais[(reais["criado_em"] >= inicio) & (reais["criado_em"] < fim)]
    ped_antes = reais[reais["criado_em"] < inicio]
    entrega = {"pedidos_no_mes": len(ped_mes), "segmentos": []}
    if len(ped_mes) >= MIN_AVALIACOES and len(ped_antes) >= MIN_AVALIACOES:
        entrega["geral"] = {
            "meses_anteriores": round(float(ped_antes["tempo_entrega_min"].mean()), 1),
            "no_mes": round(float(ped_mes["tempo_entrega_min"].mean()), 1),
        }
        for padrao in causas_da_entrega_lenta(reais):
            a = ped_antes[mascara_do_padrao(ped_antes, padrao.condicoes)]["tempo_entrega_min"]
            m = ped_mes[mascara_do_padrao(ped_mes, padrao.condicoes)]["tempo_entrega_min"]
            if len(a) < 10 or len(m) < 10:
                continue
            diferenca = float(m.mean() - a.mean())
            p = float(ttest_ind(m, a, equal_var=False, alternative="greater").pvalue)
            if diferenca >= 5 and p < 0.01:
                entrega["segmentos"].append({
                    "segmento": padrao.segmento, "meses_anteriores": round(float(a.mean()), 1),
                    "no_mes": round(float(m.mean()), 1), "diferenca_min": round(diferenca, 1),
                    "pedidos_no_mes": int(len(m)),
                })
    resultado["entrega"] = entrega
    return resultado
