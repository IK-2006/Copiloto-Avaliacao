"""Restaurante e cardápio fictícios usados na demonstração."""
from __future__ import annotations

from dataclasses import dataclass

NOME_RESTAURANTE = "Cantina Sabor da Vila"


@dataclass(frozen=True)
class ItemDef:
    nome: str
    categoria: str
    preco: float
    genero: str                 # 'm' | 'f'
    peso: float                 # popularidade relativa nos pedidos
    quente: bool                # pode "chegar frio"
    falas: tuple[str, ...]      # como o cliente escreve ao reclamar/elogiar
    aliases: tuple[str, ...]    # termos que identificam o item no texto


ITENS: tuple[ItemDef, ...] = (
    ItemDef("X-Burger Clássico", "Hambúrgueres", 28.9, "m", 9, True,
            ("x-burger", "hambúrguer clássico"), ("x-burger", "x burger", "xburger", "hamburguer classico")),
    ItemDef("X-Bacon", "Hambúrgueres", 32.9, "m", 8, True,
            ("x-bacon", "hambúrguer de bacon"), ("x-bacon", "x bacon", "xbacon", "hamburguer de bacon")),
    ItemDef("Smash Duplo", "Hambúrgueres", 36.9, "m", 8, True,
            ("smash duplo", "smash"), ("smash",)),
    ItemDef("Burger Veggie", "Hambúrgueres", 30.9, "m", 2.5, True,
            ("burger veggie", "hambúrguer vegetariano"), ("veggie", "hamburguer vegetariano")),
    ItemDef("Pizza Margherita", "Pizzas", 49.9, "f", 6, True,
            ("pizza margherita", "margherita"), ("margherita", "marguerita")),
    ItemDef("Pizza Calabresa", "Pizzas", 47.9, "f", 7, True,
            ("pizza de calabresa", "calabresa"), ("calabresa",)),
    ItemDef("Pizza Quatro Queijos", "Pizzas", 54.9, "f", 4, True,
            ("pizza quatro queijos", "pizza de quatro queijos"), ("quatro queijos", "4 queijos")),
    ItemDef("Batata Frita", "Porções", 24.9, "f", 14, True,
            ("batata frita", "batata"), ("batata frita", "batata", "batatas", "fritas")),
    ItemDef("Onion Rings", "Porções", 22.9, "m", 4, True,
            ("onion rings", "onion"), ("onion rings", "onion", "anel de cebola", "aneis de cebola")),
    ItemDef("Frango Crocante", "Porções", 34.9, "m", 6, True,
            ("frango crocante", "frango"), ("frango crocante", "frango empanado", "frango", "iscas de frango")),
    ItemDef("Spaghetti à Bolonhesa", "Massas", 38.9, "m", 4, True,
            ("spaghetti", "macarrão à bolonhesa"), ("spaghetti", "espaguete", "macarrao", "bolonhesa")),
    ItemDef("Lasanha", "Massas", 41.9, "f", 4, True,
            ("lasanha",), ("lasanha",)),
    ItemDef("Salada Caesar", "Saladas", 29.9, "f", 1.5, False,
            ("salada caesar", "salada"), ("salada caesar", "caesar", "salada")),
    ItemDef("Açaí 500ml", "Sobremesas", 22.9, "m", 9, False,
            ("açaí",), ("acai",)),
    ItemDef("Brownie com Sorvete", "Sobremesas", 21.9, "m", 3, False,
            ("brownie",), ("brownie",)),
    ItemDef("Pudim", "Sobremesas", 12.9, "m", 1.2, False,
            ("pudim",), ("pudim",)),
    ItemDef("Milk-shake de Chocolate", "Bebidas", 19.9, "m", 4.5, False,
            ("milk-shake", "shake"), ("milk-shake", "milkshake", "milk shake", "shake")),
    ItemDef("Refrigerante Lata", "Bebidas", 6.5, "m", 12, False,
            ("refrigerante",), ("refrigerante", "refri")),
    ItemDef("Suco Natural", "Bebidas", 11.9, "m", 4, False,
            ("suco",), ("suco",)),
)

ITEM_POR_NOME = {i.nome: i for i in ITENS}
