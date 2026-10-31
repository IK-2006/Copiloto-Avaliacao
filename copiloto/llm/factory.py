"""Escolha do provedor de IA conforme o ambiente."""
from __future__ import annotations

from copiloto import config
from copiloto.llm.base import ProvedorIA
from copiloto.llm.claude import ProvedorClaude
from copiloto.llm.rules import ProvedorRegras


def obter_provedor(nome: str = "auto", cfg: config.Config | None = None) -> ProvedorIA:
    """'auto' usa o Claude se houver ANTHROPIC_API_KEY e as Regras caso contrário."""
    cfg = cfg or config.carregar()
    if nome == "auto":
        nome = "claude" if cfg.anthropic_api_key else "regras"
    if nome == "regras":
        return ProvedorRegras()
    if nome == "claude":
        if not cfg.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY não está definida; use o provedor 'regras' ou configure a chave.")
        return ProvedorClaude(modelo=cfg.modelo_classificacao, api_key=cfg.anthropic_api_key)
    raise ValueError(f"provedor desconhecido: {nome!r}")
