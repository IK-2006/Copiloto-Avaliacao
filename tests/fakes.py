"""Cliente Anthropic falso: permite testar o provedor Claude sem rede nem chave."""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from types import SimpleNamespace

from copiloto.llm.base import EntradaAvaliacao, ItemCardapio
from copiloto.llm.rules import ProvedorRegras


def resposta(texto: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=texto)])


class _Mensagens:
    def __init__(self, responder: Callable[[dict], SimpleNamespace]) -> None:
        self._responder = responder
        self.chamadas: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        # guarda uma foto da conversa nesta chamada: o agente continua acrescentando mensagens à mesma lista
        self.chamadas.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        return self._responder(kwargs)


class ClienteFalso:
    def __init__(self, responder: Callable[[dict], SimpleNamespace]) -> None:
        self.messages = _Mensagens(responder)

    @property
    def chamadas(self) -> list[dict]:
        return self.messages.chamadas

    def texto_enviado(self) -> str:
        """Tudo o que o modelo receberia: system + mensagens."""
        return "\n".join(str(c["system"]) + "\n" + m["content"] for c in self.chamadas for m in c["messages"])


def avaliacoes_da_chamada(kwargs: dict) -> list[dict]:
    conteudo = kwargs["messages"][0]["content"]
    bruto = re.search(r"<avaliacoes>\n(.*)\n</avaliacoes>", conteudo, re.DOTALL).group(1)
    return json.loads(bruto)


def responder_como_regras(cardapio: list[ItemCardapio]) -> Callable[[dict], SimpleNamespace]:
    """Um 'modelo' bem-comportado: devolve o que o provedor de regras classificaria."""
    regras = ProvedorRegras()

    def _responder(kwargs: dict) -> SimpleNamespace:
        itens = avaliacoes_da_chamada(kwargs)
        entradas = [EntradaAvaliacao(i["ref"], i["nota"], i["texto"], tuple(i["itens_do_pedido"])) for i in itens]
        saida = []
        for entrada, cls in zip(entradas, regras.classificar(entradas, cardapio)):
            saida.append({
                "ref": entrada.ref,
                "sentimento": cls.sentimento,
                "temas": list(cls.temas),
                "pratos": [{"prato": p.prato, "problemas": list(p.problemas)} for p in cls.pratos],
            })
        return resposta(json.dumps({"classificacoes": saida}))

    return _responder


# --- Respostas do Claude com ferramentas (modo perguntas) ---------------------------------------
def uso_de_ferramenta(nome: str, argumentos: dict, id_: str = "t1") -> SimpleNamespace:
    """Resposta em que o modelo pede para chamar uma ferramenta."""
    bloco = SimpleNamespace(type="tool_use", id=id_, name=nome, input=argumentos)
    return SimpleNamespace(stop_reason="tool_use", content=[bloco])


def texto_final(texto: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=texto)])


def roteiro(*respostas: SimpleNamespace) -> Callable[[dict], SimpleNamespace]:
    """Responde, em ordem, uma resposta pronta por chamada à API."""
    fila = list(respostas)

    def _responder(kwargs: dict) -> SimpleNamespace:
        if not fila:
            raise AssertionError("o agente fez mais chamadas à API do que o roteiro previa")
        return fila.pop(0)

    return _responder
