"""Resumo semanal e API do n8n."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from copiloto.analytics.base import carregar_pedidos
from copiloto.resumo_semanal import PONTOS, gerar_resumo


@pytest.fixture(scope="module")
def categorias(con_classificada):
    return {r["nome"]: r["categoria"] for r in con_classificada.execute("SELECT nome, categoria FROM cardapio")}


@pytest.fixture(scope="module")
def pedidos(con_classificada):
    return carregar_pedidos(con_classificada)


@pytest.fixture(scope="module")
def resumo(df_suspeitas, pedidos, categorias):
    return gerar_resumo(df_suspeitas, pedidos, categorias, url_dashboard="https://exemplo.streamlit.app")


def test_tres_pontos_na_ordem_ataque_entrega_plano(resumo):
    assert PONTOS == 3 and [p.tipo for p in resumo.pontos] == ["ataque", "entrega", "plano"]


def test_o_ataque_vem_primeiro_com_os_numeros_do_episodio(resumo):
    ataque = resumo.pontos[0]
    assert "44 avaliações suspeitas de 14/10 a 16/10" in ataque.detalhe and "só sinaliza" in ataque.sugestao
    assert ataque.numeros["avaliacoes"] >= 40


def test_entrega_da_sexta_a_noite_traz_o_ganho_do_plano_no_mesmo_ponto(resumo):
    ponto = resumo.pontos[1]
    assert "sexta-feira, à noite" in ponto.titulo
    assert re.search(r"contra \d+ min antes \(\+\d+ min\)", ponto.detalhe)
    assert "nota de 3,88 para 4,11" in ponto.detalhe and ponto.numeros["recente_min"] > ponto.numeros["antes_min"]
    assert "escala própria para o pico" in ponto.sugestao


def test_o_plano_nao_repete_a_acao_ja_usada_nem_traz_acao_sem_padrao(resumo):
    terceiro = resumo.pontos[2]
    assert terceiro.titulo == "Melhorar Batata Frita" and "demais casos" not in terceiro.titulo
    assert not any("sexta-feira, à noite" in p.titulo for p in resumo.pontos[2:])


def test_a_semana_e_os_numeros_gerais(resumo, df_suspeitas):
    assert (resumo.inicio, resumo.fim) == (date(2026, 10, 25), date(2026, 10, 31))
    semana = df_suspeitas[(df_suspeitas["criado_em"] >= "2026-10-25") & (df_suspeitas["suspeita_nivel"].isin(["nenhum", "baixo"]))]
    assert resumo.avaliacoes == len(semana)
    assert resumo.nota_media == round(float(semana["nota"].mean()), 2)
    assert resumo.assunto == "Resumo semanal — Cantina Sabor da Vila — 25/10 a 31/10/2026"


def test_texto_e_html_trazem_os_pontos_o_aviso_e_o_link(resumo):
    texto, html = resumo.texto(), resumo.html()
    for i in (1, 2, 3):
        assert f"{i}. " in texto
    assert "Sugestão a avaliar" in texto and "Não são garantia de resultado" in texto
    assert "https://exemplo.streamlit.app" in texto and "href='https://exemplo.streamlit.app'" in html
    assert html.count("<li") == 3 and "<ol" in html


def test_html_escapa_conteudo(df_suspeitas, pedidos, categorias):
    r = gerar_resumo(df_suspeitas, pedidos, categorias, restaurante="<script>alert(1)</script> & Cia")
    assert "<script>" not in r.html() and "&lt;script&gt;" in r.html()


def test_sem_dados_pessoais_no_resumo(resumo, con_classificada):
    conteudo = resumo.texto() + resumo.html()
    for c in con_classificada.execute("SELECT nome, telefone, endereco FROM clientes LIMIT 100"):
        assert c["nome"] not in conteudo and c["telefone"] not in conteudo and c["endereco"] not in conteudo


def test_antes_do_ataque_o_resumo_cai_para_o_plano(df_suspeitas, pedidos, categorias):
    r = gerar_resumo(df_suspeitas, pedidos, categorias, ate=date(2026, 9, 30))
    assert (r.inicio, r.fim) == (date(2026, 9, 24), date(2026, 9, 30))
    assert "ataque" not in {p.tipo for p in r.pontos} and len(r.pontos) == 3


def test_semana_sem_avaliacoes_nao_quebra(df_suspeitas, pedidos, categorias):
    r = gerar_resumo(df_suspeitas, pedidos, categorias, ate=date(2026, 12, 31))
    assert r.avaliacoes == 0 and r.nota_media is None
    assert "nenhuma avaliação recebida" in r.texto() and len(r.pontos) == 3


def test_dados_de_depois_da_data_nao_entram(df_suspeitas, pedidos, categorias):
    r = gerar_resumo(df_suspeitas, pedidos, categorias, ate=date(2026, 10, 13))
    assert "ataque" not in {p.tipo for p in r.pontos}                 # o ataque é de 14 a 16/10


# --- API --------------------------------------------------------------------------------------------------------
@pytest.fixture()
def cliente(dados, monkeypatch):
    monkeypatch.setenv("COPILOTO_DB", str(dados[0]))
    monkeypatch.delenv("COPILOTO_API_TOKEN", raising=False)
    from api import main

    main._dados.cache_clear()
    return TestClient(main.app)


def test_saude(cliente):
    assert cliente.get("/health").json() == {"status": "ok"}


def test_resumo_semanal_devolve_assunto_texto_html_e_pontos(cliente):
    r = cliente.get("/weekly-summary")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["assunto"].startswith("Resumo semanal") and corpo["texto"] and corpo["html"].startswith("<div")
    assert [p["tipo"] for p in corpo["pontos"]] == ["ataque", "entrega", "plano"]
    assert corpo["semana"] == {"inicio": "2026-10-25", "fim": "2026-10-31"}


def test_parametros_ate_e_modo(cliente):
    corpo = cliente.get("/weekly-summary", params={"ate": "2026-09-30", "modo": "todas"}).json()
    assert corpo["semana"]["fim"] == "2026-09-30"
    assert cliente.get("/weekly-summary", params={"ate": "ontem"}).status_code == 422
    assert cliente.get("/weekly-summary", params={"modo": "qualquer"}).status_code == 422


def test_token_e_exigido_quando_configurado(cliente, monkeypatch):
    monkeypatch.setenv("COPILOTO_API_TOKEN", "segredo-de-teste")
    assert cliente.get("/weekly-summary").status_code == 401
    assert cliente.get("/weekly-summary", headers={"X-API-Token": "errado"}).status_code == 401
    assert cliente.get("/weekly-summary", headers={"X-API-Token": "segredo-de-teste"}).status_code == 200
    assert cliente.get("/health").status_code == 200                  # a verificação de saúde fica aberta


def test_resposta_da_api_nao_traz_dados_de_clientes(cliente, con_classificada):
    corpo = cliente.get("/weekly-summary").text
    for c in con_classificada.execute("SELECT nome, telefone, endereco FROM clientes LIMIT 100"):
        assert c["nome"] not in corpo and c["telefone"] not in corpo
