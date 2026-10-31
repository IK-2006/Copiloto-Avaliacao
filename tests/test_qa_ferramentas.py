"""Ferramentas de consulta: validação, números corretos, nada de texto de avaliação nos resultados."""
import dataclasses
import json

import pandas as pd
import pytest

from copiloto.analytics.pratos import analise_por_prato
from copiloto.qa.ferramentas import FERRAMENTAS, ErroDeFerramenta, ResultadoFerramenta


def rodar(contexto, nome: str, **argumentos) -> ResultadoFerramenta:
    return FERRAMENTAS[nome].executar(contexto, argumentos)


def test_cada_ferramenta_tem_definicao_no_formato_da_api():
    assert set(FERRAMENTAS) == {"nota_por_mes", "nota_media", "ranking_de_pratos", "temas_de_reclamacao", "causa_raiz",
                                "causa_raiz_do_prato", "plano_de_acao", "avaliacoes_suspeitas", "explicar_variacao_da_nota"}
    for f in FERRAMENTAS.values():
        s = f.schema()
        assert s["name"] == f.nome and s["description"]
        assert s["input_schema"]["type"] == "object" and s["input_schema"]["additionalProperties"] is False
        assert set(s["input_schema"]["required"]) <= set(s["input_schema"]["properties"])
        json.dumps(s)                                                       # serializável


# --- Validação dos parâmetros -----------------------------------------------------------------------
@pytest.mark.parametrize(
    "ferramenta,argumentos,trecho",
    [
        ("causa_raiz", {}, "falta o parâmetro"),
        ("causa_raiz", {"tema": "inventado"}, "deve ser um de"),
        ("causa_raiz", {"tema": "atraso", "extra": 1}, "desconhecidos"),
        ("nota_media", {"mes": "outubro"}, "AAAA-MM"),
        ("nota_media", {"mes": "2026-13"}, "AAAA-MM"),
        ("nota_media", {"mes": 10}, "deve ser texto"),
        ("ranking_de_pratos", {"prato": "Lagosta"}, "prato desconhecido"),
        ("ranking_de_pratos", {"limite": 0}, "entre 1 e 10"),
        ("ranking_de_pratos", {"limite": 99}, "entre 1 e 10"),
        ("ranking_de_pratos", {"limite": True}, "inteiro"),
        ("ranking_de_pratos", {"limite": "5"}, "inteiro"),
    ],
)
def test_parametros_invalidos_sao_recusados(contexto, ferramenta, argumentos, trecho):
    with pytest.raises(ErroDeFerramenta, match=trecho):
        rodar(contexto, ferramenta, **argumentos)


def test_argumentos_que_nao_sao_objeto_sao_recusados(contexto):
    with pytest.raises(ErroDeFerramenta):
        FERRAMENTAS["nota_media"].executar(contexto, ["2026-10"])


def test_prato_aceita_apelido_e_acentos(contexto):
    r = rodar(contexto, "ranking_de_pratos", prato="batata")
    assert r.dados["pratos"][0]["prato"] == "Batata Frita"
    assert rodar(contexto, "ranking_de_pratos", prato="acai").dados["pratos"][0]["prato"] == "Açaí 500ml"


# --- Os números são os das análises ----------------------------------------------------------------------
def test_ranking_de_pratos_bate_com_a_analise(contexto):
    r = rodar(contexto, "ranking_de_pratos", limite=3)
    analises = {a.prato: a for a in analise_por_prato(contexto.con, contexto.df)}
    primeiro = r.dados["pratos"][0]
    assert primeiro["prato"] == "Batata Frita"
    esperado = analises["Batata Frita"].com_problema
    assert (primeiro["com_problema"]["k"], primeiro["com_problema"]["n"]) == (esperado.k, esperado.n)
    assert len(r.dados["pratos"]) == 3 and r.grafico.tipo == "barra"
    assert r.dados["prato_com_mais_reclamacoes_em_numero"]["prato"] == "Batata Frita"


def test_nota_media_traz_todas_e_sem_suspeitas(contexto):
    r = rodar(contexto, "nota_media")
    assert r.dados["todas"]["avaliacoes"] == len(contexto.todas) and r.dados["todas"]["nota"] == round(contexto.todas["nota"].mean(), 2)
    assert r.dados["sem_suspeitas"]["nota"] > r.dados["todas"]["nota"]
    assert r.dados["diferenca_sem_suspeitas"] > 0.15


