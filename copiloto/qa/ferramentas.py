"""Ferramentas de consulta do agente: só leitura, parâmetros validados, números calculados em código.

O agente (Claude ou regras) nunca acessa o banco diretamente: tudo passa por aqui. Os resultados trazem os
números (com a base k de n) e uma descrição da base usada; o modelo só pode citar o que veio nelas.
Os resultados não contêm texto de avaliações, então nada escrito por clientes chega ao modelo por este caminho.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from copiloto import db
from copiloto.analytics.base import carregar_pedidos
from copiloto.analytics.causa_raiz import (
    DIMENSOES_QUANDO_ONDE,
    Padrao,
    causas_do_prato,
    causas_por_tema,
    rotulo_evento_tema,
)
from copiloto.analytics.impacto import montar_plano
from copiloto.analytics.pratos import analise_por_prato, ranking_pratos
from copiloto.analytics.series import ranking_temas
from copiloto.analytics.suspeitas import (
    MODOS,
    comparar_metricas,
    episodios_suspeitos,
    filtrar_suspeitas,
)
from copiloto.analytics.variacao import explicar_variacao, rotulo_mes
from copiloto.dominio import ROTULO_TEMA, TEMAS, normalizar
from copiloto.stats import Proporcao, pct_com_n


class ErroDeFerramenta(ValueError):
    """Chamada inválida: ferramenta ou parâmetro inexistente, valor fora do permitido."""


@dataclass(frozen=True)
class Grafico:
    tipo: str                                  # "linha" | "barra"
    titulo: str
    x: tuple
    series: dict[str, tuple]
    rotulo_y: str


@dataclass
class ResultadoFerramenta:
    dados: dict
    base: str = ""
    sem_dados: bool = False
    motivo: str = ""
    grafico: Grafico | None = None

    def para_modelo(self) -> str:
        corpo = {"base": self.base, "sem_dados": self.sem_dados, **({"motivo": self.motivo} if self.motivo else {}), **self.dados}
        return json.dumps(corpo, ensure_ascii=False)


@dataclass
class Contexto:
    """Dados disponíveis para as ferramentas. `todas` traz as colunas de suspeitas; `modo` é o filtro ativo."""

    con: sqlite3.Connection
    todas: pd.DataFrame
    pedidos: pd.DataFrame
    categorias: dict[str, str]
    aliases: dict[str, tuple[str, ...]]
    modo: str = "medias_e_altas"

    @property
    def df(self) -> pd.DataFrame:
        return filtrar_suspeitas(self.todas, self.modo)

    @property
    def pedidos_filtrados(self) -> pd.DataFrame:
        tirados = set(self.todas["pedido_id"].dropna().astype(int)) - set(self.df["pedido_id"].dropna().astype(int))
        return self.pedidos[~self.pedidos["pedido_id"].isin(tirados)]

    @property
    def pratos(self) -> list[str]:
        return list(self.categorias)

    @property
    def periodo(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        return self.todas["criado_em"].min(), self.todas["criado_em"].max()

    @property
    def base(self) -> str:
        return {"todas": "todas as avaliações", "medias_e_altas": "avaliações sem suspeitas médias e altas",
                "so_altas": "avaliações sem suspeitas altas"}[self.modo]


def carregar_contexto(con: sqlite3.Connection, todas: pd.DataFrame, modo: str = "medias_e_altas") -> Contexto:
    cardapio = con.execute("SELECT nome, categoria, aliases FROM cardapio ORDER BY item_id").fetchall()
    return Contexto(
        con=con, todas=todas, pedidos=carregar_pedidos(con), modo=modo,
        categorias={r["nome"]: r["categoria"] for r in cardapio},
        aliases={r["nome"]: tuple(json.loads(r["aliases"])) for r in cardapio},
    )


# --- Parâmetros e validação -------------------------------------------------------------------
@dataclass(frozen=True)
class Parametro:
    nome: str
    tipo: str                                   # "string" | "integer"
    descricao: str
    opcoes: tuple[str, ...] = ()
    obrigatorio: bool = False
    minimo: int | None = None
    maximo: int | None = None


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    parametros: tuple[Parametro, ...]
    funcao: Callable[..., ResultadoFerramenta]

    def schema(self) -> dict:
        """Definição no formato de ferramentas da API do Claude."""
        props = {}
        for p in self.parametros:
            item: dict[str, Any] = {"type": p.tipo, "description": p.descricao}
            if p.opcoes:
                item["enum"] = list(p.opcoes)
            props[p.nome] = item
        return {
            "name": self.nome, "description": self.descricao,
            "input_schema": {"type": "object", "properties": props,
                             "required": [p.nome for p in self.parametros if p.obrigatorio],
                             "additionalProperties": False},
        }

    def executar(self, ctx: Contexto, argumentos: Any) -> ResultadoFerramenta:
        if not isinstance(argumentos, dict):
            raise ErroDeFerramenta("os argumentos devem ser um objeto")
        conhecidos = {p.nome for p in self.parametros}
        if extras := set(argumentos) - conhecidos:
            raise ErroDeFerramenta(f"parâmetros desconhecidos: {sorted(extras)}")
        limpos: dict[str, Any] = {}
        for p in self.parametros:
            if p.nome not in argumentos or argumentos[p.nome] is None:
                if p.obrigatorio:
                    raise ErroDeFerramenta(f"falta o parâmetro '{p.nome}'")
                continue
            limpos[p.nome] = _validar(ctx, p, argumentos[p.nome])
        return self.funcao(ctx, **limpos)


_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validar(ctx: Contexto, p: Parametro, valor: Any) -> Any:
    if p.tipo == "integer":
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ErroDeFerramenta(f"'{p.nome}' deve ser um número inteiro")
        if (p.minimo is not None and valor < p.minimo) or (p.maximo is not None and valor > p.maximo):
            raise ErroDeFerramenta(f"'{p.nome}' deve estar entre {p.minimo} e {p.maximo}")
        return valor
    if not isinstance(valor, str):
        raise ErroDeFerramenta(f"'{p.nome}' deve ser texto")
    if p.nome == "mes":
        if not _MES.match(valor):
            raise ErroDeFerramenta("'mes' deve ter o formato AAAA-MM, por exemplo 2026-10")
        return valor
    if p.nome == "prato":
        alvo = normalizar(valor.strip())
        for nome in ctx.pratos:
            if alvo in {normalizar(nome), *(normalizar(a) for a in ctx.aliases[nome])}:
                return nome
        raise ErroDeFerramenta(f"prato desconhecido: {valor!r}. Pratos do cardápio: {ctx.pratos}")
    if p.opcoes and valor not in p.opcoes:
        raise ErroDeFerramenta(f"'{p.nome}' deve ser um de {list(p.opcoes)}")
    return valor


# --- Utilitários dos resultados -----------------------------------------------------------------
def _prop(p: Proporcao) -> dict:
    return {"k": p.k, "n": p.n, "pct": round(p.pct, 1)}


def _nota(valor: float) -> float:
    return round(float(valor), 2)


def _no_mes(df: pd.DataFrame, mes: str) -> pd.DataFrame:
    inicio = pd.Timestamp(f"{mes}-01")
    return df[(df["criado_em"] >= inicio) & (df["criado_em"] < inicio + pd.offsets.MonthBegin(1))]


def _sem_dados_do_mes(ctx: Contexto, mes: str) -> ResultadoFerramenta:
    ini, fim = ctx.periodo
    return ResultadoFerramenta(
        {}, base=ctx.base, sem_dados=True,
        motivo=f"Não há avaliações em {rotulo_mes(mes)}. Os dados vão de {ini:%d/%m/%Y} a {fim:%d/%m/%Y}.",
    )


def _padrao(p: Padrao, tema: str | None = None) -> dict:
    return {
        "segmento": p.segmento,
        "frase": p.texto(rotulo_evento_tema(tema) if tema else "reclamações do prato"),
        "parcela_das_reclamacoes": _prop(p.parcela_das_reclamacoes),
        "taxa_no_segmento": _prop(p.no_segmento),
        "taxa_fora_do_segmento_pct": round(p.fora_do_segmento.pct, 1),
        "vezes_mais_frequente": round(p.lift, 1),
        "pedidos_no_segmento_pct": round(p.pedidos_no_segmento.pct, 1) if p.pedidos_no_segmento else None,
        "baixa_confianca": p.baixa_confianca,
        "evidencia": p.evidencia,
    }


# --- Ferramentas --------------------------------------------------------------------------------
def nota_por_mes(ctx: Contexto) -> ResultadoFerramenta:
    sem = filtrar_suspeitas(ctx.todas, "medias_e_altas")
    meses = sorted(ctx.todas["criado_em"].dt.strftime("%Y-%m").unique())
    linhas = []
    for mes in meses:
        t, s = _no_mes(ctx.todas, mes), _no_mes(sem, mes)
        linhas.append({"mes": mes, "rotulo": rotulo_mes(mes),
                       "todas": {"nota": _nota(t["nota"].mean()), "avaliacoes": len(t)},
                       "sem_suspeitas": {"nota": _nota(s["nota"].mean()) if len(s) else None, "avaliacoes": len(s)}})
    grafico = Grafico("linha", "Nota média por mês", tuple(meses),
                      {"Todas as avaliações": tuple(l["todas"]["nota"] for l in linhas),
                       "Sem suspeitas médias e altas": tuple(l["sem_suspeitas"]["nota"] for l in linhas)}, "Nota média")
    return ResultadoFerramenta({"meses": linhas}, base="todas as avaliações e, ao lado, sem suspeitas médias e altas", grafico=grafico)


def nota_media(ctx: Contexto, mes: str | None = None) -> ResultadoFerramenta:
    def resumo(d: pd.DataFrame) -> dict:
        negativas = pct_com_n(int((d["sentimento"] == "negativo").sum()), len(d))
        return {"nota": _nota(d["nota"].mean()), "avaliacoes": len(d), "negativas": _prop(negativas)}

    todas, sem = ctx.todas, filtrar_suspeitas(ctx.todas, "medias_e_altas")
    if mes:
        todas, sem = _no_mes(todas, mes), _no_mes(sem, mes)
        if todas.empty:
            return _sem_dados_do_mes(ctx, mes)
    comp = comparar_metricas(ctx.todas)
    return ResultadoFerramenta(
        {"periodo": rotulo_mes(mes) if mes else "todo o período", "todas": resumo(todas), "sem_suspeitas": resumo(sem),
         "diferenca_sem_suspeitas": round(_nota(sem["nota"].mean()) - _nota(todas["nota"].mean()), 2),
         "suspeitas_medias_e_altas_no_total": comp.removidas},
        base="todas as avaliações e, ao lado, sem suspeitas médias e altas",
    )


def ranking_de_pratos(ctx: Contexto, prato: str | None = None, limite: int = 5) -> ResultadoFerramenta:
    analises = analise_por_prato(ctx.con, ctx.df)
    ordenadas = ranking_pratos(analises)
    escolhidas = [a for a in analises if a.prato == prato] if prato else ordenadas[:limite]
    if prato and not escolhidas[0].mencoes:
        return ResultadoFerramenta({}, base=ctx.base, sem_dados=True, motivo=f"Nenhuma avaliação cita {prato}.")
    mais_reclamacoes = max(analises, key=lambda a: a.com_problema.k)
    dados = {
        "criterio": "% das avaliações que citam o prato e relatam algum problema; pratos com menos de 20 avaliações "
                    "ficam no fim e são marcados como baixa confiança",
        "pratos": [{
            "prato": a.prato, "categoria": a.categoria, "pedidos_com_o_prato": a.pedidos,
            "avaliacoes_que_citam": a.mencoes, "com_problema": _prop(a.com_problema), "baixa_confianca": a.baixa_confianca,
            "problemas": [{"tema": t, "rotulo": ROTULO_TEMA[t], **_prop(p)} for t, p in a.problemas],
        } for a in escolhidas],
        "prato_com_mais_reclamacoes_em_numero": {"prato": mais_reclamacoes.prato, "reclamacoes": mais_reclamacoes.com_problema.k},
    }
    grafico = Grafico("barra", "Avaliações com problema, por prato (%)", tuple(a.prato for a in escolhidas),
                      {"% com problema": tuple(round(a.com_problema.pct, 1) for a in escolhidas)}, "% das avaliações que citam o prato")
    return ResultadoFerramenta(dados, base=ctx.base, grafico=grafico)


def temas_de_reclamacao(ctx: Contexto, mes: str | None = None) -> ResultadoFerramenta:
    df = _no_mes(ctx.df, mes) if mes else ctx.df
    if df.empty:
        return _sem_dados_do_mes(ctx, mes)
    ranking = ranking_temas(df)
    dados = {"periodo": rotulo_mes(mes) if mes else "todo o período",
             "temas": [{"tema": t, "rotulo": ROTULO_TEMA[t], **_prop(p)} for t, p in ranking if p.k]}
    grafico = Grafico("barra", "Temas de reclamação (% das avaliações)", tuple(x["rotulo"] for x in dados["temas"]),
                      {"% das avaliações": tuple(x["pct"] for x in dados["temas"])}, "% das avaliações que citam o tema")
    return ResultadoFerramenta(dados, base=ctx.base, grafico=grafico)


def causa_raiz(ctx: Contexto, tema: str) -> ResultadoFerramenta:
    mecanismo = causas_por_tema(ctx.df, ctx.pedidos_filtrados)[tema]
    quando_onde = causas_por_tema(ctx.df, ctx.pedidos_filtrados, dimensoes=DIMENSOES_QUANDO_ONDE)[tema]
    if not mecanismo and not quando_onde:
        return ResultadoFerramenta(
            {}, base=ctx.base + ", só avaliações de pedidos", sem_dados=True,
            motivo=f"Nenhuma condição do pedido (dia, turno, tempos, distância) concentra de forma consistente "
                   f"as reclamações de {ROTULO_TEMA[tema].lower()}.")
    return ResultadoFerramenta(
        {"tema": ROTULO_TEMA[tema], "condicao_do_pedido": [_padrao(p, tema) for p in mecanismo],
         "quando_e_onde": [_padrao(p, tema) for p in quando_onde]},
        base=ctx.base + ", só avaliações de pedidos")


def causa_raiz_do_prato(ctx: Contexto, prato: str) -> ResultadoFerramenta:
    padroes = causas_do_prato(ctx.df, ctx.pedidos_filtrados, prato)
    if not padroes:
        return ResultadoFerramenta({}, base=ctx.base, sem_dados=True,
                                   motivo=f"Nenhuma condição do pedido concentra de forma consistente os problemas de {prato}.")
    return ResultadoFerramenta({"prato": prato, "padroes": [_padrao(p) for p in padroes]},
                               base=ctx.base + ", avaliações de pedidos que incluíram o prato")


def plano_de_acao(ctx: Contexto, limite: int = 5) -> ResultadoFerramenta:
    plano = montar_plano(ctx.df, ctx.pedidos_filtrados)
    if not plano.acoes:
        return ResultadoFerramenta({}, base=ctx.base, sem_dados=True, motivo="Não há reclamações suficientes para montar um plano.")
    acoes = plano.acoes[:limite]
    dados = {
        "nota_atual": _nota(plano.nota_atual), "nota_referencia_de_quem_nao_reclama": _nota(plano.nota_referencia),
        "nota_com_todo_o_plano": {"completo": _nota(plano.nota_final), "conservador": _nota(plano.nota_final_conservadora)},
        "acoes": [{"prioridade": a.prioridade, "titulo": a.titulo, "ganho_completo": _nota(a.ganho),
                   "ganho_conservador": _nota(a.ganho_conservador), "nota_antes": _nota(a.nota_antes),
                   "nota_depois": _nota(a.nota_depois), "avaliacoes_afetadas": _prop(a.avaliacoes_afetadas),
                   "baixa_confianca": a.baixa_confianca} for a in acoes],
        "aviso": "Estimativa por contrafactual simples, não previsão; o conservador supõe metade do ganho.",
    }
    grafico = Grafico("barra", "Ganho estimado na nota média, por ação", tuple(f"{a.prioridade}. {a.titulo}" for a in acoes),
                      {"Ganho (cenário completo)": tuple(_nota(a.ganho) for a in acoes)}, "Pontos de nota")
    return ResultadoFerramenta(dados, base=ctx.base + ", só avaliações de pedidos", grafico=grafico)


def avaliacoes_suspeitas(ctx: Contexto) -> ResultadoFerramenta:
    niveis = ctx.todas["suspeita_nivel"].value_counts()
    comp = comparar_metricas(ctx.todas)
    dados = {
        "niveis": {n: int(niveis.get(n, 0)) for n in ("alto", "médio", "baixo")},
        "total_de_avaliacoes": comp.avaliacoes_todas,
        "nota_com_todas": _nota(comp.nota_todas), "nota_sem_suspeitas": _nota(comp.nota_sem_suspeitas),
        "negativas_com_todas": _prop(comp.negativas_todas), "negativas_sem_suspeitas": _prop(comp.negativas_sem_suspeitas),
        "episodios": [{
            "inicio": e.inicio.strftime("%d/%m/%Y"), "fim": e.fim.strftime("%d/%m/%Y"), "avaliacoes": e.avaliacoes,
            "altas": e.altas, "nota_media": _nota(e.nota_media), "sem_pedido": _prop(e.sem_pedido),
            "contas_novas": _prop(e.contas_novas), "texto_parecido": _prop(e.texto_parecido), "resumo": e.texto(),
        } for e in episodios_suspeitos(ctx.todas)],
        "aviso": "A ferramenta só sinaliza; a decisão de contestar é do dono.",
    }
    return ResultadoFerramenta(dados, base="todas as avaliações")


def explicar_variacao_da_nota(ctx: Contexto, mes: str) -> ResultadoFerramenta:
    r = explicar_variacao(ctx.todas, ctx.pedidos, mes)
    if r["sem_dados"]:
        return ResultadoFerramenta({}, base="todas as avaliações", sem_dados=True, motivo=r["motivo"])
    grafico = nota_por_mes(ctx).grafico
    return ResultadoFerramenta({"mes": rotulo_mes(mes), **{k: v for k, v in r.items() if k not in ("mes", "sem_dados")}},
                               base="todas as avaliações; o mês contra todos os meses anteriores", grafico=grafico)


def _mes(descricao: str = "Mês no formato AAAA-MM, por exemplo 2026-10.") -> Parametro:
    return Parametro("mes", "string", descricao)


def _prato() -> Parametro:
    return Parametro("prato", "string", "Nome do prato do cardápio.")


FERRAMENTAS: dict[str, Ferramenta] = {f.nome: f for f in (
    Ferramenta("nota_por_mes", "Nota média por mês, com todas as avaliações e sem as suspeitas. Use para evolução da nota.",
               (), nota_por_mes),
    Ferramenta("nota_media", "Nota média, avaliações e % de negativas, com e sem suspeitas, para todo o período ou um mês.",
               (_mes(),), nota_media),
    Ferramenta("ranking_de_pratos", "Pratos com mais problemas citados nas avaliações (% e quantidade, com baixa confiança "
               "quando há menos de 20 avaliações). Com `prato`, detalha um prato.",
               (_prato(), Parametro("limite", "integer", "Quantos pratos listar (1 a 10).", minimo=1, maximo=10)),
               ranking_de_pratos),
    Ferramenta("temas_de_reclamacao", "Temas de reclamação mais citados (atraso, comida fria, textura etc.), no período todo ou em um mês.",
               (_mes(),), temas_de_reclamacao),
    Ferramenta("causa_raiz", "Em que condições do pedido (dia, turno, tempos de entrega e preparo, distância) um tema de "
               "problema se concentra.",
               (Parametro("tema", "string", "Tema do problema.", opcoes=TEMAS, obrigatorio=True),), causa_raiz),
    Ferramenta("causa_raiz_do_prato", "Em que condições do pedido os problemas de um prato se concentram.",
               (Parametro("prato", "string", "Nome do prato do cardápio.", obrigatorio=True),), causa_raiz_do_prato),
    Ferramenta("plano_de_acao", "O que resolver primeiro, em ordem de efeito estimado na nota média.",
               (Parametro("limite", "integer", "Quantas ações listar (1 a 10).", minimo=1, maximo=10),), plano_de_acao),
    Ferramenta("avaliacoes_suspeitas", "Avaliações suspeitas de serem falsas: níveis, episódios e a nota com e sem elas.",
               (), avaliacoes_suspeitas),
    Ferramenta("explicar_variacao_da_nota", "Por que a nota de um mês mudou em relação aos meses anteriores: efeito das "
               "avaliações suspeitas, temas que cresceram e piora no tempo de entrega.",
               (Parametro("mes", "string", "Mês no formato AAAA-MM, por exemplo 2026-10.", obrigatorio=True),),
               explicar_variacao_da_nota),
)}
