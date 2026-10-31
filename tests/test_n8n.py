"""Arquivos de implantação: o workflow do n8n, o docker-compose e o que não pode vazar para o repositório."""
import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def fluxo() -> dict:
    return json.loads((RAIZ / "n8n" / "workflow.json").read_text(encoding="utf-8"))


def nos(fluxo: dict) -> dict:
    return {n["type"].removeprefix("n8n-nodes-base."): n for n in fluxo["nodes"]}


def test_tres_nos_na_ordem_agenda_api_email(fluxo):
    n = nos(fluxo)
    assert set(n) == {"scheduleTrigger", "httpRequest", "emailSend"}
    ligacoes = fluxo["connections"]
    assert ligacoes[n["scheduleTrigger"]["name"]]["main"][0][0]["node"] == n["httpRequest"]["name"]
    assert ligacoes[n["httpRequest"]["name"]]["main"][0][0]["node"] == n["emailSend"]["name"]


def test_roda_toda_segunda_as_8h_no_horario_de_brasilia(fluxo):
    regra = nos(fluxo)["scheduleTrigger"]["parameters"]["rule"]["interval"][0]
    assert regra["field"] == "weeks" and regra["triggerAtDay"] == [1] and regra["triggerAtHour"] == 8
    assert fluxo["settings"]["timezone"] == "America/Sao_Paulo"
    assert fluxo["active"] is False                                     # o dono ativa depois de configurar o e-mail


def test_chama_a_api_com_token_de_credencial(fluxo):
    http = nos(fluxo)["httpRequest"]
    assert http["parameters"]["url"].endswith("'/weekly-summary' }}")
    assert http["parameters"]["authentication"] == "genericCredentialType"
    assert http["parameters"]["genericAuthType"] == "httpHeaderAuth"
    assert http["retryOnFail"] is True and http["maxTries"] >= 2         # a API pode estar subindo junto


def test_email_usa_os_campos_do_resumo(fluxo):
    p = nos(fluxo)["emailSend"]["parameters"]
    assert p["subject"] == "={{ $json.assunto }}" and p["text"] == "={{ $json.texto }}" and p["html"] == "={{ $json.html }}"
    assert p["emailFormat"] == "both" and "RESUMO_EMAIL_PARA" in p["toEmail"]


def test_workflow_nao_guarda_segredos_nem_enderecos_pessoais(fluxo):
    bruto = json.dumps(fluxo)
    for no in fluxo["nodes"]:
        for credencial in no.get("credentials", {}).values():
            assert set(credencial) == {"id", "name"}                     # só referência, nunca o valor
    assert not re.search(r"password|senha|secret|bearer|api[_-]?key", bruto, re.IGNORECASE)
    assert not re.search(r"[\w.+-]+@(?!localhost)[\w-]+\.\w+", bruto)     # nenhum e-mail real
    ids = [n["id"] for n in fluxo["nodes"]]
    assert len(set(ids)) == len(ids)


def test_compose_com_imagem_fixa_portas_locais_e_variaveis_obrigatorias():
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r"image: docker\.n8n\.io/n8nio/n8n:\d+\.\d+\.\d+", compose) and ":latest" not in compose
    assert compose.count('"127.0.0.1:') == 2                              # nada exposto além do próprio computador
    for variavel in ("COPILOTO_API_TOKEN", "N8N_ENCRYPTION_KEY", "RESUMO_EMAIL_PARA"):
        assert f"${{{variavel}:?" in compose                              # sem a variável, o compose se recusa a subir
    assert "./data:/app/data:ro" in compose


def test_dockerfile_da_api_nao_leva_segredos_nem_o_dashboard():
    docker = (RAIZ / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements-api.txt" in docker and ".env" not in docker.replace(".env.", "")
    ignorado = (RAIZ / ".dockerignore").read_text(encoding="utf-8").split()
    assert {".env", ".git", ".venv"} <= set(ignorado)
    assert "streamlit" not in (RAIZ / "requirements-api.txt").read_text(encoding="utf-8")


def test_env_example_lista_as_variaveis_e_env_fica_fora_do_git():
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    for variavel in ("ANTHROPIC_API_KEY", "COPILOTO_API_TOKEN", "N8N_ENCRYPTION_KEY", "RESUMO_EMAIL_PARA"):
        assert re.search(rf"^{variavel}=$", exemplo, re.MULTILINE)       # presentes e vazias
    assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_api_le_um_banco_somente_leitura_mesmo_sem_as_tabelas_novas(dados, tmp_path):
    """No compose o banco é montado como somente leitura: abrir não pode tentar criar tabelas."""
    import os
    import shutil
    import sqlite3
    import stat

    from copiloto import db

    copia = tmp_path / "antigo.db"
    shutil.copy(dados[0], copia)
    bruto = sqlite3.connect(copia)
    bruto.executescript("DROP TABLE respostas; DROP TABLE uso_llm;")      # banco anterior às tabelas novas
    bruto.commit()
    bruto.close()
    os.chmod(copia, stat.S_IREAD)
    try:
        con = db.conectar(copia)
        assert con.execute("SELECT COUNT(*) FROM avaliacoes").fetchone()[0] > 0
        con.close()
    finally:
        os.chmod(copia, stat.S_IREAD | stat.S_IWRITE)
