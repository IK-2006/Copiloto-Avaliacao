"""API mínima para o n8n: GET /weekly-summary devolve o resumo da semana (assunto, texto e HTML).

Executar: uvicorn api.main:app --host 0.0.0.0 --port 8000

Segurança:
- se COPILOTO_API_TOKEN estiver definido, toda chamada a /weekly-summary exige o cabeçalho X-API-Token igual a ele
  (comparação em tempo constante). Sem a variável, a API fica aberta, o que só serve para uso local;
- a resposta contém apenas números agregados e texto escrito pelo código: nenhum dado pessoal de cliente nem texto
  de avaliação.
"""
from __future__ import annotations

import os
import secrets
from datetime import date
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from copiloto import config, db
from copiloto.analytics.base import carregar_avaliacoes, carregar_pedidos
from copiloto.analytics.suspeitas import com_suspeitas
from copiloto.resumo_semanal import gerar_resumo

app = FastAPI(title="Copiloto de Avaliações: resumo semanal", version="1.0.0")


def exigir_token(x_api_token: Annotated[str | None, Header()] = None) -> None:
    esperado = os.environ.get("COPILOTO_API_TOKEN")
    if esperado and not (x_api_token and secrets.compare_digest(x_api_token, esperado)):
        raise HTTPException(status_code=401, detail="token ausente ou inválido")


@lru_cache(maxsize=2)
def _dados(caminho: str, versao: str):
    con = db.conectar(caminho)
    try:
        categorias = {r["nome"]: r["categoria"] for r in con.execute("SELECT nome, categoria FROM cardapio")}
        return com_suspeitas(carregar_avaliacoes(con)), carregar_pedidos(con), categorias
    finally:
        con.close()


def _carregar():
    caminho = config.carregar().db_path
    con = db.conectar(caminho)
    try:
        versao = db.versao_dos_dados(con)
    finally:
        con.close()
    return _dados(str(caminho), versao)


@app.get("/health")
def saude() -> dict:
    return {"status": "ok"}


@app.get("/weekly-summary", dependencies=[Depends(exigir_token)])
def resumo_semanal(
    ate: Annotated[date | None, Query(description="Último dia da semana (AAAA-MM-DD). Padrão: o último dia com avaliações.")] = None,
    modo: Annotated[Literal["todas", "medias_e_altas", "so_altas"], Query(description="Filtro de avaliações suspeitas.")] = "medias_e_altas",
) -> dict:
    todas, pedidos, categorias = _carregar()
    if todas.empty:
        raise HTTPException(status_code=503, detail="nenhuma avaliação classificada; rode python -m copiloto.classify")
    resumo = gerar_resumo(todas, pedidos, categorias, ate=ate, modo=modo, url_dashboard=os.environ.get("COPILOTO_DASHBOARD_URL"))
    return resumo.para_json()
