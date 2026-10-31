"""Dashboard do Copiloto de Avaliações. Execute: streamlit run app/streamlit_app.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from copiloto import config, db
from copiloto.analytics.base import carregar_avaliacoes, carregar_pedidos
from copiloto.analytics.causa_raiz import (
    DIMENSOES_QUANDO_ONDE,
    Padrao,
    causas_da_entrega_lenta,
    causas_do_prato,
    causas_por_tema,
    comparar_tempos,
    evolucao_do_padrao,
    evolucao_tempos,
    rotulo_evento_tema,
)
from copiloto.analytics.pratos import AnalisePrato, analise_por_prato, ranking_pratos
from copiloto.analytics.series import nota_por_semana, ranking_temas, resumo_geral, temas_por_semana
from copiloto.analytics.tendencias import alertas_tendencia
from copiloto.dominio import ROTULO_TEMA
from copiloto.stats import formatar_nota, formatar_pct

st.set_page_config(page_title="Copiloto de Avaliações", page_icon="🍽️", layout="wide")

COR_PRINCIPAL = "#c2410c"
COR_NEUTRA = "#a8a29e"


@st.cache_data(show_spinner=False)
def carregar(db_path: str, versao_arquivo: float) -> pd.DataFrame:
    con = db.conectar(db_path)
    try:
        return carregar_avaliacoes(con)
    finally:
        con.close()


@st.cache_data(show_spinner="Procurando padrões nos pedidos…")
def calcular_causas(db_path: str, versao_arquivo: float):
    """Causa raiz por tema (mecanismo e quando/onde), por prato e das entregas lentas."""
    con = db.conectar(db_path)
    try:
        avaliacoes, pedidos = carregar_avaliacoes(con), carregar_pedidos(con)
    finally:
        con.close()
    pratos = sorted({i for itens in pedidos["itens"] for i in itens})
    return {
        "pedidos": pedidos,
        "mecanismo": causas_por_tema(avaliacoes, pedidos),
        "quando_onde": causas_por_tema(avaliacoes, pedidos, dimensoes=DIMENSOES_QUANDO_ONDE),
        "pratos": {p: causas_do_prato(avaliacoes, pedidos, p) for p in pratos},
        "lentas": causas_da_entrega_lenta(pedidos),
    }


def cartao_padrao(padrao: Padrao, rotulo_evento: str, **kwargs) -> None:
    with st.container(border=True):
        st.markdown(f"**{padrao.segmento[:1].upper()}{padrao.segmento[1:]}**")
        st.write(padrao.texto(rotulo_evento, **kwargs))
        st.caption(padrao.evidencia.capitalize() + ".")


def analisar_pratos(db_path: str, df: pd.DataFrame) -> list[AnalisePrato]:
    con = db.conectar(db_path)
    try:
        return analise_por_prato(con, df)
    finally:
        con.close()


def aviso_baixa_confianca(analise: AnalisePrato) -> None:
    if analise.baixa_confianca:
        st.warning(
            f"Baixa confiança: só {analise.mencoes} avaliações citam {analise.prato}. "
            "Com tão poucas, a porcentagem muda muito a cada nova avaliação."
        )


cfg = config.carregar()
if not cfg.db_path.exists():
    st.error("Banco de dados não encontrado. Rode `python -m copiloto.datagen` e `python -m copiloto.classify`.")
    st.stop()

df = carregar(str(cfg.db_path), cfg.db_path.stat().st_mtime)
if df.empty:
    st.error("Nenhuma avaliação classificada. Rode `python -m copiloto.classify`.")
    st.stop()

st.title("🍽️ Copiloto de Avaliações")
st.caption(
    "Restaurante e dados **fictícios**, criados para demonstração. "
    "Todo percentual mostra em quantas avaliações se baseia e é calculado em código, não pela IA."
)

geral = resumo_geral(df)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Avaliações", geral["avaliacoes"])
c2.metric("Nota média", formatar_nota(geral["nota_media"]))
c3.metric("Avaliações negativas", formatar_pct(geral["negativas"].pct), help=geral["negativas"].texto())
c4.metric("Com pedido associado", formatar_pct(geral["com_pedido"].pct), help=geral["com_pedido"].texto())

aba_geral, aba_pratos, aba_causa, aba_seguranca, aba_dados = st.tabs(
    ["Visão geral", "Análise por prato", "Causa raiz", "Segurança", "Sobre os dados"]
)

with aba_geral:
    for alerta in alertas_tendencia(df):
        st.warning(f"**Alerta de tendência.** {alerta.texto()}", icon="📈")
    st.subheader("Nota média por semana")
    semanal = nota_por_semana(df)
    fig = px.line(semanal, x="semana", y="nota_media", markers=True, custom_data=["avaliacoes"])
    fig.update_traces(
        line_color=COR_PRINCIPAL,
        hovertemplate="Semana de %{x|%d/%m}<br>Nota média: %{y:.2f}<br>%{customdata[0]} avaliações<extra></extra>",
    )
    fig.update_layout(yaxis_title="Nota média (1 a 5)", xaxis_title=None, yaxis_range=[1, 5], margin=dict(t=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("Etapa 4 acrescenta a comparação com e sem avaliações suspeitas.")

    esq, dir_ = st.columns([2, 3])
    with esq:
        st.subheader("Principais temas de reclamação")
        ranking = ranking_temas(df)
        tabela = pd.DataFrame(
            {
                "Tema": [ROTULO_TEMA[t] for t, _ in ranking],
                "% das avaliações": [p.pct for _, p in ranking],
                "Avaliações": [f"{p.k} de {p.n}" for _, p in ranking],
            }
        )
        fig = px.bar(tabela.iloc[::-1], x="% das avaliações", y="Tema", orientation="h", text="Avaliações")
        fig.update_traces(marker_color=COR_PRINCIPAL, textposition="outside", cliponaxis=False)
        fig.update_layout(xaxis_title="% das avaliações que citam o tema", yaxis_title=None, margin=dict(t=10))
        fig.update_xaxes(range=[0, tabela["% das avaliações"].max() * 1.35])
        st.plotly_chart(fig, width="stretch")
    with dir_:
        st.subheader("Evolução semanal dos temas")
        evolucao = temas_por_semana(df)
        principais = [t for t, _ in ranking[:4]]
        evolucao = evolucao[evolucao["tema"].isin(principais)].assign(
            Tema=lambda d: d["tema"].map(ROTULO_TEMA)
        )
        fig = px.line(evolucao, x="semana", y="pct", color="Tema", custom_data=["k", "n"],
                      color_discrete_sequence=["#c2410c", "#1d4ed8", "#15803d", "#7c3aed"])
        fig.update_traces(
            hovertemplate="Semana de %{x|%d/%m}<br>%{customdata[0]} de %{customdata[1]} avaliações"
            " (%{y:.0f}%)<extra>%{fullData.name}</extra>"
        )
        fig.update_layout(yaxis_title="% das avaliações da semana", xaxis_title=None, margin=dict(t=10))
        st.plotly_chart(fig, width="stretch")

with aba_pratos:
    analises = analisar_pratos(str(cfg.db_path), df)
    ordenadas = ranking_pratos(analises)
    st.subheader("Ranking de pratos por problemas")
    st.caption(
        "Base: avaliações que citam o prato. Pratos com menos de 20 avaliações aparecem com aviso "
        "de baixa confiança e vão para o fim da lista."
    )
    ranking_df = pd.DataFrame(
        {
            "Prato": [a.prato for a in ordenadas],
            "% com problema": [a.com_problema.pct for a in ordenadas],
            "Base": [a.com_problema.texto() for a in ordenadas],
            "Confiança": ["baixa" if a.baixa_confianca else "ok" for a in ordenadas],
        }
    )
    fig = px.bar(
        ranking_df.iloc[::-1], x="% com problema", y="Prato", orientation="h", color="Confiança",
        color_discrete_map={"ok": COR_PRINCIPAL, "baixa": COR_NEUTRA}, custom_data=["Base"],
    )
    fig.update_traces(hovertemplate="%{y}: %{customdata[0]}<extra></extra>")
    fig.update_layout(xaxis_title="% das avaliações que citam o prato e relatam problema", yaxis_title=None,
                      height=620, margin=dict(t=10))
    st.plotly_chart(fig, width="stretch")

    st.subheader("Detalhe do prato")
    nomes = [a.prato for a in ordenadas]
    escolhido = st.selectbox("Prato", nomes, index=0)
    a = next(x for x in analises if x.prato == escolhido)
    aviso_baixa_confianca(a)
    e, d = st.columns(2)
    e.metric("Avaliações que citam o prato", a.mencoes, help=f"{a.pedidos} pedidos incluíram este prato.")
    d.metric("Com algum problema", a.com_problema.texto())
    if a.problemas:
        detalhe = pd.DataFrame(
            {
                "Problema": [ROTULO_TEMA[t] for t, _ in a.problemas],
                "% das menções": [p.pct for _, p in a.problemas],
                "Base": [p.texto() for _, p in a.problemas],
            }
        )
        fig = px.bar(detalhe.iloc[::-1], x="% das menções", y="Problema", orientation="h", custom_data=["Base"])
        fig.update_traces(marker_color=COR_PRINCIPAL, hovertemplate="%{customdata[0]}<extra></extra>")
        fig.update_layout(xaxis_title="% das avaliações que citam o prato", yaxis_title=None, margin=dict(t=10),
                          height=80 + 50 * len(detalhe))
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Nenhum problema citado para este prato.")
    exemplos = df[df["pratos"].map(lambda ps: any(p["prato"] == escolhido and p["problemas"] for p in ps))]
    if not exemplos.empty:
        with st.expander(f"Exemplos de avaliações com problema ({len(exemplos)})"):
            for _, linha in exemplos.head(8).iterrows():
                st.markdown(f"**{int(linha['nota'])}★** — {linha['texto']}")

def desenhar_causa_raiz() -> None:
    causas = calcular_causas(str(cfg.db_path), cfg.db_path.stat().st_mtime)
    pedidos = causas["pedidos"]
    com_pedido = df[df["tem_pedido"]]
    st.subheader("Em que condições cada problema aparece")
    st.caption(
        "Cruza as avaliações com dia, horário, tempos de preparo e entrega e distância do pedido. Só aparecem "
        "padrões que resistem a um teste estatístico com correção para múltiplas comparações; se nada "
        "aparece para um tema, os dados não mostram concentração."
    )
    ordem = [t for t, _ in ranking_temas(df)]
    com_padrao = [t for t in ordem if causas["mecanismo"][t] or causas["quando_onde"][t]]
    if not com_padrao:
        st.info("Nenhum problema mostra concentração consistente nos dados atuais.")
        return
    tema = st.selectbox("Problema", com_padrao, format_func=lambda t: ROTULO_TEMA[t])
    rotulo = rotulo_evento_tema(tema)
    esq, dir_ = st.columns(2)
    with esq:
        st.markdown("##### Qual condição do pedido?")
        for p in causas["mecanismo"][tema] or []:
            cartao_padrao(p, rotulo)
        if not causas["mecanismo"][tema]:
            st.info("Nenhuma condição do pedido concentra este problema.")
    with dir_:
        st.markdown("##### Quando e onde?")
        for p in causas["quando_onde"][tema] or []:
            cartao_padrao(p, rotulo)
        if not causas["quando_onde"][tema]:
            st.info("Nenhum dia, turno ou distância concentra este problema.")

    principal = (causas["quando_onde"][tema] or causas["mecanismo"][tema])[0]
    evolucao = evolucao_do_padrao(com_pedido, com_pedido["temas"].map(lambda ts: tema in ts), principal.condicoes)
    st.markdown(f"##### O problema piorou? {principal.segmento[:1].upper()}{principal.segmento[1:]}, mês a mês")
    fig = px.line(evolucao, x="mes", y="pct", color="grupo", markers=True, custom_data=["k", "n"],
                  color_discrete_map={"No segmento": COR_PRINCIPAL, "Demais pedidos": COR_NEUTRA})
    fig.update_traces(hovertemplate="%{x|%b/%Y}: %{customdata[0]} de %{customdata[1]} avaliações (%{y:.0f}%)"
                                    "<extra>%{fullData.name}</extra>")
    fig.update_layout(yaxis_title="% das avaliações que citam o problema", xaxis_title=None, margin=dict(t=10),
                      legend_title=None)
    st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("Por que as entregas demoram?")
    st.caption("Usa todos os pedidos (não só os avaliados): quando e onde as entregas passam de 40 minutos.")
    for p in causas["lentas"]:
        cartao_padrao(p, "entregas acima de 40 min", unidade="pedidos", predicado="têm entrega acima de 40 min")
        tempos = comparar_tempos(pedidos, p.condicoes)
        st.dataframe(
            pd.DataFrame(
                {
                    "Tempo médio": ["Preparo na cozinha", "Deslocamento até o cliente", "Total até a porta"],
                    "No segmento": [f"{tempos[k]['no_segmento']:.0f} min" for k in ("preparo", "deslocamento", "entrega")],
                    "Demais pedidos": [f"{tempos[k]['demais']:.0f} min" for k in ("preparo", "deslocamento", "entrega")],
                }
            ),
            hide_index=True,
        )
    if causas["lentas"]:
        mensal = evolucao_tempos(pedidos, causas["lentas"][-1].condicoes)
        st.markdown("##### Tempo médio de entrega por mês")
        fig = px.line(mensal, x="mes", y="entrega_media", color="grupo", markers=True, custom_data=["pedidos"],
                      color_discrete_map={"No segmento": COR_PRINCIPAL, "Demais pedidos": COR_NEUTRA})
        fig.update_traces(hovertemplate="%{x|%b/%Y}: %{y:.0f} min (%{customdata[0]} pedidos)<extra>%{fullData.name}</extra>")
        fig.update_layout(yaxis_title="Minutos até a porta", xaxis_title=None, margin=dict(t=10), legend_title=None)
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Segmento acompanhado: {causas['lentas'][-1].segmento}.")

    st.divider()
    st.subheader("Causa raiz por prato")
    com_causa = [p for p, ps in causas["pratos"].items() if ps]
    prato = st.selectbox("Prato", com_causa, key="prato_causa") if com_causa else None
    for p in (causas["pratos"][prato] if prato else []):
        cartao_padrao(p, "reclamações do prato")
    st.caption(
        "Base: avaliações de pedidos que incluíram o prato, citem-no ou não. Quem avalia não é uma amostra "
        "aleatória dos clientes (quem teve problema costuma avaliar mais); as taxas descrevem as avaliações, "
        "não todos os pedidos."
    )


with aba_causa:
    desenhar_causa_raiz()

with aba_seguranca:
    st.subheader("Texto de avaliação é dado, nunca instrução")
    suspeitas = df[df["injecao"]]
    st.write(
        f"**{len(suspeitas)}** avaliações tentaram dar ordens ao sistema (por exemplo, "
        "“ignore as instruções anteriores”). Elas foram classificadas normalmente, pelo que o cliente "
        "relata sobre a comida, e sinalizadas aqui."
    )
    for _, linha in suspeitas.iterrows():
        st.markdown(f"> {linha['texto']}")
        st.caption(
            f"Classificada como **{linha['sentimento']}**, temas: "
            f"{', '.join(ROTULO_TEMA[t] for t in linha['temas']) or 'nenhum'}."
        )
    st.markdown(
        "- A IA só pode responder com valores de listas fechadas (sentimento, temas, pratos).\n"
        "- Nome, telefone e endereço dos clientes nunca são enviados à IA.\n"
        "- Respostas sugeridas (Etapa 5) ficam como rascunho até o dono aprovar."
    )

with aba_dados:
    st.subheader("Padrões plantados nos dados")
    caminho = cfg.db_path.parent / "plantados.json"
    if caminho.exists():
        plantados = json.loads(caminho.read_text(encoding="utf-8"))
        for p in plantados["padroes"]:
            st.markdown(f"**{p['id']} — {p['titulo']}**  \n{p['regra']}  \n*Onde ver:* {p['onde_ver']}")
        resumo = plantados["resumo"]
        st.caption(
            f"{resumo['pedidos']} pedidos e {resumo['avaliacoes']} avaliações, de {resumo['periodo'][0]} "
            f"a {resumo['periodo'][1]} (seed {resumo['seed']})."
        )
    provedores = ", ".join(sorted(df["provedor"].unique()))
    st.caption(f"Classificação feita por: {provedores}.")
