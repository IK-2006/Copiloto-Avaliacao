"""Os scripts de apoio rodam de ponta a ponta (com um Claude simulado)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests.fakes import ClienteFalso, avaliacoes_da_chamada, resposta, texto_final, uso_de_ferramenta

RAIZ = Path(__file__).resolve().parent.parent


def carregar_script(nome: str):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def claude_simulado(kwargs: dict):
    if "tools" in kwargs:                                            # perguntas
        ultima = kwargs["messages"][-1]
        if isinstance(ultima["content"], list):
            return texto_final("Veja os números consultados acima.")
        return uso_de_ferramenta("nota_media", {})
    if "classificacoes" in json.dumps(kwargs["output_config"]):       # classificação
        itens = avaliacoes_da_chamada(kwargs)
        return resposta(json.dumps({"classificacoes": [
            {"ref": i["ref"], "sentimento": "negativo", "temas": ["atraso"], "pratos": []} for i in itens]}))
    return resposta(json.dumps({"resposta": "Olá, {nome}! Sentimos muito pela demora na entrega. Já repassamos à equipe.\nAtenciosamente,\n{restaurante}"}))


def test_check_claude_sem_chave_avisa_e_sai_com_erro(dados, monkeypatch, capsys):
    monkeypatch.setenv("COPILOTO_DB", str(dados[0]))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert carregar_script("check_claude").main() == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_check_claude_roda_os_tres_usos_sem_gravar_no_banco(dados, monkeypatch, capsys, con_classificada):
    monkeypatch.setenv("COPILOTO_DB", str(dados[0]))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-teste")
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: ClienteFalso(claude_simulado))
    antes = con_classificada.execute("SELECT COUNT(*) FROM respostas").fetchone()[0], con_classificada.execute("SELECT COUNT(*) FROM uso_llm").fetchone()[0]
    assert carregar_script("check_claude").main() == 0
    saida = capsys.readouterr().out
    assert "== 1. Classificação" in saida and "== 2. Rascunho de resposta" in saida and "== 3. Perguntas" in saida
    assert "Veja os números consultados" in saida and "Números não verificados: nenhum" in saida
    depois = con_classificada.execute("SELECT COUNT(*) FROM respostas").fetchone()[0], con_classificada.execute("SELECT COUNT(*) FROM uso_llm").fetchone()[0]
    assert antes == depois


def test_smtp_de_teste_grava_o_email_recebido(tmp_path):
    """Sobe o servidor SMTP de teste, envia um e-mail com smtplib e confere o arquivo gravado."""
    import smtplib
    import subprocess
    import time
    from email.message import EmailMessage

    import socket

    with socket.socket() as sonda:                                      # uma porta livre, para não colidir com outro SMTP
        sonda.bind(("127.0.0.1", 0))
        porta = sonda.getsockname()[1]
    caixa = tmp_path / "caixa"
    processo = subprocess.Popen([sys.executable, str(RAIZ / "scripts" / "smtp_de_teste.py"), str(caixa), str(porta)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            try:
                with smtplib.SMTP("127.0.0.1", porta, timeout=2) as smtp:
                    msg = EmailMessage()
                    msg["From"], msg["To"], msg["Subject"] = "a@teste.local", "b@teste.local", "Resumo de teste"
                    msg.set_content("Olá, tudo bem?\n.\nlinha com ponto sozinho acima")
                    smtp.send_message(msg)
                break
            except OSError:
                time.sleep(0.2)
        else:
            erro = processo.stderr.read().decode("utf-8", "replace") if processo.poll() is not None else f"sem resposta na porta {porta}"
            pytest.fail(f"o servidor SMTP de teste não subiu: {erro}")
        time.sleep(0.3)
        [arquivo] = list(caixa.glob("*.eml"))
        import email
        import email.policy

        mensagem = email.message_from_bytes(arquivo.read_bytes(), policy=email.policy.default)
        assert mensagem["Subject"] == "Resumo de teste" and mensagem["To"] == "b@teste.local"
        assert "linha com ponto sozinho acima" in mensagem.get_content()          # o ponto sozinho foi preservado
    finally:
        processo.terminate()
        processo.wait(timeout=5)
