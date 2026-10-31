"""Pipeline de classificação: anonimiza, chama o provedor de IA e guarda o resultado em cache.

Uso: python -m copiloto.classify [--provedor auto|regras|claude] [--forcar]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from copiloto import db
from copiloto.llm import sanitize
from copiloto.llm.base import EntradaAvaliacao, ItemCardapio, ProvedorIA
from copiloto.llm.factory import obter_provedor


@dataclass
class ResumoClassificacao:
    total: int = 0
    classificadas: int = 0
    em_cache: int = 0
    falhas: int = 0
    injecoes_detectadas: int = 0
    pratos_fora_do_pedido: int = 0


def carregar_cardapio(con: sqlite3.Connection) -> list[ItemCardapio]:
    return [
        ItemCardapio(r["nome"], tuple(json.loads(r["aliases"])))
        for r in con.execute("SELECT nome, aliases FROM cardapio ORDER BY item_id")
    ]


def _itens_por_pedido(con: sqlite3.Connection) -> dict[int, tuple[str, ...]]:
    itens: dict[int, list[str]] = {}
    consulta = """SELECT pi.pedido_id, c.nome FROM pedido_itens pi
                  JOIN cardapio c ON c.item_id = pi.item_id ORDER BY pi.pedido_id, c.nome"""
    for r in con.execute(consulta):
        itens.setdefault(r["pedido_id"], []).append(r["nome"])
    return {k: tuple(v) for k, v in itens.items()}


def classificar_pendentes(
    con: sqlite3.Connection, provedor: ProvedorIA, *, forcar: bool = False, lote: int = 60
) -> ResumoClassificacao:
    """Classifica o que ainda não está em cache (ou tudo, com forcar=True)."""
    cardapio = carregar_cardapio(con)
    itens_pedido = _itens_por_pedido(con)
    em_cache = {
        r["avaliacao_id"]: r["hash_entrada"] for r in con.execute("SELECT avaliacao_id, hash_entrada FROM classificacoes")
    }
    consulta = """SELECT a.avaliacao_id, a.pedido_id, a.nota, a.texto, c.nome, c.endereco
                  FROM avaliacoes a JOIN clientes c ON c.cliente_id = a.cliente_id
                  ORDER BY a.avaliacao_id"""
    resumo = ResumoClassificacao()
    pendentes: list[tuple[EntradaAvaliacao, int | None, str, bool]] = []
    for r in con.execute(consulta):
        resumo.total += 1
        itens = itens_pedido.get(r["pedido_id"], ()) if r["pedido_id"] else ()
        # O texto sai daqui sem dados pessoais; nome e endereço do cliente nunca chegam à IA.
        texto = sanitize.limpar_texto(sanitize.mascarar_pii(r["texto"], nomes=[r["nome"]], frases=[r["endereco"]]))
        entrada = EntradaAvaliacao(sanitize.referencia_avaliacao(r["avaliacao_id"]), r["nota"], texto, itens)
        chave = sanitize.hash_entrada({
            "ref": entrada.ref, "nota": entrada.nota, "texto": entrada.texto, "itens": list(itens),
            "provedor": provedor.nome, "modelo": provedor.modelo, "versao": provedor.versao,
        })
        if not forcar and em_cache.get(r["avaliacao_id"]) == chave:
            resumo.em_cache += 1
            continue
        injecao = sanitize.detectar_injecao(r["texto"])
        resumo.injecoes_detectadas += int(injecao)
        pendentes.append((entrada, r["pedido_id"], chave, injecao))

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i in range(0, len(pendentes), lote):
        parte = pendentes[i : i + lote]
        resultados = provedor.classificar([p[0] for p in parte], cardapio)
        for (entrada, pedido_id, chave, injecao), cls in zip(parte, resultados):
            if cls is None:
                resumo.falhas += 1
                continue
            pratos = list(cls.pratos)
            if pedido_id is not None:
                # Só vale prato que está no pedido: ancora a avaliação nos itens que o cliente comprou.
                validos = [p for p in pratos if p.prato in entrada.itens_pedido]
                resumo.pratos_fora_do_pedido += len(pratos) - len(validos)
                pratos = validos
            con.execute(
                "INSERT OR REPLACE INTO classificacoes VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    int(entrada.ref.removeprefix("av_")),
                    cls.sentimento,
                    json.dumps(list(cls.temas), ensure_ascii=False),
                    json.dumps([{"prato": p.prato, "problemas": list(p.problemas)} for p in pratos], ensure_ascii=False),
                    int(injecao),
                    provedor.nome,
                    provedor.modelo,
                    chave,
                    agora,
                ),
            )
            resumo.classificadas += 1
        con.commit()
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description="Classifica as avaliações com sentimento, temas e pratos.")
    ap.add_argument("--provedor", default="auto", choices=["auto", "regras", "claude"])
    ap.add_argument("--forcar", action="store_true", help="reclassifica tudo, ignorando o cache")
    args = ap.parse_args()

    provedor = obter_provedor(args.provedor)
    con = db.conectar()
    resumo = classificar_pendentes(con, provedor, forcar=args.forcar)
    print(f"Provedor: {provedor.nome} ({provedor.modelo})")
    for campo, valor in vars(resumo).items():
        print(f"  {campo}: {valor}")


if __name__ == "__main__":
    main()
