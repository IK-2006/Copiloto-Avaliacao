"""Aba "Respostas": rascunhos de resposta às avaliações negativas, para o dono editar e aprovar."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from copiloto import db, respostas
from copiloto.llm.limite import usadas_hoje

ROTULO_STATUS = {"rascunho": "Rascunhos", "aprovada": "Aprovadas", "descartada": "Descartadas"}
POR_PAGINA = 12


def _aplicar(cfg, operacao, *argumentos) -> None:
    con = db.conectar(cfg.db_path)
    try:
        operacao(con, *argumentos)
    except (ValueError, KeyError) as erro:
        st.session_state["erro_resposta"] = str(erro)
    finally:
        con.close()


def desenhar(cfg, df_todas: pd.DataFrame) -> None:
    st.subheader("Respostas sugeridas às avaliações negativas")
    st.info(
        "**Nada é publicado automaticamente.** O app só escreve rascunhos. Você edita, e \"Aprovar\" apenas marca o "
        "texto como pronto para você copiar e publicar na plataforma.",
        icon="✋",
    )
    if erro := st.session_state.pop("erro_resposta", None):
        st.error(erro)

    con = db.conectar(cfg.db_path)
    try:
        suspeitas = set(df_todas.loc[df_todas["suspeita_nivel"].isin(["médio", "alto"]), "avaliacao_id"].astype(int))
        candidatas = respostas.ids_candidatos(con, excluir=suspeitas)
        puladas = len(respostas.ids_candidatos(con)) - len(candidatas)
        contagem = {s: len(respostas.listar(con, s)) for s in respostas.STATUS}
        gerador = respostas.obter_gerador(cfg)
        usadas = usadas_hoje(con)
    finally:
        con.close()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sem rascunho", len(candidatas), help="Avaliações negativas ainda sem resposta sugerida.")
    c2.metric("Rascunhos", contagem["rascunho"])
    c3.metric("Aprovadas", contagem["aprovada"])
    c4.metric("Descartadas", contagem["descartada"])
    if puladas:
        st.caption(f"{puladas} avaliações negativas suspeitas (médias ou altas) não recebem rascunho: avalie "
                   "contestá-las na aba Suspeitas antes de responder.")

    usa_claude = gerador.nome == "claude"
    st.caption(
        f"Gerador: **Claude** ({gerador.modelo}), {usadas} de {cfg.limite_diario_llm} chamadas hoje; se uma resposta "
        "for inválida, o rascunho cai para as regras." if usa_claude else
        "Gerador: **regras** (offline), com modelos de frase escolhidos pelos temas e pratos da avaliação. "
        "Com a chave do Claude o texto fica mais personalizado."
    )
    cima, baixo = st.columns([1, 3])
    quantas = cima.number_input("Quantos gerar agora", min_value=1, max_value=50, value=min(10, max(1, len(candidatas))))
    if baixo.button("Gerar rascunhos", type="primary", disabled=not candidatas):
        con = db.conectar(cfg.db_path)
        try:
            resumo = respostas.gerar_rascunhos(con, candidatas[: int(quantas)], gerador, limite_diario=cfg.limite_diario_llm)
        finally:
            con.close()
        st.session_state["resumo_rascunhos"] = resumo
        st.rerun()
    if resumo := st.session_state.pop("resumo_rascunhos", None):
        st.success(
            f"{resumo.criados} rascunhos criados ({resumo.pelo_claude} pelo Claude, {resumo.pelas_regras} pelas regras; "
            f"{resumo.reserva_por_falha} caíram para as regras por resposta inválida, {resumo.reserva_por_injecao} por "
            f"tentativa de injeção e {resumo.reserva_por_limite} por limite diário)."
        )

    st.divider()
    status = st.radio("Mostrar", list(ROTULO_STATUS), format_func=lambda s: f"{ROTULO_STATUS[s]} ({contagem[s]})", horizontal=True)
    con = db.conectar(cfg.db_path)
    try:
        lista = respostas.listar(con, status)
    finally:
        con.close()
    if lista.empty:
        st.info("Nenhuma resposta neste grupo.")
        return
    if len(lista) > POR_PAGINA:
        st.caption(f"Mostrando {POR_PAGINA} de {len(lista)}.")

    for _, r in lista.head(POR_PAGINA).iterrows():
        id_ = int(r["avaliacao_id"])
        with st.container(border=True):
            st.caption(f"Avaliação #{id_} · nota {int(r['nota'])} · {r['avaliada_em']} · rascunho de: {r['provedor']}")
            st.markdown(f"> {r['avaliacao']}")
            if status == "rascunho":
                texto = st.text_area("Resposta (edite à vontade)", value=r["texto_final"], key=f"texto_{id_}", height=180)
                a, b, c = st.columns(3)
                if a.button("Salvar edição", key=f"salvar_{id_}"):
                    _aplicar(cfg, respostas.editar, id_, texto)
                    st.rerun()
                if b.button("Aprovar", key=f"aprovar_{id_}", type="primary"):
                    def salvar_e_aprovar(con, id_, texto):
                        respostas.editar(con, id_, texto)
                        respostas.aprovar(con, id_)
                    _aplicar(cfg, salvar_e_aprovar, id_, texto)
                    st.rerun()
                if c.button("Descartar", key=f"descartar_{id_}"):
                    _aplicar(cfg, respostas.descartar, id_)
                    st.rerun()
            else:
                st.code(r["texto_final"], language=None, wrap_lines=True)
                if st.button("Reabrir como rascunho", key=f"reabrir_{id_}"):
                    _aplicar(cfg, respostas.reabrir, id_)
                    st.rerun()

    if status == "aprovada":
        st.download_button("Baixar as aprovadas (CSV)", lista[["avaliacao_id", "avaliada_em", "nota", "texto_final"]]
                           .to_csv(index=False).encode("utf-8-sig"), file_name="respostas_aprovadas.csv", mime="text/csv")
