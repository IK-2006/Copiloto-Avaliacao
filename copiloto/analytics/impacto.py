"""Plano de ação priorizado pelo efeito estimado na nota média.

Como a estimativa é feita (e o que ela não é):

1. Referência: a nota média das avaliações que não citam nenhum problema (`nota_referencia`).
2. Cada reclamação (avaliação, tema) é uma unidade que uma ação pode resolver. Se uma avaliação cita
   vários temas, a distância entre a nota dela e a referência é dividida igualmente entre eles.
3. "Resolver" uma reclamação é supor que a avaliação passaria a valer a parcela correspondente dessa
   distância. Avaliações que já estão acima da referência não mudam (a nota nunca cai).
4. As ações são ordenadas de forma gulosa: a cada passo entra a que mais eleva a nota *dado o que as
   anteriores já resolveram*, para que reclamações compartilhadas não sejam contadas duas vezes.
5. O ganho vem em dois cenários: o completo (as avaliações voltam à nota de referência) e o
   conservador (metade disso, já que nem todo cliente volta a dar a nota de quem nunca reclamou).

É uma estimativa por contrafactual simples, não uma previsão: assume que quem reclamou de X avaliaria
como quem não reclama de nada se X sumisse, e que o resto fica igual. Não mede o efeito de nenhuma
medida específica.

As ações vêm de três fontes: segmentos da causa raiz (quando e onde o problema ocorre; temas que
compartilham o mesmo segmento viram uma ação só), pratos com problemas citados, e o que sobra de cada
tema fora dessas duas.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from copiloto.analytics.causa_raiz import (
    DIMENSOES_QUANDO_ONDE,
    Padrao,
    causas_por_tema,
    mascara_do_padrao,
)
from copiloto.stats import Proporcao, pct_com_n

MIN_INSTANCIAS = 6
MIN_GANHO = 0.005
FATOR_CONSERVADOR = 0.5
PADROES_POR_TEMA = 2

SUBSTANTIVO_TEMA = {
    "atraso": "atrasos",
    "temperatura": "comida fria",
    "textura": "comida murcha ou mole",
    "embalagem": "problemas de embalagem",
    "sabor": "reclamações de sabor",
    "quantidade": "reclamações de quantidade",
    "atendimento": "problemas de atendimento",
    "pedido_errado": "pedidos errados",
}


def _lista_em_portugues(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


@dataclass(frozen=True)
class Candidato:
    tipo: str                                   # "segmento" | "prato" | "residual"
    titulo: str
    instancias: frozenset[tuple[int, str]]      # (posição da avaliação, tema)
    temas: tuple[str, ...] = ()
    prato: str | None = None
    padroes: tuple[tuple[str, Padrao], ...] = ()          # causa raiz que originou o candidato, por tema
    problemas_do_prato: tuple[tuple[str, int], ...] = ()  # (tema, nº de reclamações), para pratos


@dataclass(frozen=True)
class Acao:
    prioridade: int
    candidato: Candidato
    reclamacoes_resolvidas: int                 # novas, depois das ações anteriores
    avaliacoes_afetadas: Proporcao              # avaliações com esse problema, entre as consideradas
    ganho: float                                # cenário completo, em pontos de nota
    ganho_conservador: float
    nota_antes: float                           # com as ações anteriores já aplicadas
    nota_depois: float
    nota_depois_conservadora: float

    @property
    def titulo(self) -> str:
        return self.candidato.titulo

    @property
    def baixa_confianca(self) -> bool:
        return self.avaliacoes_afetadas.k < 20


@dataclass(frozen=True)
class Plano:
    acoes: list[Acao]
    nota_atual: float
    nota_referencia: float
    avaliacoes: int

    @property
    def nota_final(self) -> float:
        return self.acoes[-1].nota_depois if self.acoes else self.nota_atual

    @property
    def nota_final_conservadora(self) -> float:
        return self.acoes[-1].nota_depois_conservadora if self.acoes else self.nota_atual


def base_do_plano(df: pd.DataFrame) -> pd.DataFrame:
    """Avaliações de pedidos reais, com índice 0..N-1. Sem pedido não há como localizar a causa."""
    return df[df["tem_pedido"]].reset_index(drop=True)


def nota_referencia(base: pd.DataFrame) -> float:
    sem_problema = base[base["temas"].map(len) == 0]
    return float(sem_problema["nota"].mean()) if len(sem_problema) else float("nan")


# --- Candidatos -----------------------------------------------------------------------------
def construir_candidatos(
    base: pd.DataFrame, quando_onde: dict[str, list[Padrao]], *, min_instancias: int = MIN_INSTANCIAS
) -> list[Candidato]:
    temas_por_linha = base["temas"].tolist()
    candidatos: list[Candidato] = []

    por_segmento: dict[tuple[str, ...], dict] = {}
    for tema, padroes in quando_onde.items():
        for padrao in padroes[:PADROES_POR_TEMA]:
            dentro = np.flatnonzero(mascara_do_padrao(base, padrao.condicoes))
            instancias = {(int(i), tema) for i in dentro if tema in temas_por_linha[i]}
            if not instancias:
                continue
            grupo = por_segmento.setdefault(padrao.condicoes, {"segmento": padrao.segmento, "inst": set(), "padroes": []})
            grupo["inst"] |= instancias
            grupo["padroes"].append((tema, padrao))
    for grupo in por_segmento.values():
        if len(grupo["inst"]) < min_instancias:
            continue
        temas = tuple(dict.fromkeys(t for t, _ in grupo["padroes"]))
        titulo = f"Resolver {_lista_em_portugues([SUBSTANTIVO_TEMA[t] for t in temas])} em {grupo['segmento']}"
        candidatos.append(Candidato("segmento", titulo, frozenset(grupo["inst"]), temas=temas,
                                    padroes=tuple(grupo["padroes"])))

    por_prato: dict[str, set[tuple[int, str]]] = {}
    for i, pratos in enumerate(base["pratos"]):
        for entrada in pratos:
            for tema in entrada["problemas"]:
                por_prato.setdefault(entrada["prato"], set()).add((i, tema))
    for prato, instancias in sorted(por_prato.items()):
        if len(instancias) >= min_instancias:
            contagem: dict[str, int] = {}
            for _, tema in instancias:
                contagem[tema] = contagem.get(tema, 0) + 1
            problemas = tuple(sorted(contagem.items(), key=lambda x: (-x[1], x[0])))
            candidatos.append(Candidato(
                "prato", f"Melhorar {prato}", frozenset(instancias),
                temas=tuple(t for t, _ in problemas), prato=prato, problemas_do_prato=problemas))

    todas = {(i, t) for i, ts in enumerate(temas_por_linha) for t in ts}
    cobertas = set().union(*(c.instancias for c in candidatos)) if candidatos else set()
    for tema in sorted({t for _, t in todas}):
        sobra = frozenset(x for x in todas - cobertas if x[1] == tema)
        if len(sobra) >= min_instancias:
            # "demais casos" só quando já existe uma ação de segmento para o mesmo tema
            sufixo = " (demais casos)" if any(tema in c.temas and c.tipo == "segmento" for c in candidatos) else ""
            candidatos.append(Candidato("residual", f"Resolver {SUBSTANTIVO_TEMA[tema]}{sufixo}", sobra, temas=(tema,)))
    return candidatos


# --- Plano ----------------------------------------------------------------------------------
def ordenar_plano(
    base: pd.DataFrame,
    candidatos: list[Candidato],
    *,
    min_ganho: float = MIN_GANHO,
    min_instancias: int = MIN_INSTANCIAS,
) -> Plano:
    n = len(base)
    ref = nota_referencia(base)
    nota = base["nota"].to_numpy(dtype=float)
    nota_atual = float(nota.mean()) if n else float("nan")
    if n == 0 or np.isnan(ref):
        return Plano([], nota_atual, ref, n)

    distancia = np.maximum(0.0, ref - nota)
    n_temas = base["temas"].map(len).to_numpy()
    valor = np.divide(distancia, n_temas, out=np.zeros(n), where=n_temas > 0)  # ganho por reclamação resolvida

    resolvidas: set[tuple[int, str]] = set()
    restantes = list(candidatos)
    acoes: list[Acao] = []
    acumulado = 0.0
    while True:
        elegiveis = [
            (sum(valor[i] for i, _ in c.instancias - resolvidas) / n, c)
            for c in restantes
            if len(c.instancias - resolvidas) >= min_instancias  # o que sobra de uma ação já coberta não vira item
        ]
        if not elegiveis:
            break
        ganho, melhor = max(elegiveis, key=lambda x: x[0])
        if ganho < min_ganho:
            break
        novas = melhor.instancias - resolvidas
        acoes.append(Acao(
            prioridade=len(acoes) + 1,
            candidato=melhor,
            reclamacoes_resolvidas=len(novas),
            avaliacoes_afetadas=pct_com_n(len({i for i, _ in novas}), n),
            ganho=ganho,
            ganho_conservador=ganho * FATOR_CONSERVADOR,
            nota_antes=nota_atual + acumulado,
            nota_depois=nota_atual + acumulado + ganho,
            nota_depois_conservadora=nota_atual + (acumulado + ganho) * FATOR_CONSERVADOR,
        ))
        acumulado += ganho
        resolvidas |= novas
        restantes.remove(melhor)
    return Plano(acoes, nota_atual, ref, n)


def montar_plano(df: pd.DataFrame, pedidos: pd.DataFrame) -> Plano:
    """Atalho: causa raiz (quando e onde) -> candidatos -> plano ordenado."""
    base = base_do_plano(df)
    quando_onde = causas_por_tema(df, pedidos, dimensoes=DIMENSOES_QUANDO_ONDE)
    return ordenar_plano(base, construir_candidatos(base, quando_onde))
