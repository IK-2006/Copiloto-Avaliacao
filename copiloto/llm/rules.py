"""Provedor "Regras": classificador offline por léxico, sem rede e sem chave de API.

Serve de reserva quando não há chave do Claude e como base dos testes. É mais simples que
um modelo de linguagem: não entende ironia nem frases sem as palavras do léxico. Sua
acurácia, medida contra o gabarito dos dados fictícios, está no README.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from copiloto.dominio import TEMAS, normalizar
from copiloto.llm.base import Classificacao, EntradaAvaliacao, ItemCardapio, PratoClassificado

_SEPARADOR = re.compile(r"[.!?;\n]+|\bmas\b|\bporem\b|\bembora\b")
_NEGADORES = {"nao", "nem", "nunca", "sem", "nada", "nenhum", "nenhuma", "jamais"}


def _p(*padroes: str) -> list[re.Pattern]:
    return [re.compile(p) for p in padroes]


# Gatilhos de problema, em texto normalizado. Valem a menos que estejam negados ("nao demorou").
_PROBLEMAS: dict[str, list[re.Pattern]] = {
    "atraso": _p(
        r"\b(demor\w*|atras\w*)\b",
        r"\bpassou (muito )?(do|da) (prazo|hora|horario)\b",
        r"\bquase desisti\b",
        r"\besper(ei|ar|ando)\b",
        r"\b(muito|bastante) tempo\b",
    ),
    "temperatura": _p(
        r"\b(frio|fria|frios|frias|gelad[oa]s?|morn[oa]s?|esfri\w*|derret\w*|requent\w*|esquent\w*|microondas)\b",
        r"\bsem (nenhum )?calor\b",
    ),
    "textura": _p(
        r"\b(murch\w*|moles?|molenga\w*|empap\w*|borrachud\w*|ressec\w*|encharcad\w*|duro|dura|duros|duras|papelao)\b",
    ),
    "embalagem": _p(
        r"\b(vazou|vazando|amassad\w*|derramou|melad\w*|caixa aberta|sem lacre)\b",
        r"\bembalagem (horrivel|ruim|pessima|fraca|rasgada)\b",
    ),
    "sabor": _p(
        r"\bsem (sabor|gosto|tempero)\b",
        r"\b(insos\w*|azedo|queimad\w*)\b",
        r"\bgosto ruim\b",
        r"\b(muito|demais) salgad\w*|\bsalgad\w* demais\b",
        r"\bsabor (muito )?fraco\b",
        r"\bnao tinha tempero\b",
    ),
    "quantidade": _p(
        r"\bveio (muito |bem )?(pouc\w*|pequen\w*)\b",
        r"\bquantidade (ridicula|pouca|pequena|minima)\b",
        r"\bporcao (muito )?pequen\w*",
        r"\bpequen[oa]s? demais\b",
    ),
    "atendimento": _p(
        r"\batendimento (pessimo|ruim|horrivel|lento|fraco|terrivel)\b",
        r"\b(grosseir\w*|mal educad\w*|mal-educad\w*|rude|mal atendid\w*)\b",
        r"\bignor(ou|aram|ando)\b",
        r"\bninguem (resolveu|respondeu|atendeu)\b",
        r"\bsem resposta\b",
    ),
    "pedido_errado": _p(
        r"\b(pedido errado|pedido trocado|trocaram|trocou|errad[oa]s?|faltou|faltando|faltaram)\b",
        r"\bveio outra coisa\b",
        r"\bnao veio\b",
        r"\besquec\w+ (metade|item|itens|o pedido|do meu|meu|minha|a bebida)\b",
    ),
}

# Palavras positivas que só viram problema quando negadas ("nao chegou quente", "nada crocante").
_POSITIVAS_NEGAVEIS: dict[str, list[re.Pattern]] = {
    "temperatura": _p(r"\bquent\w*"),
    "textura": _p(r"\bcrocan\w*"),
}

_POSITIVO = re.compile(
    r"\b(adorei|amei|gostei|delicia\w*|gostos[oa]|saboros[oa]|otim[oa]|excelente|perfeit[oa]|recomendo|"
    r"rapid[oa]|quentinh[oa]|crocante|maravilh\w*|nota 10|certinho|bom|boa|antes do prazo)\b"
)
_NEGATIVO = re.compile(
    r"\b(pessim[oa]|horrivel|horriveis|terrivel|decepcion\w*|ruim|lixo|descaso|absurd\w*|inaceitavel|"
    r"vergonha|estragad\w*|nojent\w*|golpe|fraud\w*|pior|nunca mais|nao recomendo)\b"
)


def _negado(sentenca: str, inicio: int) -> bool:
    anteriores = re.findall(r"\w+", sentenca[:inicio])[-3:]
    return any(t in _NEGADORES for t in anteriores)


def _temas_da_sentenca(sentenca: str) -> set[str]:
    achados: set[str] = set()
    for tema, padroes in _PROBLEMAS.items():
        for padrao in padroes:
            for m in padrao.finditer(sentenca):
                if not _negado(sentenca, m.start()):
                    achados.add(tema)
    for tema, padroes in _POSITIVAS_NEGAVEIS.items():
        for padrao in padroes:
            for m in padrao.finditer(sentenca):
                if _negado(sentenca, m.start()):
                    achados.add(tema)
    return achados


def _polaridade(texto: str) -> int:
    pos = sum(1 for m in _POSITIVO.finditer(texto) if not _negado(texto, m.start()))
    neg = len(_NEGATIVO.findall(texto))
    return pos - neg


def _compilar_aliases(cardapio: Sequence[ItemCardapio]) -> list[tuple[str, re.Pattern]]:
    compilados = []
    for item in cardapio:
        termos = sorted({normalizar(a) for a in (item.nome, *item.aliases)}, key=len, reverse=True)
        padrao = r"\b(?:" + "|".join(re.escape(t) for t in termos) + r")\b"
        compilados.append((item.nome, re.compile(padrao)))
    return compilados


class ProvedorRegras:
    nome = "regras"
    modelo = "lexico"
    versao = "1"

    def classificar(
        self, entradas: Sequence[EntradaAvaliacao], cardapio: Sequence[ItemCardapio]
    ) -> list[Classificacao | None]:
        aliases = _compilar_aliases(cardapio)
        return [self._classificar_uma(e, aliases) for e in entradas]

    def _classificar_uma(self, entrada: EntradaAvaliacao, aliases: list[tuple[str, re.Pattern]]) -> Classificacao:
        texto = normalizar(entrada.texto)
        temas: set[str] = set()
        pratos: dict[str, set[str]] = {}
        for sentenca in (s.strip() for s in _SEPARADOR.split(texto)):
            if not sentenca:
                continue
            temas_s = _temas_da_sentenca(sentenca)
            temas |= temas_s
            for nome, padrao in aliases:
                if padrao.search(sentenca):
                    pratos.setdefault(nome, set()).update(temas_s)

        score = _polaridade(texto) - 1.2 * len(temas) + 0.6 * (entrada.nota - 3)
        sentimento = "positivo" if score >= 1 else "negativo" if score <= -1 else "neutro"
        return Classificacao(
            sentimento=sentimento,
            temas=tuple(t for t in TEMAS if t in temas),
            pratos=tuple(
                PratoClassificado(n, tuple(t for t in TEMAS if t in ts)) for n, ts in sorted(pratos.items())
            ),
        )
