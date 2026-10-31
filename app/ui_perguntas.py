"""Aba "Pergunte aos dados": perguntas em linguagem natural respondidas só com consultas calculadas em código."""
from __future__ import annotations

import anthropic
import pandas as pd
import plotly.express as px
import streamlit as st

from copiloto import db
from copiloto.llm.limite import usadas_hoje
from copiloto.qa import textos
from copiloto.qa.agente import Resposta, responder
from copiloto.qa.ferramentas import Grafico, carregar_contexto

COR_PRINCIPAL = "#c2410c"
COR_NEUTRA = "#a8a29e"


def desenhar_grafico(g: Grafico, chave: str) -> None:
    tabela = pd.DataFrame({"x": list(g.x), **{nome: list(valores) for nome, valores in g.series.items()}})
    longa = tabela.melt(id_vars="x", var_name="Série", value_name="valor")
    cores = [COR_NEUTRA, COR_PRINCIPAL] if len(g.series) > 1 else [COR_PRINCIPAL]
    if g.tipo == "linha":
        fig = px.line(longa, x="x", y="valor", color="Série", markers=True, color_discrete_sequence=cores)
    else:
        fig = px.bar(longa.iloc[::-1], x="valor", y="x", orientation="h", color="Série", color_discrete_sequence=cores)
    fig.update_layout(title=g.titulo, xaxis_title=None if g.tipo == "linha" else g.rotulo_y,
                      yaxis_title=g.rotulo_y if g.tipo == "linha" else None, margin=dict(t=40),
                      legend_title=None, showlegend=len(g.series) > 1)
    st.plotly_chart(fig, width="stretch", key=chave)


def _mostrar(resposta: Resposta, indice: int) -> None:
    origem = f"Claude ({resposta.modelo})" if resposta.origem == "claude" else "modo offline (regras)"
    st.markdown(resposta.texto)
    if resposta.aviso:
        st.warning(resposta.aviso)
    if resposta.grafico:
        desenhar_grafico(resposta.grafico, f"grafico_{indice}")
    if resposta.usos:
        with st.expander("Números usados nesta resposta"):
            for uso in resposta.usos:
                argumentos = ", ".join(f"{k}={v}" for k, v in uso.argumentos.items()) or "sem parâmetros"
                if uso.erro:
                    st.markdown(f"**{uso.nome}** ({argumentos}): erro: {uso.erro}")
                    continue
                st.markdown(f"**{uso.nome}** ({argumentos}) · base: {uso.resultado.base}")
                if uso.resultado.sem_dados:
                    st.caption(uso.resultado.motivo)
                else:
                    st.json(uso.resultado.dados, expanded=False)
    st.caption(f"Respondido por: {origem}. Todo número vem de uma consulta calculada em código.")


def desenhar(cfg, df_todas: pd.DataFrame, modo: str) -> None:
    st.subheader("Pergunte aos dados")
    con = db.conectar(cfg.db_path)
    try:
        usadas = usadas_hoje(con)
    finally:
        con.close()
    if cfg.anthropic_api_key:
        st.caption(f"Perguntas livres com o Claude ({cfg.modelo_geracao}); {usadas} de {cfg.limite_diario_llm} chamadas hoje. "
                   "O Claude só consulta os dados por funções definidas no código e os números citados são conferidos.")
    else:
        st.info("**Modo offline.** Sem a chave do Claude, o app reconhece alguns tipos de pergunta (veja os exemplos) e diz "
                "quando não entende. Com a chave, as perguntas passam a ser livres.", icon="ℹ️")

    historico: list[tuple[str, Resposta]] = st.session_state.setdefault("historico_perguntas", [])
    pendente = None
    for linha in (textos.EXEMPLOS[:2], textos.EXEMPLOS[2:4]):
        for coluna, exemplo in zip(st.columns(2), linha):
            if coluna.button(exemplo, key=f"ex_{exemplo}", width="stretch"):
                pendente = exemplo
    pergunta = st.chat_input("Pergunte algo sobre as avaliações…") or pendente

    if pergunta:
        con = db.conectar(cfg.db_path)
        try:
            ctx = carregar_contexto(con, df_todas, modo)
            with st.spinner("Consultando os dados…"):
                resposta = responder(pergunta, ctx, cfg)
            historico.append((pergunta, resposta))
        except ValueError as erro:
            st.error(str(erro))
        except anthropic.AuthenticationError:
            st.error("A chave do Claude foi recusada. Confira ANTHROPIC_API_KEY.")
        finally:
            con.close()

    for i, (feita, resposta) in enumerate(historico):
        with st.chat_message("user"):
            st.write(feita)
        with st.chat_message("assistant"):
            _mostrar(resposta, i)
    if historico and st.button("Limpar conversa"):
        historico.clear()
        st.rerun()
