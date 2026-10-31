"""Interpretação offline da pergunta: palavras-chave -> chamadas de ferramentas.

É deliberadamente simples e previsível: reconhece um conjunto de tipos de pergunta e diz com clareza quando
não entendeu ou quando o assunto está fora dos dados. Perguntas livres exigem o modo com Claude.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from copiloto.dominio import normalizar
from copiloto.qa.ferramentas import Contexto

MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

_TEMAS = {
    "atraso": r"atras|demor|demora|prazo|lent",
    "temperatura": r"\bfri[oa]s?\b|gelad|morn|esfri|temperatura|quente",
    "textura": r"murch|mole|molenga|empap|borrachud|textura|crocan",
    "embalagem": r"embalagem|vazou|vazament|amassad",
    "sabor": r"sabor|salgad|insos|gosto|tempero",
    "quantidade": r"quantidade|porcao|pouca comida|pequen",
    "atendimento": r"atendimento|atendente|entregador|grosseir",
    "pedido_errado": r"errad|trocaram|faltou|esquec",
}
_FORA_DO_ESCOPO = r"faturamento|lucro|receita|vendas|custo|estoque|funcionari|salario|concorrente|clima|chuva|marketing|instagram|ifood"


@dataclass(frozen=True)
class Chamada:
    ferramenta: str
    argumentos: dict


@dataclass(frozen=True)
class Interpretacao:
    chamadas: tuple[Chamada, ...] = ()
    fora_do_escopo: str | None = None      # assunto que os dados não cobrem
    sem_dados: str | None = None           # pedido que os dados não cobrem (ex.: ano fora do período)


def _mes_citado(q: str, ctx: Contexto) -> tuple[str | None, str | None]:
    """Devolve (mês 'AAAA-MM' ou None, aviso de dados indisponíveis ou None)."""
    inicio, fim = ctx.periodo
    ano_citado = re.search(r"\b(20\d{2})\b", q)
    if ano_citado and int(ano_citado.group(1)) not in (inicio.year, fim.year):
        return None, (f"Os dados vão de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}; não há avaliações em {ano_citado.group(1)}.")
    ano = int(ano_citado.group(1)) if ano_citado else fim.year
    for numero, nome in enumerate(MESES, start=1):
        if re.search(rf"\b{nome}\b", q):
            return f"{ano}-{numero:02d}", None
    if re.search(r"\b(este mes|neste mes|mes atual|ultimo mes|mes passado)\b", q):
        return fim.strftime("%Y-%m"), None
    return None, None


def _tema_citado(q: str) -> str | None:
    for tema, padrao in _TEMAS.items():
        if re.search(padrao, q):
            return tema
    return None


def _prato_citado(q: str, ctx: Contexto) -> str | None:
    melhor, tamanho = None, 0
    for prato, aliases in ctx.aliases.items():
        for termo in {normalizar(prato), *(normalizar(a) for a in aliases)}:
            if len(termo) > tamanho and re.search(rf"\b{re.escape(termo)}\b", q):
                melhor, tamanho = prato, len(termo)
    return melhor


def interpretar(pergunta: str, ctx: Contexto) -> Interpretacao:
    q = normalizar(pergunta)
    if (fora := re.search(_FORA_DO_ESCOPO, q)):
        return Interpretacao(fora_do_escopo=fora.group(0))
    mes, sem_dados = _mes_citado(q, ctx)
    if sem_dados:
        return Interpretacao(sem_dados=sem_dados)
    ultimo_mes = ctx.periodo[1].strftime("%Y-%m")
    prato = _prato_citado(q, ctx)
    tema = _tema_citado(q)
    pede_causa = bool(re.search(r"por ?que|porque|causa|motivo|origem|quando|onde|em que|concentr|explica", q))

    if "nota" in q and re.search(r"\b(caiu|cair|queda|piorou|piora|baixou|despencou|subiu|aumentou|melhorou|mudou)\b", q):
        return Interpretacao((Chamada("explicar_variacao_da_nota", {"mes": mes or ultimo_mes}),))
    if prato and re.search(r"problema|reclam|queixa|por ?que|porque|motivo|causa|piora|ruim", q):
        return Interpretacao((Chamada("ranking_de_pratos", {"prato": prato}), Chamada("causa_raiz_do_prato", {"prato": prato})))
    if re.search(r"\bprato", q) and re.search(r"mais|pior|maior|principal|top", q) and re.search(r"reclam|problema|queixa|ruim", q):
        return Interpretacao((Chamada("ranking_de_pratos", {}),))
    if tema and pede_causa:
        return Interpretacao((Chamada("causa_raiz", {"tema": tema}),))
    if re.search(r"plano|prioridade|priorizar|resolver primeiro|melhorar primeiro|aumentar a nota|subir a nota|o que (devo )?(fazer|resolver|melhorar)|como melhorar", q):
        return Interpretacao((Chamada("plano_de_acao", {}),))
    if re.search(r"suspeit|falsa|falso|fake|ataque|fraude|\bbots?\b|golpe", q):
        return Interpretacao((Chamada("avaliacoes_suspeitas", {}),))
    if re.search(r"reclam|queixa|problema|tema", q):
        return Interpretacao((Chamada("temas_de_reclamacao", {"mes": mes} if mes else {}),))
    if "nota" in q and re.search(r"evolu|ao longo|por mes|mes a mes|historico|tendencia", q):
        return Interpretacao((Chamada("nota_por_mes", {}),))
    if "nota" in q or "avaliac" in q:
        return Interpretacao((Chamada("nota_media", {"mes": mes} if mes else {}),))
    return Interpretacao()
