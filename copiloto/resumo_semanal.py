"""Resumo semanal: os três pontos que mais precisam de atenção, em texto e HTML, para enviar por e-mail.

Tudo é calculado em código, com as mesmas análises do dashboard, e funciona sem chave de IA. O n8n só
agenda a chamada e envia o e-mail; não decide nada.

Escolha dos pontos, nesta ordem de precedência, até completar três:
1. possível ataque de avaliações falsas nos últimos 28 dias (exige uma decisão do dono);
2. queda da nota da semana contra as 4 semanas anteriores (teste t de Welch);
3. temas de reclamação em alta nos últimos 28 dias (teste de Fisher);
4. piora no tempo de entrega em um dia e horário nas últimas 4 semanas (teste t de Welch); quando a
   primeira ação do plano trata do mesmo segmento, o ganho estimado dela entra neste ponto;
5. as ações do plano de ação, na ordem de ganho estimado na nota (só as de segmento ou de prato).
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from scipy.stats import ttest_ind

from copiloto.analytics.causa_raiz import causas_da_entrega_lenta, mascara_do_padrao
from copiloto.analytics.impacto import montar_plano
from copiloto.analytics.suspeitas import episodios_suspeitos, filtrar_suspeitas
from copiloto.analytics.tendencias import alertas_tendencia
from copiloto.datagen.cardapio import NOME_RESTAURANTE
from copiloto.stats import formatar_nota, pct_com_n
from copiloto.sugestoes import AVISO, OPERACAO, sugestoes_para

PONTOS = 3
JANELA_RECENTE_DIAS = 28
MIN_AVALIACOES_SEMANA = 15
MIN_AVALIACOES_ANTERIOR = 30
QUEDA_MINIMA = 0.30
ALFA_NOTA = 0.05
AUMENTO_ENTREGA_MIN = 5.0


@dataclass(frozen=True)
class Ponto:
    tipo: str                    # "ataque" | "nota" | "tendencia" | "entrega" | "plano"
    titulo: str
    detalhe: str
    sugestao: str | None = None
    numeros: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResumoSemanal:
    restaurante: str
    inicio: date
    fim: date
    avaliacoes: int
    nota_media: float | None
    nota_anterior: float | None
    negativas_pct: float | None
    pontos: list[Ponto]
    url_dashboard: str | None = None

    @property
    def periodo(self) -> str:
        return f"{self.inicio:%d/%m} a {self.fim:%d/%m/%Y}"

    @property
    def assunto(self) -> str:
        return f"Resumo semanal — {self.restaurante} — {self.periodo}"

    def _linha_da_semana(self) -> str:
        if not self.avaliacoes:
            return f"Semana de {self.periodo}: nenhuma avaliação recebida."
        texto = (f"Semana de {self.periodo}: {self.avaliacoes} avaliações, nota média {formatar_nota(self.nota_media, 2)}"
                 f" e {self.negativas_pct:.0f}% de negativas.")
        if self.nota_anterior is not None:
            texto += f" Nas 4 semanas anteriores, a nota média foi {formatar_nota(self.nota_anterior, 2)}."
        return texto

    def texto(self) -> str:
        linhas = ["Bom dia!", "", self._linha_da_semana(), "", f"Os {len(self.pontos)} pontos que mais precisam de atenção:", ""]
        for i, p in enumerate(self.pontos, start=1):
            linhas += [f"{i}. {p.titulo}", f"   {p.detalhe}"]
            if p.sugestao:
                linhas.append(f"   Sugestão a avaliar: {p.sugestao}")
            linhas.append("")
        linhas += [AVISO, "Todos os números são calculados em código a partir das avaliações e dos pedidos."]
        if self.url_dashboard:
            linhas += ["", f"Detalhes no dashboard: {self.url_dashboard}"]
        return "\n".join(linhas)

    def html(self) -> str:
        e = html.escape
        itens = ""
        for p in self.pontos:
            sugestao = f"<p style='margin:4px 0 0;color:#57534e'><em>Sugestão a avaliar:</em> {e(p.sugestao)}</p>" if p.sugestao else ""
            itens += (f"<li style='margin-bottom:14px'><strong>{e(p.titulo)}</strong>"
                      f"<p style='margin:4px 0 0'>{e(p.detalhe)}</p>{sugestao}</li>")
        link = f"<p><a href='{e(self.url_dashboard, quote=True)}'>Abrir o dashboard</a></p>" if self.url_dashboard else ""
        return (
            "<div style='font-family:Arial,sans-serif;max-width:600px;color:#1c1917'>"
            f"<h2 style='color:#c2410c'>{e(self.assunto)}</h2><p>Bom dia!</p><p>{e(self._linha_da_semana())}</p>"
            f"<h3>Os {len(self.pontos)} pontos que mais precisam de atenção</h3><ol style='padding-left:20px'>{itens}</ol>"
            f"<p style='font-size:12px;color:#78716c'>{e(AVISO)} Todos os números são calculados em código a partir das "
            f"avaliações e dos pedidos.</p>{link}</div>"
        )

    def para_json(self) -> dict:
        return {
            "assunto": self.assunto, "texto": self.texto(), "html": self.html(),
            "semana": {"inicio": self.inicio.isoformat(), "fim": self.fim.isoformat()},
            "metricas": {"avaliacoes": self.avaliacoes, "nota_media": self.nota_media,
                         "nota_media_4_semanas_anteriores": self.nota_anterior, "negativas_pct": self.negativas_pct},
            "pontos": [{"tipo": p.tipo, "titulo": p.titulo, "detalhe": p.detalhe, "sugestao": p.sugestao,
                        "numeros": p.numeros} for p in self.pontos],
        }


# --- Candidatos a "ponto de atenção" -----------------------------------------------------------------
def _ponto_de_ataque(todas: pd.DataFrame, ate: pd.Timestamp) -> list[Ponto]:
    recentes = [e for e in episodios_suspeitos(todas) if e.fim >= ate - pd.Timedelta(days=JANELA_RECENTE_DIAS)]
    return [Ponto("ataque", "Possível ataque de avaliações falsas", e.texto(),
                  "Veja a aba Suspeitas e decida se vale contestar: a ferramenta só sinaliza.",
                  {"avaliacoes": e.avaliacoes, "altas": e.altas, "nota_media": round(e.nota_media, 2)})
            for e in recentes[:1]]


def _ponto_de_nota(semana: pd.DataFrame, anterior: pd.DataFrame) -> list[Ponto]:
    if len(semana) < MIN_AVALIACOES_SEMANA or len(anterior) < MIN_AVALIACOES_ANTERIOR:
        return []
    queda = float(anterior["nota"].mean() - semana["nota"].mean())
    p = float(ttest_ind(semana["nota"], anterior["nota"], equal_var=False, alternative="less").pvalue)
    if queda < QUEDA_MINIMA or p >= ALFA_NOTA:
        return []
    return [Ponto("nota", "A nota da semana caiu",
                  f"Nota média {formatar_nota(semana['nota'].mean(), 2)} em {len(semana)} avaliações, contra "
                  f"{formatar_nota(anterior['nota'].mean(), 2)} em {len(anterior)} nas 4 semanas anteriores "
                  f"(queda de {formatar_nota(queda, 2)}).",
                  None, {"nota_semana": round(float(semana["nota"].mean()), 2), "queda": round(queda, 2)})]


def _pontos_de_tendencia(base: pd.DataFrame) -> list[Ponto]:
    pontos = []
    for a in alertas_tendencia(base, dias=JANELA_RECENTE_DIAS):
        pontos.append(Ponto("tendencia", f"Reclamações de {a.tema.replace('_', ' ')} em alta", a.texto(),
                            OPERACAO[a.tema][0].texto, {"tema": a.tema, "aumento_pct": round(a.aumento_pct)}))
    return pontos


def _pontos_de_entrega(pedidos: pd.DataFrame, ate: pd.Timestamp) -> list[tuple[Ponto, str]]:
    """Segmentos de dia e horário em que o tempo de entrega piorou nas últimas 4 semanas (com o segmento)."""
    corte = ate.normalize() - pd.Timedelta(days=JANELA_RECENTE_DIAS - 1)
    recentes, antes = pedidos[pedidos["criado_em"] >= corte], pedidos[pedidos["criado_em"] < corte]
    if len(recentes) < MIN_AVALIACOES_SEMANA or len(antes) < MIN_AVALIACOES_ANTERIOR:
        return []
    achados = []
    for padrao in causas_da_entrega_lenta(pedidos):
        if not any(c.startswith("de ") or c.startswith("à ") or c.startswith("no ") for c in padrao.condicoes):
            continue                                     # só dia e horário: distância não "piora com o tempo"
        r = recentes[mascara_do_padrao(recentes, padrao.condicoes)]["tempo_entrega_min"]
        a = antes[mascara_do_padrao(antes, padrao.condicoes)]["tempo_entrega_min"]
        if len(r) < 10 or len(a) < 10:
            continue
        diferenca = float(r.mean() - a.mean())
        p = float(ttest_ind(r, a, equal_var=False, alternative="greater").pvalue)
        if diferenca >= AUMENTO_ENTREGA_MIN and p < 0.01:
            achados.append((Ponto(
                "entrega", f"Entregas mais lentas em {padrao.segmento}",
                f"O tempo médio de entrega foi de {r.mean():.0f} min nas últimas 4 semanas ({len(r)} pedidos), contra "
                f"{a.mean():.0f} min antes (+{diferenca:.0f} min).",
                OPERACAO["atraso"][0].texto, {"antes_min": round(float(a.mean())), "recente_min": round(float(r.mean()))}),
                padrao.segmento))
    return achados


def _pontos_do_plano(plano, categorias: dict[str, str]) -> list[tuple[Ponto, str]]:
    pontos = []
    for acao in plano.acoes:
        if acao.candidato.tipo == "residual":
            continue
        sugestoes = sugestoes_para(acao.candidato, categorias)
        pontos.append((Ponto(
            "plano", acao.titulo,
            f"Resolver isso tem potencial de levar a nota de {formatar_nota(acao.nota_antes, 2)} para "
            f"{formatar_nota(acao.nota_depois, 2)} (no cenário conservador, +{formatar_nota(acao.ganho_conservador, 2)}); "
            f"{acao.avaliacoes_afetadas.k} avaliações afetadas"
            f"{' (baixa confiança)' if acao.baixa_confianca else ''}. É uma estimativa, não uma previsão.",
            sugestoes[0].texto if sugestoes else None,
            {"ganho_completo": round(acao.ganho, 2), "ganho_conservador": round(acao.ganho_conservador, 2)}),
            acao.titulo))
    return pontos


def gerar_resumo(
    todas: pd.DataFrame,
    pedidos: pd.DataFrame,
    categorias: dict[str, str] | None = None,
    *,
    ate: date | None = None,
    modo: str = "medias_e_altas",
    restaurante: str = NOME_RESTAURANTE,
    url_dashboard: str | None = None,
) -> ResumoSemanal:
    """Resumo dos 7 dias que terminam em `ate` (padrão: o último dia com avaliações)."""
    categorias = categorias or {}
    fim = pd.Timestamp(ate or todas["criado_em"].max().date())
    inicio = fim - pd.Timedelta(days=6)
    limite = fim + pd.Timedelta(days=1)

    todas = todas[todas["criado_em"] < limite]
    pedidos = pedidos[pedidos["criado_em"] < limite]
    base = filtrar_suspeitas(todas, modo)
    semana = base[base["criado_em"] >= inicio]
    anterior = base[(base["criado_em"] < inicio) & (base["criado_em"] >= inicio - pd.Timedelta(days=28))]

    tirados = set(todas["pedido_id"].dropna().astype(int)) - set(base["pedido_id"].dropna().astype(int))
    pedidos_reais = pedidos[~pedidos["pedido_id"].isin(tirados)]
    plano = montar_plano(base, pedidos_reais)

    pontos: list[Ponto] = []
    pontos += _ponto_de_ataque(todas, fim)
    pontos += _ponto_de_nota(semana, anterior)
    pontos += _pontos_de_tendencia(base)

    plano_pontos = _pontos_do_plano(plano, categorias)
    usados_do_plano: set[str] = set()
    for ponto, segmento in _pontos_de_entrega(pedidos_reais, fim):
        junto = next(((p, t) for p, t in plano_pontos if segmento in t), None)
        if junto:                                       # a ação do plano trata do mesmo segmento: um ponto só
            ponto = Ponto(ponto.tipo, ponto.titulo, f"{ponto.detalhe} {junto[0].detalhe}", junto[0].sugestao or ponto.sugestao,
                          {**ponto.numeros, **junto[0].numeros})
            usados_do_plano.add(junto[1])
        pontos.append(ponto)
    pontos += [p for p, t in plano_pontos if t not in usados_do_plano]

    return ResumoSemanal(
        restaurante=restaurante, inicio=inicio.date(), fim=fim.date(), avaliacoes=len(semana),
        nota_media=round(float(semana["nota"].mean()), 2) if len(semana) else None,
        nota_anterior=round(float(anterior["nota"].mean()), 2) if len(anterior) else None,
        negativas_pct=round(pct_com_n(int((semana["sentimento"] == "negativo").sum()), len(semana)).pct, 1) if len(semana) else None,
        pontos=pontos[:PONTOS], url_dashboard=url_dashboard,
    )
