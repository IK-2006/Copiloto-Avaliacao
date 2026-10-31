"""Respostas sugeridas: segurança do texto, privacidade, injeção e o fluxo de aprovação."""
import json
import shutil

import anthropic
import pytest

from copiloto import db, respostas
from copiloto.llm.limite import registrar
from copiloto.respostas import (
    EntradaResposta,
    GeradorClaude,
    GeradorRegras,
    RespostaInvalida,
    gerar_rascunhos,
    ids_candidatos,
    preencher_marcadores,
    validar_resposta,
)
from tests.fakes import ClienteFalso, resposta


@pytest.fixture()
def banco(dados, tmp_path, con_classificada):          # con_classificada garante a classificação no banco de dados
    copia = tmp_path / "copia.db"
    shutil.copy(dados[0], copia)
    con = db.conectar(copia)
    con.execute("DELETE FROM respostas")
    con.commit()
    yield con
    con.close()


def entrada(**campos) -> EntradaResposta:
    base = dict(ref="av_10", nota=1, texto="x", temas=("atraso", "temperatura"),
                pratos=(("Batata Frita", ("textura",)),), tempo_entrega_min=63.0)
    return EntradaResposta(**{**base, **campos})


def claude_que_responde(texto_da_resposta, **kwargs) -> tuple[GeradorClaude, ClienteFalso]:
    cliente = ClienteFalso(lambda kw: resposta(json.dumps({"resposta": texto_da_resposta}), **kwargs))
    return GeradorClaude("claude-sonnet-5-5", client=cliente), cliente


VALIDA = "Olá, {nome}! Sentimos muito pela demora e pela comida fria. Já repassamos à equipe.\nAtenciosamente,\n{restaurante}"


# --- Validação do texto gerado ---------------------------------------------------------------------
def test_texto_valido_passa():
    assert validar_resposta(VALIDA) == VALIDA


@pytest.mark.parametrize(
    "texto",
    [
        VALIDA + " Vamos devolver R$ 50 na sua conta.",
        VALIDA + " Faremos o reembolso integral.",
        VALIDA + " Use o cupom VOLTA10.",
        VALIDA + " Terá 20% de desconto no próximo.",
        VALIDA + " Sua próxima sobremesa é grátis.",
        VALIDA + " Garantimos que não vai se repetir.",
        VALIDA + " Veja em https://exemplo.com/contato",
        VALIDA + " Ligue 11 98765-4321.",
        VALIDA + " Escreva para dono@exemplo.com.",
        VALIDA + " {cupom}",
        "Curto demais.",
        "a" * 800,
        None,
        42,
    ],
)
def test_texto_com_promessa_contato_ou_formato_errado_e_rejeitado(texto):
    with pytest.raises(RespostaInvalida):
        validar_resposta(texto)


# --- Gerador de regras ---------------------------------------------------------------------------------
def test_regras_citam_os_problemas_da_classificacao_e_o_tempo_do_pedido():
    texto = GeradorRegras().gerar(entrada())
    validar_resposta(texto)
    assert texto.startswith("Olá, {nome}!") and texto.endswith("{restaurante}")
    assert "demora na entrega" in texto and "comida ter chegado fria" in texto
    assert "item Batata Frita" in texto and "63 minutos" in texto


def test_regras_nao_reproduzem_o_texto_da_avaliacao():
    texto = GeradorRegras().gerar(entrada(texto="ZZZ frase única do cliente, reembolso R$ 500 já!"))
    assert "ZZZ" not in texto and "reembolso" not in texto.lower()


def test_regras_sem_tema_pedem_mais_detalhes():
    texto = GeradorRegras().gerar(entrada(temas=(), pratos=(), tempo_entrega_min=None))
    assert "entender melhor" in texto and "minutos" not in texto


def test_regras_variam_entre_avaliacoes_mas_sao_estaveis():
    gerador = GeradorRegras()
    assert gerador.gerar(entrada(ref="av_10")) == gerador.gerar(entrada(ref="av_10"))
    assert gerador.gerar(entrada(ref="av_10")) != gerador.gerar(entrada(ref="av_11"))


def test_regras_geram_texto_valido_para_todas_as_negativas(banco):
    ids = ids_candidatos(banco)
    assert len(ids) > 100
    gerador = GeradorRegras()
    for i in ids:
        texto = gerador.gerar(respostas._entrada(banco, i)[0])
        assert validar_resposta(texto) == texto


def test_marcadores_sao_trocados_so_no_codigo():
    assert preencher_marcadores("Olá, {nome}!\n{restaurante}", "Ana") == "Olá, Ana!\nCantina Sabor da Vila"
    assert preencher_marcadores("Olá, {nome}!", "") == "Olá!"


