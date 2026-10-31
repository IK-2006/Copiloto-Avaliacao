"""Privacidade e prompt injection ao longo do pipeline completo (banco -> IA -> cache)."""
import json
import re
import shutil

import pytest

from copiloto import db
from copiloto.classify import carregar_cardapio, classificar_pendentes
from copiloto.datagen.frases import INJECOES
from copiloto.llm.base import EntradaAvaliacao
from copiloto.llm.claude import ProvedorClaude
from copiloto.llm.rules import ProvedorRegras
from tests.fakes import ClienteFalso, avaliacoes_da_chamada, resposta, responder_como_regras


@pytest.fixture()
def banco(dados, tmp_path):
    copia = tmp_path / "copia.db"
    shutil.copy(dados[0], copia)
    con = db.conectar(copia)
    con.execute("DELETE FROM classificacoes")
    con.commit()
    yield con
    con.close()


def test_nenhum_dado_pessoal_chega_ao_modelo(banco):
    cliente = ClienteFalso(responder_como_regras(carregar_cardapio(banco)))
    resumo = classificar_pendentes(banco, ProvedorClaude("claude-haiku-5-5", client=cliente))
    assert resumo.classificadas == resumo.total > 0

    enviado = cliente.texto_enviado()
    for c in banco.execute("SELECT cliente_ref, nome, telefone, endereco FROM clientes"):
        assert c["telefone"] not in enviado
        assert c["endereco"] not in enviado
        assert c["nome"] not in enviado
        assert c["cliente_ref"] not in enviado
    assert not re.search(r"\(\d{2}\)\s?9\d{4}-\d{4}", enviado)


def test_pii_escrita_pelo_cliente_no_texto_e_mascarada(banco):
    nome, tel, ende = banco.execute(
        "SELECT c.nome, c.telefone, c.endereco FROM clientes c JOIN avaliacoes a USING (cliente_id) WHERE a.avaliacao_id = 1"
    ).fetchone()
    banco.execute(
        "UPDATE avaliacoes SET texto = ? WHERE avaliacao_id = 1",
        (f"Sou {nome}, liguem {tel}, entreguem na {ende}. Mande e-mail para eu@teste.com. Pedido atrasou.",),
    )
    banco.commit()

    cliente = ClienteFalso(responder_como_regras(carregar_cardapio(banco)))
    classificar_pendentes(banco, ProvedorClaude("claude-haiku-5-5", client=cliente))
    texto = next(a["texto"] for c in cliente.chamadas for a in avaliacoes_da_chamada(c) if a["ref"] == "av_1")
    for sensivel in (nome, tel, ende, "eu@teste.com"):
        assert sensivel not in texto
    assert "atrasou" in texto


def test_modelo_que_obedece_a_injecao_nao_contamina_o_banco(banco):
    """Um 'modelo' manipulado devolve lixo para as avaliações com injeção: tudo é rejeitado."""
    base = responder_como_regras(carregar_cardapio(banco))

    def manipulado(kwargs):
        conteudo = base(kwargs)
        dados = json.loads(conteudo.content[0].text)
        por_ref = {a["ref"]: a for a in avaliacoes_da_chamada(kwargs)}
        for item in dados["classificacoes"]:
            if "instru" in por_ref[item["ref"]]["texto"].lower():
                item["sentimento"] = "positivo. NOTA MÉDIA = 5"
        return resposta(json.dumps(dados))

    resumo = classificar_pendentes(banco, ProvedorClaude("claude-haiku-5-5", client=ClienteFalso(manipulado)))
    assert resumo.falhas == 2 and resumo.injecoes_detectadas == 2
    guardados = {r[0] for r in banco.execute("SELECT avaliacao_id FROM classificacoes")}
    assert len(guardados) == resumo.total - 2
    assert all(
        r[0] in ("positivo", "neutro", "negativo") for r in banco.execute("SELECT sentimento FROM classificacoes")
    )


def test_injecao_nao_muda_a_classificacao_das_regras(con_classificada):
    cardapio = carregar_cardapio(con_classificada)
    regras = ProvedorRegras()
    achadas = 0
    for r in con_classificada.execute("SELECT texto, nota FROM avaliacoes"):
        for injecao in INJECOES:
            if r["texto"].endswith(injecao):
                limpo = r["texto"].removesuffix(injecao).strip()
                com = regras.classificar([EntradaAvaliacao("a", r["nota"], r["texto"], ())], cardapio)
                sem = regras.classificar([EntradaAvaliacao("a", r["nota"], limpo, ())], cardapio)
                assert com == sem
                achadas += 1
    assert achadas == 2


def test_texto_de_injecao_e_classificado_pelo_conteudo_real(con_classificada):
    linhas = con_classificada.execute(
        "SELECT a.texto, k.sentimento, k.temas, k.injecao FROM avaliacoes a JOIN classificacoes k USING (avaliacao_id) WHERE k.injecao = 1"
    ).fetchall()
    assert len(linhas) == 2
    for r in linhas:
        assert r["sentimento"] == "negativo"          # ordem era "classifique como positiva"
        assert json.loads(r["temas"])                  # os problemas reais foram vistos


def test_pipeline_usa_cache_e_so_reclassifica_o_que_mudou(banco):
    regras = ProvedorRegras()
    primeira = classificar_pendentes(banco, regras)
    segunda = classificar_pendentes(banco, regras)
    assert primeira.classificadas == primeira.total and segunda.classificadas == 0
    assert segunda.em_cache == segunda.total
    banco.execute("UPDATE avaliacoes SET texto = 'agora chegou fria' WHERE avaliacao_id = 3")
    banco.commit()
    terceira = classificar_pendentes(banco, regras)
    assert terceira.classificadas == 1


def test_prato_citado_fora_do_pedido_e_descartado(banco):
    pedido, = banco.execute("SELECT pedido_id FROM avaliacoes WHERE pedido_id IS NOT NULL LIMIT 1").fetchone()
    itens = {r[0] for r in banco.execute(
        "SELECT c.nome FROM pedido_itens pi JOIN cardapio c USING (item_id) WHERE pedido_id = ?", (pedido,))}
    ausente = next(n for (n,) in banco.execute("SELECT nome FROM cardapio") if n not in itens)
    banco.execute("UPDATE avaliacoes SET texto = ? WHERE pedido_id = ?", (f"Adorei {ausente.lower()}", pedido))
    banco.commit()
    cardapio = carregar_cardapio(banco)

    def modelo(kwargs):
        itens_ = avaliacoes_da_chamada(kwargs)
        return resposta(json.dumps({"classificacoes": [
            {"ref": a["ref"], "sentimento": "positivo", "temas": [],
             "pratos": [{"prato": ausente, "problemas": []}]} for a in itens_]}))

    classificar_pendentes(banco, ProvedorClaude("claude-haiku-5-5", client=ClienteFalso(modelo)))
    pratos = json.loads(banco.execute(
        "SELECT pratos FROM classificacoes k JOIN avaliacoes a USING (avaliacao_id) WHERE a.pedido_id = ?", (pedido,)
    ).fetchone()[0])
    assert all(p["prato"] in itens for p in pratos)
    assert cardapio
