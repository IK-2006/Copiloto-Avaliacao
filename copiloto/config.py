"""Configuração lida de variáveis de ambiente (nunca de arquivos versionados)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


@dataclass(frozen=True)
class Config:
    db_path: Path
    anthropic_api_key: str | None
    modelo_classificacao: str
    modelo_geracao: str
    limite_diario_llm: int
    salt_anonimizacao: str


def carregar() -> Config:
    """Lê o ambiente a cada chamada, para que testes possam alterá-lo."""
    db_env = os.environ.get("COPILOTO_DB", "data/restaurante.db")
    db_path = Path(db_env)
    if not db_path.is_absolute():
        db_path = RAIZ / db_path
    return Config(
        db_path=db_path,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        modelo_classificacao=os.environ.get("COPILOTO_MODELO_CLASSIFICACAO", "claude-haiku-5-5"),
        modelo_geracao=os.environ.get("COPILOTO_MODELO_GERACAO", "claude-sonnet-5-5"),
        limite_diario_llm=int(os.environ.get("COPILOTO_LIMITE_DIARIO_LLM", "200")),
        salt_anonimizacao=os.environ.get("COPILOTO_SALT", "copiloto-demo"),
    )
