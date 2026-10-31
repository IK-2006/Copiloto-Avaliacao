"""Estatísticas básicas. Todo percentual exibido no app nasce aqui, nunca da IA."""
from __future__ import annotations

from dataclasses import dataclass

LIMIAR_BAIXA_CONFIANCA = 20


@dataclass(frozen=True)
class Proporcao:
    """k ocorrências em n avaliações."""

    k: int
    n: int

    @property
    def pct(self) -> float:
        return 100.0 * self.k / self.n if self.n else 0.0

    @property
    def baixa_confianca(self) -> bool:
        return self.n < LIMIAR_BAIXA_CONFIANCA

    def texto(self, casas: int = 0, unidade: str = "avaliações") -> str:
        """Ex.: '65% de 120 avaliações'. Sempre mostra a base (n)."""
        base = f"{formatar_pct(self.pct, casas)} de {self.n} {unidade}"
        if self.baixa_confianca:
            base += " (baixa confiança)"
        return base


def pct_com_n(k: int, n: int) -> Proporcao:
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"proporção inválida: k={k}, n={n}")
    return Proporcao(int(k), int(n))


def formatar_pct(valor: float, casas: int = 0) -> str:
    """Formata no padrão brasileiro (vírgula decimal)."""
    return f"{valor:.{casas}f}".replace(".", ",") + "%"


def formatar_nota(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")