def test_nota_por_mes_cobre_os_seis_meses_com_grafico_de_duas_series(contexto):
    r = rodar(contexto, "nota_por_mes")
    assert [m["mes"] for m in r.dados["meses"]] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert len(r.grafico.series) == 2 and r.grafico.tipo == "linha"
    outubro = r.dados["meses"][-1]
    assert outubro["sem_suspeitas"]["nota"] - outubro["todas"]["nota"] > 0.5


def test_causa_raiz_devolve_frases_e_numeros(contexto):
    r = rodar(contexto, "causa_raiz", tema="temperatura")
    primeiro = r.dados["quando_e_onde"][0]
    assert "sexta-feira, à noite" in primeiro["segmento"]
    assert primeiro["parcela_das_reclamacoes"]["k"] <= primeiro["parcela_das_reclamacoes"]["n"]
    assert primeiro["evidencia"].startswith("chance de ser acaso")


def test_tema_sem_padrao_diz_que_os_dados_nao_concluem(contexto):
    r = rodar(contexto, "causa_raiz", tema="sabor")
    assert r.sem_dados and "concentra" in r.motivo


def test_mes_fora_do_periodo_diz_o_intervalo_dos_dados(contexto):
    r = rodar(contexto, "nota_media", mes="2026-11")
    assert r.sem_dados and "01/05/2026 a 31/10/2026" in r.motivo
    assert rodar(contexto, "explicar_variacao_da_nota", mes="2026-05").sem_dados


def test_plano_e_suspeitas_e_variacao(contexto):
    plano = rodar(contexto, "plano_de_acao", limite=2)
    assert len(plano.dados["acoes"]) == 2 and plano.dados["acoes"][0]["ganho_completo"] >= plano.dados["acoes"][1]["ganho_completo"]
    susp = rodar(contexto, "avaliacoes_suspeitas")
    assert susp.dados["episodios"] and susp.dados["niveis"]["alto"] >= 40
    var = rodar(contexto, "explicar_variacao_da_nota", mes="2026-10")
    assert var.dados["nota"]["efeito_das_suspeitas"] >= 0.6 and var.grafico is not None


def test_filtro_de_suspeitas_muda_a_base_das_ferramentas(contexto):
    todas = dataclasses.replace(contexto, modo="todas")
    r_todas, r_sem = rodar(todas, "plano_de_acao"), rodar(contexto, "plano_de_acao")
    assert r_todas.base != r_sem.base and r_sem.dados["nota_atual"] > r_todas.dados["nota_atual"]


# --- Segurança dos resultados ------------------------------------------------------------------------------
def todos_os_resultados(contexto) -> list[ResultadoFerramenta]:
    return [
        rodar(contexto, "nota_por_mes"), rodar(contexto, "nota_media"), rodar(contexto, "ranking_de_pratos"),
        rodar(contexto, "temas_de_reclamacao"), rodar(contexto, "causa_raiz", tema="atraso"),
        rodar(contexto, "causa_raiz_do_prato", prato="Batata Frita"), rodar(contexto, "plano_de_acao"),
        rodar(contexto, "avaliacoes_suspeitas"), rodar(contexto, "explicar_variacao_da_nota", mes="2026-10"),
    ]


def test_resultados_nao_trazem_texto_de_avaliacoes_nem_dados_de_clientes(contexto):
    saida = " ".join(r.para_modelo() for r in todos_os_resultados(contexto))
    for texto in contexto.todas["texto"].head(80):
        if len(texto) > 30:
            assert texto not in saida
    for c in contexto.con.execute("SELECT nome, telefone, endereco FROM clientes LIMIT 50"):
        assert c["nome"] not in saida and c["telefone"] not in saida and c["endereco"] not in saida
    assert "instruções anteriores" not in saida.lower()                      # as injeções plantadas não aparecem


def test_resultados_sao_json_e_as_ferramentas_nao_alteram_os_dados(contexto):
    antes = contexto.todas.copy(deep=True)
    for r in todos_os_resultados(contexto):
        assert isinstance(json.loads(r.para_modelo()), dict)
    pd.testing.assert_frame_equal(antes, contexto.todas)
