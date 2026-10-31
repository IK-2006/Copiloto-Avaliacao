"""Proteções que ficam entre os dados do restaurante e qualquer modelo de IA.

1. Privacidade: dados pessoais são mascarados e só identificadores anônimos saem do sistema.
2. Injeção de prompt: o texto de uma avaliação é sempre tratado como dado. Aqui o texto é
   limpo e as tentativas de manipulação são detectadas (para sinalizar), mas a defesa
   principal é estrutural: a saída do modelo só pode conter valores de listas fechadas
   (ver `base.validar_classificacao`).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from copiloto.dominio import normalizar

TAMANHO_MAX_TEXTO = 1200

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_CEP = re.compile(r"(?<!\d)\d{5}-\d{3}(?!\d)")
_TELEFONE = re.compile(r"(?<!\d)(?:\+?55[\s-]?)?(?:\(?\d{2}\)?[\s-]?)?9?\d{4}[\s-]?\d{4}(?!\d)")
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Procurados no texto normalizado (minúsculas, sem acento).
_PADROES_INJECAO = [
    re.compile(p)
    for p in (
        r"\b(ignor\w*|desconsider\w*|esquec\w*|descart\w*)\b.{0,25}\b(instruc\w*|regras|ordens|orientac\w*|prompt)",
        r"\b(ignore|disregard|forget)\b.{0,25}\b(previous|prior|above|all|instructions)",
        r"\b(voce|vc)\s+(agora\s+)?(e|sera|deve ser)\s+um",
        r"\b(prompt|instrucoes)\s+d[eo]\s+sistema",
        r"\bsystem\s+prompt\b",
        r"\b(novas?|nova)\s+instruc",
        r"\b(finja|simule|aja como|act as)\b",
        r"\brevele\b.{0,30}\b(prompt|instruc|chave|senha)",
    )
]


def referencia_avaliacao(avaliacao_id: int) -> str:
    return f"av_{avaliacao_id}"


def referencia_cliente(cliente_id: int, salt: str) -> str:
    return "cli_" + hashlib.sha256(f"{salt}:{cliente_id}".encode()).hexdigest()[:10]


def mascarar_pii(texto: str, nomes: Iterable[str] = (), frases: Iterable[str] = ()) -> str:
    """Troca e-mail, CPF, CEP, telefone e dados conhecidos do cliente por marcadores.

    `nomes`: nome do cliente (cada parte vira [NOME]). `frases`: textos exatos a esconder,
    como o endereço cadastrado.
    """
    for padrao, marca in ((_EMAIL, "[EMAIL]"), (_CPF, "[CPF]"), (_CEP, "[CEP]"), (_TELEFONE, "[TELEFONE]")):
        texto = padrao.sub(marca, texto)
    for frase in frases:
        if frase:
            texto = re.sub(re.escape(frase), "[ENDEREÇO]", texto, flags=re.IGNORECASE)
    for nome in nomes:
        for parte in re.split(r"\s+", nome.strip()):
            if len(parte) >= 3:
                texto = re.sub(rf"\b{re.escape(parte)}\b", "[NOME]", texto, flags=re.IGNORECASE)
    return texto


def neutralizar_delimitadores(texto: str) -> str:
    """Impede que o texto feche ou abra as tags que delimitam o conteúdo no prompt."""
    return texto.replace("<", "‹").replace(">", "›")


def limpar_texto(texto: str) -> str:
    texto = _CONTROLE.sub(" ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return neutralizar_delimitadores(texto)[:TAMANHO_MAX_TEXTO]


def detectar_injecao(texto: str) -> bool:
    """True se o texto parece tentar dar ordens ao modelo. Só sinaliza; não altera a análise."""
    normal = normalizar(texto)
    return any(p.search(normal) for p in _PADROES_INJECAO)


def hash_entrada(partes: dict) -> str:
    """Impressão digital estável do que foi enviado à IA, usada como chave de cache."""
    bruto = json.dumps(partes, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode()).hexdigest()[:16]