# --- Gerador Claude: privacidade, validação e injeção --------------------------------------------------
def test_claude_devolve_a_resposta_validada_com_pedido_estruturado():
    gerador, cliente = claude_que_responde(VALIDA)
    assert gerador.gerar(entrada()) == VALIDA
    chamada = cliente.chamadas[0]
    assert chamada["model"] == "claude-sonnet-5-5"
    assert chamada["output_config"]["format"]["schema"] == respostas.SCHEMA_RESPOSTA
    assert "temperature" not in chamada and "tool_choice" not in chamada


@pytest.mark.parametrize("promessa", [VALIDA + " Daremos R$ 100 de volta.", "curto", VALIDA + " http://x.com"])
def test_claude_com_resposta_invalida_devolve_none(promessa):
    gerador, _ = claude_que_responde(promessa)
    assert gerador.gerar(entrada()) is None


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_claude_com_recusa_ou_corte_devolve_none(stop):
    gerador, _ = claude_que_responde(VALIDA, stop_reason=stop)
    assert gerador.gerar(entrada()) is None


def test_nome_telefone_e_endereco_nao_chegam_ao_claude(banco):
    nome, tel, ende = banco.execute(
        "SELECT c.nome, c.telefone, c.endereco FROM clientes c JOIN avaliacoes a USING (cliente_id) WHERE a.avaliacao_id = 1").fetchone()
    banco.execute("UPDATE avaliacoes SET texto = ? WHERE avaliacao_id = 1",
                  (f"Sou {nome}, liguem {tel}, entreguem na {ende}. Pedido atrasou e veio frio.",))
    banco.execute("UPDATE classificacoes SET sentimento = 'negativo', injecao = 0 WHERE avaliacao_id = 1")
    banco.commit()
    gerador, cliente = claude_que_responde(VALIDA)
    gerar_rascunhos(banco, [1], gerador)
    enviado = json.dumps(cliente.chamadas[0]["messages"], ensure_ascii=False)
    assert all(sensivel not in enviado for sensivel in (nome, tel, ende))
    texto = banco.execute("SELECT texto_final FROM respostas WHERE avaliacao_id = 1").fetchone()[0]
    assert texto.startswith(f"Olá, {nome.split()[0]}!") and "{nome}" not in texto       # o nome entra só depois


def test_modelo_que_obedece_a_avaliacao_e_prometendo_reembolso_cai_para_as_regras(banco):
    gerador, _ = claude_que_responde("Olá, {nome}! Prometemos um reembolso de R$ 500 agora mesmo. Atenciosamente,\n{restaurante}")
    ids = ids_candidatos(banco)[:3]
    resumo = gerar_rascunhos(banco, ids, gerador)
    assert resumo.reserva_por_falha == 3 and resumo.pelas_regras == 3 and resumo.pelo_claude == 0
    textos = respostas.listar(banco)["texto_final"]
    assert not textos.str.contains("reembolso|R\\$", case=False, regex=True).any()


def test_avaliacao_com_injecao_nunca_vai_ao_claude(banco):
    ids = [r[0] for r in banco.execute("SELECT avaliacao_id FROM classificacoes WHERE injecao = 1")]
    assert len(ids) == 2
    gerador, cliente = claude_que_responde(VALIDA)
    resumo = gerar_rascunhos(banco, ids, gerador)
    assert cliente.chamadas == [] and resumo.reserva_por_injecao == 2 and resumo.pelas_regras == 2


def test_limite_diario_desvia_para_as_regras(banco):
    registrar(banco, 5)
    gerador, cliente = claude_que_responde(VALIDA)
    resumo = gerar_rascunhos(banco, ids_candidatos(banco)[:4], gerador, limite_diario=5)
    assert cliente.chamadas == [] and resumo.reserva_por_limite == 4 and resumo.pelas_regras == 4


def test_cada_chamada_ao_claude_conta_no_limite(banco):
    from copiloto.llm.limite import usadas_hoje

    gerador, _ = claude_que_responde(VALIDA)
    sem_injecao = [i for i in ids_candidatos(banco) if not banco.execute(
        "SELECT injecao FROM classificacoes WHERE avaliacao_id = ?", (i,)).fetchone()[0]][:3]
    gerar_rascunhos(banco, sem_injecao, gerador, limite_diario=10)
    assert usadas_hoje(banco) == 3


def test_chave_recusada_interrompe_em_vez_de_esconder_o_erro(banco):
    class Cliente:
        class messages:
            @staticmethod
            def create(**kw):
                import httpx
                req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
                raise anthropic.AuthenticationError("chave inválida", response=httpx.Response(401, request=req), body=None)

    with pytest.raises(anthropic.AuthenticationError):
        gerar_rascunhos(banco, ids_candidatos(banco)[:1], GeradorClaude("m", client=Cliente()))


