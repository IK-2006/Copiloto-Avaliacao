"""Vocabulário fechado do domínio. A IA só pode responder com valores destas listas."""
from __future__ import annotations

import unicodedata

SENTIMENTOS = ("positivo", "neutro", "negativo")

TEMAS = (
    "atraso", "temperatura", "textura", "embalagem",
    "sabor", "quantidade", "atendimento", "pedido_errado",
)

ROTULO_TEMA = {
    "atraso": "Atraso na entrega",
    "temperatura": "Comida fria / temperatura",
    "textura": "Textura (murcha, mole)",
    "embalagem": "Embalagem",
    "sabor": "Sabor",
    "quantidade": "Quantidade",
    "atendimento": "Atendimento",
    "pedido_errado": "Pedido errado",
}


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar textos escritos de formas diferentes."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return sem_acento.lower()
