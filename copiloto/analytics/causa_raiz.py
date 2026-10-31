"""Causa raiz: em que condições do pedido (dia, turno, tempos, distância) cada problema se concentra.

Para um evento (ex.: "a avaliação cita comida fria") o módulo testa todas as combinações de até três
condições e guarda as que o concentram de forma consistente. Cada candidato recebe:

- parcela das reclamações: quantas das reclamações vêm do segmento (k de K);
- taxa dentro do segmento contra fora dele, e quantas vezes maior é (lift);
- peso do segmento nos pedidos: o quanto ele é grande no movimento total;
- p-valor do teste exato de Fisher, corrigido pelo número de candidatos testados (Bonferroni),
  para que o acaso não seja apresentado como padrão.

Os candidatos são ordenados por cobertura x precisão (parcela das reclamações que o segmento pega vezes a
taxa do problema dentro dele), com leve preferência por explicações mais simples, e os que apenas repetem
outro já escolhido são descartados. As reclamações em excesso (k menos o esperado se o segmento tivesse a
taxa de fora) acompanham cada padrão como medida de impacto.

Base dos percentuais: avaliações de pedidos. Quem avalia não é uma amostra aleatória dos clientes
(quem teve problema tende a avaliar mais), então as taxas descrevem as avaliações, não todos os pedidos.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

from copiloto.dominio import ROTULO_TEMA, TEMAS
from copiloto.stats import Proporcao, formatar_nota, formatar_pct, pct_com_n

MIN_N_SEGMENTO = 10
MIN_EVENTOS_SEGMENTO = 6
MIN_EVENTOS_TOTAIS = 12
LIFT_MINIMO = 1.5
ALFA = 0.05
MAX_CONDICOES = 3
PENALIDADE_POR_CONDICAO = 0.10
SOBREPOSICAO_MAXIMA = 0.5

NOMES_DIA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
ROTULO_TURNO = {"almoço": "no almoço", "tarde": "à tarde", "noite": "à noite"}
LIMIARES_ENTREGA = (30, 40, 50)
LIMIARES_DISTANCIA = (3, 5)
LIMIARES_PREPARO = (22, 28)


@dataclass(frozen=True)
class Padrao:
    condicoes: tuple[str, ...]
    no_segmento: Proporcao            # avaliações do segmento que têm o evento (k de n)
    fora_do_segmento: Proporcao       # idem, nas demais avaliações
    parcela_das_reclamacoes: Proporcao  # do total de reclamações (K), quantas vêm do segmento
    pedidos_no_segmento: Proporcao | None  # pedidos do segmento entre todos os pedidos
    lift: float
    excesso: float                    # reclamações acima do esperado se o segmento fosse igual aos demais
    p_ajustado: float

    @property
    def segmento(self) -> str:
        return "pedidos " + ", ".join(self.condicoes)

    @property
    def baixa_confianca(self) -> bool:
        return self.no_segmento.baixa_confianca

    @property
    def evidencia(self) -> str:
        """Quão improvável é que o padrão seja acaso, em linguagem simples (p já corrigido)."""
        if self.p_ajustado < 0.001:
            return "chance de ser acaso: menos de 1 em 1.000"
        if self.p_ajustado < 0.01:
            return "chance de ser acaso: menos de 1 em 100"
        return "chance de ser acaso: menos de 1 em 20"

    def texto(self, rotulo_evento: str, *, unidade: str = "avaliações", predicado: str = "citam o problema") -> str:
        """Frase pronta para o dono. `rotulo_evento`: ex. 'reclamações de comida fria'."""
        k, K = self.parcela_das_reclamacoes.k, self.parcela_das_reclamacoes.n
        partes = [
            f"{formatar_pct(self.parcela_das_reclamacoes.pct)} das {rotulo_evento} ({k} de {K}) "
            f"vêm de {self.segmento}"
        ]
        if self.pedidos_no_segmento is not None:
            partes[0] += f", que são {formatar_pct(self.pedidos_no_segmento.pct)} dos pedidos"
        partes[0] += "."
        partes.append(
            f"Nesse grupo, {self.no_segmento.texto(unidade=unidade)} {predicado}, "
            f"contra {formatar_pct(self.fora_do_segmento.pct)} nos demais ({formatar_nota(self.lift, 1)}× mais)."
        )
        if self.baixa_confianca:
            partes.append("Amostra pequena: trate como indício, não como conclusão.")
        return " ".join(partes)


# --- Condições ------------------------------------------------------------------------------
TODAS_DIMENSOES = ("dia", "turno", "entrega", "distancia", "preparo")
# "Quando e onde": o que o restaurante não controla pelo cardápio, sem os tempos que são consequência.
DIMENSOES_QUANDO_ONDE = ("dia", "turno", "distancia")


def _condicoes(d: pd.DataFrame, dimensoes: tuple[str, ...] = TODAS_DIMENSOES) -> dict[str, list[tuple[str, np.ndarray]]]:
    """dimensão -> [(rótulo, máscara)]. Dentro de uma dimensão as condições são alternativas."""
    todas = {
        "dia": [(f"de {NOMES_DIA[i]}", (d["dia_semana"] == i).to_numpy()) for i in range(7)],
        "turno": [(r, (d["turno"] == t).to_numpy()) for t, r in ROTULO_TURNO.items()],
        "entrega": [(f"com entrega acima de {x} min", (d["tempo_entrega_min"] > x).to_numpy()) for x in LIMIARES_ENTREGA],
        "distancia": [(f"a mais de {x} km de distância", (d["distancia_km"] > x).to_numpy()) for x in LIMIARES_DISTANCIA],
        "preparo": [(f"com preparo acima de {x} min", (d["tempo_preparo_min"] > x).to_numpy()) for x in LIMIARES_PREPARO],
    }
    return {dim: todas[dim] for dim in dimensoes}


def _candidatos(conds: dict[str, list[tuple[str, np.ndarray]]], max_condicoes: int):
    dims = list(conds)
    for r in range(1, max_condicoes + 1):
        for dims_sel in itertools.combinations(dims, r):
            for escolha in itertools.product(*(conds[d] for d in dims_sel)):
                yield tuple(rot for rot, _ in escolha), np.logical_and.reduce([m for _, m in escolha])


def mascara_do_padrao(d: pd.DataFrame, condicoes: tuple[str, ...]) -> np.ndarray:
    """Recalcula, em qualquer tabela com as colunas do pedido, quem pertence ao segmento."""
    por_rotulo = {rot: m for lista in _condicoes(d).values() for rot, m in lista}
    return np.logical_and.reduce([por_rotulo[c] for c in condicoes])


# --- Busca ----------------------------------------------------------------------------------
def buscar_padroes(
    base: pd.DataFrame,
    evento: pd.Series,
    pedidos: pd.DataFrame | None = None,
    *,
    top: int = 3,
    max_condicoes: int = MAX_CONDICOES,
    dimensoes: tuple[str, ...] = TODAS_DIMENSOES,
) -> list[Padrao]:
    """Segmentos em que o evento é mais frequente do que no resto. Lista vazia = nada consistente."""
    ev = evento.to_numpy(dtype=bool)
    n_total, k_total = len(base), int(ev.sum())
    if n_total == 0 or k_total < MIN_EVENTOS_TOTAIS:
        return []

    unicos: dict[bytes, tuple[tuple[str, ...], np.ndarray, int, int]] = {}
    for chave, mascara in _candidatos(_condicoes(base, dimensoes), max_condicoes):
        n = int(mascara.sum())
        if n < MIN_N_SEGMENTO:
            continue
        k = int((mascara & ev).sum())
        if k < MIN_EVENTOS_SEGMENTO:
            continue
        assinatura = mascara.tobytes()
        if assinatura not in unicos or len(chave) < len(unicos[assinatura][0]):
            unicos[assinatura] = (chave, mascara, n, k)  # mesmo grupo de pessoas: fica a explicação mais curta

    n_testes = len(unicos)
    mascaras_pedidos = (
        dict(_candidatos(_condicoes(pedidos, dimensoes), max_condicoes)) if pedidos is not None else {}
    )
    candidatos = []
    for chave, mascara, n, k in unicos.values():
        fora_n, fora_k = n_total - n, k_total - k
        taxa_dentro = k / n
        taxa_fora = fora_k / fora_n if fora_n else 0.0
        if taxa_dentro <= taxa_fora:
            continue
        lift = ((k + 0.5) / (n + 1)) / ((fora_k + 0.5) / (fora_n + 1))
        if lift < LIFT_MINIMO:
            continue
        p = fisher_exact([[k, n - k], [fora_k, fora_n - fora_k]], alternative="greater").pvalue
        p_ajustado = min(1.0, float(p) * n_testes)
        if p_ajustado >= ALFA:
            continue
        excesso = k - n * taxa_fora
        pedidos_seg = None
        if pedidos is not None:
            pedidos_seg = pct_com_n(int(mascaras_pedidos[chave].sum()), len(pedidos))
        # Cobertura x precisão: o segmento precisa pegar muitas reclamações (k/K) e, dentro dele, o
        # problema precisa ser frequente (k/n). Um filtro largo demais ("entrega acima de 30 min")
        # cobre quase tudo mas dilui a taxa; um estreito demais acerta a taxa mas deixa reclamações de fora.
        relevancia = (k / k_total) * taxa_dentro
        candidatos.append((
            relevancia / (1 + PENALIDADE_POR_CONDICAO * (len(chave) - 1)),
            mascara,
            Padrao(chave, pct_com_n(k, n), pct_com_n(fora_k, fora_n), pct_com_n(k, k_total),
                   pedidos_seg, float(lift), float(excesso), p_ajustado),
        ))

    escolhidos: list[tuple[np.ndarray, Padrao]] = []
    for _, mascara, padrao in sorted(candidatos, key=lambda c: -c[0]):
        eventos_aqui = mascara & ev
        if any((eventos_aqui & m).sum() / max(1, eventos_aqui.sum()) >= SOBREPOSICAO_MAXIMA for m, _ in escolhidos):
            continue  # repete um padrão já escolhido
        escolhidos.append((mascara, padrao))
        if len(escolhidos) == top:
            break
    return [p for _, p in escolhidos]


# --- Eventos de interesse -------------------------------------------------------------------
def _com_pedido(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["tem_pedido"]]


def causas_por_tema(
    df: pd.DataFrame, pedidos: pd.DataFrame, *, top: int = 3, dimensoes: tuple[str, ...] = TODAS_DIMENSOES
) -> dict[str, list[Padrao]]:
    """Para cada tema de problema, os segmentos de pedido que o concentram.

    Com todas as dimensões, o resultado costuma apontar o tempo de entrega (o mecanismo). Com
    `DIMENSOES_QUANDO_ONDE`, aponta em que dia, turno e distância o problema ocorre.
    """
    base = _com_pedido(df)
    return {
        t: buscar_padroes(base, base["temas"].map(lambda ts, t=t: t in ts), pedidos, top=top, dimensoes=dimensoes)
        for t in TEMAS
    }


def causas_da_entrega_lenta(pedidos: pd.DataFrame, *, limiar_min: int = 40, top: int = 3) -> list[Padrao]:
    """Quando e onde as entregas passam do limite. Usa todos os pedidos, não só os avaliados."""
    evento = pedidos["tempo_entrega_min"] > limiar_min
    return buscar_padroes(pedidos, evento, pedidos, top=top, dimensoes=DIMENSOES_QUANDO_ONDE)


def comparar_tempos(pedidos: pd.DataFrame, condicoes: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """Médias de preparo, deslocamento e entrega dentro e fora de um segmento (descrição, não teste)."""
    dentro = mascara_do_padrao(pedidos, condicoes)
    d = pedidos.assign(deslocamento_min=pedidos["tempo_entrega_min"] - pedidos["tempo_preparo_min"])
    colunas = {"preparo": "tempo_preparo_min", "deslocamento": "deslocamento_min", "entrega": "tempo_entrega_min"}
    return {
        nome: {"no_segmento": float(d.loc[dentro, col].mean()), "demais": float(d.loc[~dentro, col].mean())}
        for nome, col in colunas.items()
    }


def causas_do_prato(df: pd.DataFrame, pedidos: pd.DataFrame, prato: str, *, top: int = 3) -> list[Padrao]:
    """Segmentos em que pedidos com o prato geram avaliação com problema no prato.

    Base: avaliações de pedidos que incluíram o prato, citem-no ou não.
    """
    base = _com_pedido(df)
    base = base[base["itens"].map(lambda itens: prato in itens)]
    evento = base["pratos"].map(lambda ps: any(p["prato"] == prato and p["problemas"] for p in ps))
    pedidos_do_prato = pedidos[pedidos["itens"].map(lambda itens: prato in itens)]
    return buscar_padroes(base, evento, pedidos_do_prato, top=top)


def evolucao_tempos(pedidos: pd.DataFrame, condicoes: tuple[str, ...]) -> pd.DataFrame:
    """Tempo médio de entrega por mês, dentro e fora de um segmento (mostra piora ao longo do tempo)."""
    dentro = mascara_do_padrao(pedidos, condicoes)
    mes = pedidos["criado_em"].dt.to_period("M").dt.start_time
    linhas = []
    for nome, grupo in (("No segmento", dentro), ("Demais pedidos", ~dentro)):
        agregado = pedidos[grupo].groupby(mes[grupo])["tempo_entrega_min"].agg(["mean", "count"])
        for m, linha in agregado.iterrows():
            linhas.append({"mes": m, "grupo": nome, "entrega_media": float(linha["mean"]), "pedidos": int(linha["count"])})
    return pd.DataFrame(linhas)


def rotulo_evento_tema(tema: str) -> str:
    return f"reclamações de {ROTULO_TEMA[tema].lower()}"


def evolucao_do_padrao(base: pd.DataFrame, evento: pd.Series, condicoes: tuple[str, ...]) -> pd.DataFrame:
    """Por mês: avaliações do segmento e do resto, com quantas têm o evento."""
    dentro = mascara_do_padrao(base, condicoes)
    ev = evento.to_numpy(dtype=bool)
    mes = base["criado_em"].dt.to_period("M").dt.start_time.to_numpy()
    linhas = []
    for m in sorted(set(mes)):
        no_mes = mes == m
        for nome, grupo in (("No segmento", dentro), ("Demais pedidos", ~dentro)):
            sel = no_mes & grupo
            linhas.append({"mes": pd.Timestamp(m), "grupo": nome, "k": int((sel & ev).sum()), "n": int(sel.sum())})
    return pd.DataFrame(linhas).assign(pct=lambda d: 100 * d["k"] / d["n"].where(d["n"] > 0))
