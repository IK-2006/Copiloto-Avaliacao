"""Detecção de avaliações suspeitas de serem falsas ou parte de um ataque coordenado.

A ferramenta só SINALIZA: cada avaliação recebe pontos, um nível (baixo, médio, alto) e os motivos
em linguagem simples. Nada é apagado nem contestado; quem decide é o dono. As métricas do app podem ser
vistas com ou sem as suspeitas.

Sinais (pontos):
- sem pedido correspondente (2);
- conta criada há menos de 7 dias e com no máximo 1 pedido (1): um cliente novo avaliando o primeiro
  pedido é normal, por isso o peso é baixo;
- nota 1–2 em um dia com rajada de notas baixas (1): o dia tem muito mais avaliações de nota 1–2 do que o
  normal, segundo uma distribuição de Poisson (p < 0,001);
- texto muito parecido com o de pelo menos 2 outras avaliações, de pelo menos 3 contas diferentes, em até
  7 dias (3): similaridade de cosseno >= 0,8 sobre trechos de 3 a 5 letras.

Níveis pela soma: 1–2 baixo, 3–4 médio, 5 ou mais alto. Nenhum sinal sozinho passa de "médio"; "alto" exige
combinação (por exemplo, texto copiado + conta nova + rajada).

Limites: textos parafraseados por um modelo de linguagem escapam do sinal de similaridade, e um ataque
lento e espalhado escapa do sinal de rajada. A comparação de textos é O(n²), adequada para alguns milhares
de avaliações.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.feature_extraction.text import TfidfVectorizer

from copiloto.dominio import normalizar
from copiloto.stats import Proporcao, formatar_nota, formatar_pct, pct_com_n

PONTOS = {"sem_pedido": 2, "conta_nova": 1, "rajada": 1, "texto_parecido": 3}
LIMITE_MEDIO = 3
LIMITE_ALTO = 5
NIVEIS = ("nenhum", "baixo", "médio", "alto")

CONTA_NOVA_DIAS = 7
CONTA_NOVA_MAX_PEDIDOS = 1
NOTA_BAIXA = 2
RAJADA_MIN_AVALIACOES = 5
RAJADA_ALFA = 0.001
SIMILARIDADE_MINIMA = 0.8
JANELA_TEXTO_DIAS = 7
MIN_PARECIDAS = 2
MIN_CONTAS = 3
TAMANHO_MIN_TEXTO = 40

MODOS = {
    "todas": "Incluir todas as avaliações",
    "medias_e_altas": "Excluir suspeitas médias e altas",
    "so_altas": "Excluir só as suspeitas altas",
}
_NIVEIS_EXCLUIDOS = {"todas": (), "medias_e_altas": ("médio", "alto"), "so_altas": ("alto",)}


def nivel_da(pontos: int) -> str:
    if pontos >= LIMITE_ALTO:
        return "alto"
    if pontos >= LIMITE_MEDIO:
        return "médio"
    return "baixo" if pontos > 0 else "nenhum"


# --- Sinais ---------------------------------------------------------------------------------
def dias_de_rajada(df: pd.DataFrame) -> dict[pd.Timestamp, tuple[int, float]]:
    """Dias com muito mais avaliações de nota baixa do que o normal: {dia: (quantidade, média típica)}."""
    dia = df["criado_em"].dt.normalize()
    todos_os_dias = pd.date_range(dia.min(), dia.max(), freq="D")
    baixas = dia[df["nota"] <= NOTA_BAIXA]
    por_dia = baixas.value_counts().reindex(todos_os_dias, fill_value=0).sort_index()
    tipicos = por_dia[por_dia <= por_dia.quantile(0.9)]   # a média típica não conta os dias extremos
    media_tipica = max(float(tipicos.mean()), 0.3)
    return {
        d: (int(k), media_tipica)
        for d, k in por_dia.items()
        if k >= RAJADA_MIN_AVALIACOES and poisson.sf(k - 1, media_tipica) < RAJADA_ALFA
    }


def textos_parecidos(df: pd.DataFrame) -> dict:
    """Por índice da avaliação: (nº de avaliações parecidas, nº de outras contas, dias de intervalo)."""
    textos = df["texto"].map(normalizar).to_numpy()
    posicoes = np.flatnonzero([len(t) >= TAMANHO_MIN_TEXTO for t in textos])
    if len(posicoes) < MIN_PARECIDAS + 1:
        return {}
    vetores = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit_transform(textos[posicoes])
    similaridade = (vetores @ vetores.T).toarray()          # linhas normalizadas: produto = cosseno
    np.fill_diagonal(similaridade, 0.0)
    segundos = df["criado_em"].to_numpy().astype("datetime64[s]").astype("int64")[posicoes]
    na_janela = np.abs(segundos[:, None] - segundos[None, :]) <= JANELA_TEXTO_DIAS * 86400
    parecidas = (similaridade >= SIMILARIDADE_MINIMA) & na_janela
    contas = df["cliente_id"].to_numpy()[posicoes]

    achados = {}
    for a in range(len(posicoes)):
        vizinhas = np.flatnonzero(parecidas[a])
        if len(vizinhas) < MIN_PARECIDAS:
            continue
        contas_do_grupo = set(contas[vizinhas]) | {contas[a]}
        if len(contas_do_grupo) < MIN_CONTAS:
            continue
        instantes = np.append(segundos[vizinhas], segundos[a])
        dias = max(1, math.ceil((instantes.max() - instantes.min()) / 86400))
        achados[df.index[posicoes[a]]] = (len(vizinhas), len(contas_do_grupo) - 1, dias)
    return achados


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def analisar_suspeitas(df: pd.DataFrame) -> pd.DataFrame:
    """Pontos, nível, sinais e motivos de cada avaliação (mesmo índice de `df`)."""
    rajadas = dias_de_rajada(df) if len(df) else {}
    parecidas = textos_parecidos(df) if len(df) else {}

    pontos, sinais, motivos = [], [], []
    for idx, r in zip(df.index, df.itertuples(index=False)):
        s: list[str] = []
        m: list[str] = []
        if pd.isna(r.pedido_id):
            s.append("sem_pedido")
            m.append("Sem pedido correspondente.")
        idade = r.criado_em - r.conta_criada_em
        if idade < pd.Timedelta(days=CONTA_NOVA_DIAS) and r.pedidos_da_conta <= CONTA_NOVA_MAX_PEDIDOS:
            s.append("conta_nova")
            quando = "menos de 1 dia" if idade < pd.Timedelta(days=1) else _plural(idade.days, "dia", "dias")
            historico = "sem nenhum pedido" if r.pedidos_da_conta == 0 else "com 1 pedido"
            m.append(f"Conta criada há {quando}, {historico}.")
        dia = r.criado_em.normalize()
        if r.nota <= NOTA_BAIXA and dia in rajadas:
            k, tipico = rajadas[dia]
            s.append("rajada")
            m.append(f"Nota {r.nota} em um dia com {k} avaliações de nota 1–2 (o normal é cerca de "
                     f"{formatar_nota(tipico)} por dia).")
        if idx in parecidas:
            n, outras, dias = parecidas[idx]
            s.append("texto_parecido")
            m.append(f"Texto muito parecido com o de outras {n} avaliações, de {_plural(outras, 'outra conta', 'outras contas')}, "
                     f"em até {_plural(dias, 'dia', 'dias')}.")
        pontos.append(sum(PONTOS[x] for x in s))
        sinais.append(s)
        motivos.append(m)

    out = pd.DataFrame({"suspeita_pontos": pontos, "suspeita_sinais": sinais, "suspeita_motivos": motivos}, index=df.index)
    out["suspeita_nivel"] = out["suspeita_pontos"].map(nivel_da)
    return out


def com_suspeitas(df: pd.DataFrame) -> pd.DataFrame:
    return df.join(analisar_suspeitas(df))


# --- Ver as métricas com e sem as suspeitas --------------------------------------------------
def filtrar_suspeitas(df: pd.DataFrame, modo: str) -> pd.DataFrame:
    """`modo` em MODOS. Só tira da análise; nada é apagado do banco."""
    excluidos = _NIVEIS_EXCLUIDOS[modo]
    return df if not excluidos else df[~df["suspeita_nivel"].isin(excluidos)]


@dataclass(frozen=True)
class ComparacaoMetricas:
    avaliacoes_todas: int
    avaliacoes_sem_suspeitas: int
    nota_todas: float
    nota_sem_suspeitas: float
    negativas_todas: Proporcao
    negativas_sem_suspeitas: Proporcao

    @property
    def removidas(self) -> int:
        return self.avaliacoes_todas - self.avaliacoes_sem_suspeitas

    @property
    def diferenca_nota(self) -> float:
        return self.nota_sem_suspeitas - self.nota_todas


def comparar_metricas(df: pd.DataFrame, modo: str = "medias_e_altas") -> ComparacaoMetricas:
    sem = filtrar_suspeitas(df, modo)

    def negativas(d: pd.DataFrame) -> Proporcao:
        return pct_com_n(int((d["sentimento"] == "negativo").sum()), len(d))

    return ComparacaoMetricas(
        len(df), len(sem), float(df["nota"].mean()), float(sem["nota"].mean()), negativas(df), negativas(sem)
    )


# --- Episódios -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Episodio:
    inicio: pd.Timestamp
    fim: pd.Timestamp
    avaliacoes: int
    altas: int
    nota_media: float
    sem_pedido: Proporcao
    contas_novas: Proporcao
    texto_parecido: Proporcao

    def texto(self) -> str:
        periodo = (
            f"em {self.inicio.strftime('%d/%m')}" if self.inicio.date() == self.fim.date()
            else f"de {self.inicio.strftime('%d/%m')} a {self.fim.strftime('%d/%m')}"
        )

        def parte(p: Proporcao) -> str:
            return f"{p.k} ({formatar_pct(p.pct)})"

        return (
            f"{self.avaliacoes} avaliações suspeitas {periodo}, com nota média {formatar_nota(self.nota_media)}. "
            f"Dessas, {parte(self.sem_pedido)} não têm pedido, {parte(self.contas_novas)} vêm de contas novas "
            f"e {parte(self.texto_parecido)} têm texto parecido com o de outras."
        )


def episodios_suspeitos(df: pd.DataFrame, *, min_avaliacoes: int = 5, lacuna_dias: int = 3) -> list[Episodio]:
    """Agrupa as suspeitas médias e altas em períodos contínuos (a lacuna máxima entre elas é de `lacuna_dias`)."""
    suspeitas = df[df["suspeita_nivel"].isin(("médio", "alto"))].sort_values("criado_em")
    if suspeitas.empty:
        return []
    grupo = (suspeitas["criado_em"].diff() > pd.Timedelta(days=lacuna_dias)).cumsum()
    episodios = []
    for _, g in suspeitas.groupby(grupo):
        if len(g) < min_avaliacoes:
            continue
        n = len(g)
        tem = lambda sinal: int(g["suspeita_sinais"].map(lambda s: sinal in s).sum())  # noqa: E731
        episodios.append(Episodio(
            inicio=g["criado_em"].min(), fim=g["criado_em"].max(), avaliacoes=n,
            altas=int((g["suspeita_nivel"] == "alto").sum()), nota_media=float(g["nota"].mean()),
            sem_pedido=pct_com_n(tem("sem_pedido"), n), contas_novas=pct_com_n(tem("conta_nova"), n),
            texto_parecido=pct_com_n(tem("texto_parecido"), n),
        ))
    return sorted(episodios, key=lambda e: -e.avaliacoes)


def contagem_de_sinais(df: pd.DataFrame) -> Counter:
    return Counter(s for lista in df["suspeita_sinais"] for s in lista)