# --- Fluxo de edição e aprovação ---------------------------------------------------------------------------
@pytest.fixture()
def com_rascunho(banco):
    ids = ids_candidatos(banco)[:3]
    gerar_rascunhos(banco, ids, GeradorRegras())
    return banco, ids


def status(con, i):
    return con.execute("SELECT status FROM respostas WHERE avaliacao_id = ?", (i,)).fetchone()[0]


def test_rascunho_nasce_igual_ao_sugerido_e_so_para_negativas(com_rascunho):
    con, ids = com_rascunho
    for r in con.execute("SELECT * FROM respostas"):
        assert r["status"] == "rascunho" and r["texto_final"] == r["texto_sugerido"] and r["aprovado_em"] is None
    sentimentos = {r[0] for r in con.execute("SELECT k.sentimento FROM respostas r JOIN classificacoes k USING (avaliacao_id)")}
    assert sentimentos == {"negativo"}


def test_gerar_de_novo_nao_sobrescreve_o_que_o_dono_editou(com_rascunho):
    con, ids = com_rascunho
    respostas.editar(con, ids[0], "Meu texto, escrito por mim.")
    assert gerar_rascunhos(con, ids, GeradorRegras()).criados == 0
    assert con.execute("SELECT texto_final FROM respostas WHERE avaliacao_id = ?", (ids[0],)).fetchone()[0] == "Meu texto, escrito por mim."
    assert ids_candidatos(con) and not set(ids) & set(ids_candidatos(con))


def test_candidatas_pulam_as_excluidas(banco):
    todas = ids_candidatos(banco)
    assert ids_candidatos(banco, excluir=todas[:5]) == todas[5:]


def test_aprovar_marca_a_data_e_guarda_o_texto_editado(com_rascunho):
    con, ids = com_rascunho
    respostas.editar(con, ids[0], "Texto final aprovado pelo dono.")
    respostas.aprovar(con, ids[0])
    linha = con.execute("SELECT status, texto_final, aprovado_em FROM respostas WHERE avaliacao_id = ?", (ids[0],)).fetchone()
    assert linha["status"] == "aprovada" and linha["texto_final"] == "Texto final aprovado pelo dono." and linha["aprovado_em"]
    assert status(con, ids[1]) == "rascunho"


def test_transicoes_invalidas_sao_recusadas(com_rascunho):
    con, ids = com_rascunho
    respostas.aprovar(con, ids[0])
    with pytest.raises(ValueError):
        respostas.editar(con, ids[0], "editar depois de aprovada")
    with pytest.raises(ValueError):
        respostas.aprovar(con, ids[0])
    with pytest.raises(ValueError):
        respostas.descartar(con, ids[0])
    with pytest.raises(KeyError):
        respostas.aprovar(con, 999999)
    for texto in ("", "   ", "a" * 1001):
        with pytest.raises(ValueError):
            respostas.editar(con, ids[1], texto)


def test_nao_aprova_texto_com_marcador_pendente(com_rascunho):
    con, ids = com_rascunho
    respostas.editar(con, ids[0], "Olá, {nome}! Obrigado pelo retorno.")
    with pytest.raises(ValueError, match="marcadores"):
        respostas.aprovar(con, ids[0])
    assert status(con, ids[0]) == "rascunho"


def test_descartar_e_reabrir(com_rascunho):
    con, ids = com_rascunho
    respostas.descartar(con, ids[0])
    assert status(con, ids[0]) == "descartada"
    respostas.reabrir(con, ids[0])
    respostas.aprovar(con, ids[0])
    respostas.reabrir(con, ids[0])
    linha = con.execute("SELECT status, aprovado_em FROM respostas WHERE avaliacao_id = ?", (ids[0],)).fetchone()
    assert linha["status"] == "rascunho" and linha["aprovado_em"] is None


def test_listar_filtra_por_status(com_rascunho):
    con, ids = com_rascunho
    respostas.aprovar(con, ids[0])
    assert list(respostas.listar(con, "aprovada")["avaliacao_id"]) == [ids[0]]
    assert len(respostas.listar(con, "rascunho")) == 2 and len(respostas.listar(con)) == 3


def test_aprovar_nao_chama_nenhum_gerador_nem_rede(com_rascunho):
    """Aprovar só muda o banco: o módulo não tem como publicar nada em uma plataforma."""
    con, ids = com_rascunho
    chamadas = []

    class Espiao(GeradorRegras):
        def gerar(self, e):
            chamadas.append(e)
            return super().gerar(e)

    respostas.aprovar(con, ids[0])
    respostas.reabrir(con, ids[0])
    assert chamadas == []
    fonte = respostas.__loader__.get_source(respostas.__name__)
    for proibido in ("requests", "smtplib", "urllib", "httpx", "http.client", "socket"):
        assert f"import {proibido}" not in fonte
