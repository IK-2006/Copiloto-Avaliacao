"""Contrato entre o app e qualquer provedor de IA (Claude ou Regras)."""
from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from copiloto.dominio import SENTIMENTOS, TEMAS, normalizar


class SaidaInvalida(ValueError):
    """A resposta do provedor não segue o formato fechado esperado."""


@dataclass(frozen=True)
class ItemCardapio:
    nome: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntradaAvaliacao:
    """Tudo o que a IA enxerga de uma avaliação. Não há campo para dados pessoais."""

    ref: str                       # identificador anônimo, ex.: "av_123"
    nota: int
    texto: str                     # já com dados pessoais mascarados
    itens_pedido: tuple[str, ...]  # nomes do cardápio; vazio se não há pedido


@dataclass(frozen=True)
class PratoClassificado:
    prato: str
    problemas: tuple[str, ...]


@dataclass(frozen=True)
class Classificacao:
    sentimento: str
    temas: tuple[str, ...]
    pratos: tuple[PratoClassificado, ...]


class ProvedorIA(Protocol):
    nome: str
    modelo: str
    versao: str

    def classificar(
        self, entradas: Sequence[EntradaAvaliacao], cardapio: Sequence[ItemCardapio]
    ) -> list[Classificacao | None]:
        """Uma classificação por entrada, na mesma ordem. None = falha naquela avaliação."""
        ...


def validar_classificacao(bruto: Any, nomes_cardapio: Collection[str]) -> Classificacao:
    """Aceita só valores das listas fechadas. Texto livre vindo do modelo nunca passa daqui.

    Prato desconhecido é descartado (o modelo pode errar o nome); sentimento ou tema
    fora do vocabulário invalida a resposta inteira.
    """
    if not isinstance(bruto, dict):
        raise SaidaInvalida("resposta não é um objeto")
    sentimento = bruto.get("sentimento")
    if sentimento not in SENTIMENTOS:
        raise SaidaInvalida(f"sentimento inválido: {sentimento!r}")

    temas = _validar_temas(bruto.get("temas", []))
    por_nome = {normalizar(n): n for n in nomes_cardapio}
    pratos: dict[str, set[str]] = {}
    brutos = bruto.get("pratos", [])
    if not isinstance(brutos, list):
        raise SaidaInvalida("'pratos' não é uma lista")
    for item in brutos:
        if not isinstance(item, dict):
            raise SaidaInvalida("item de 'pratos' inválido")
        nome = por_nome.get(normalizar(str(item.get("prato", ""))))
        problemas = _validar_temas(item.get("problemas", []))
        if nome is not None:
            pratos.setdefault(nome, set()).update(problemas)

    todos = set(temas).union(*pratos.values()) if pratos else set(temas)
    return Classificacao(
        sentimento=sentimento,
        temas=tuple(t for t in TEMAS if t in todos),
        pratos=tuple(
            PratoClassificado(n, tuple(t for t in TEMAS if t in pratos[n])) for n in sorted(pratos)
        ),
    )


def _validar_temas(valor: Any) -> tuple[str, ...]:
    if not isinstance(valor, list):
        raise SaidaInvalida("lista de temas inválida")
    invalidos = [t for t in valor if t not in TEMAS]
    if invalidos:
        raise SaidaInvalida(f"temas fora do vocabulário: {invalidos!r}")
    return tuple(t for t in TEMAS if t in valor)
