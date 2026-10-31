"""Confere, com a sua chave, os três usos do Claude no projeto: classificação, rascunho de resposta e perguntas.

    python scripts/check_claude.py

Faz cerca de 10 chamadas pequenas à API (poucos centavos) e não grava nada no banco. Precisa de ANTHROPIC_API_KEY
no ambiente ou no arquivo .env. A saída mostra o que o Claude devolveu e se passou nas validações do projeto
(vocabulário fechado, texto de resposta seguro, números conferidos contra as consultas).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copiloto import config, db  # noqa: E402
from copiloto.analytics.base import carregar_avaliacoes  # noqa: E402
from copiloto.analytics.suspeitas import com_suspeitas  # noqa: E402
from copiloto.classify import carregar_cardapio  # noqa: E402
from copiloto.llm import sanitize  # noqa: E402
from copiloto.llm.base import EntradaAvaliacao  # noqa: E402
from copiloto.llm.claude import ProvedorClaude  # noqa: E402
from copiloto.llm.rules import ProvedorRegras  # noqa: E402
from copiloto.qa.agente import AgenteClaude  # noqa: E402
from copiloto.qa.ferramentas import carregar_contexto  # noqa: E402
from copiloto.respostas import GeradorClaude, _entrada, ids_candidatos  # noqa: E402

PERGUNTAS = ["Por que minha nota caiu em outubro?", "Qual prato mais gera reclamação e por quê?"]


def main() -> int:
    cfg = config.carregar()
    if not cfg.anthropic_api_key:
        print("ANTHROPIC_API_KEY não está definida. Copie .env.example para .env e preencha a chave.")
        return 1
    con = db.conectar(cfg.db_path)
    cardapio = carregar_cardapio(con)

    print(f"== 1. Classificação ({cfg.modelo_classificacao}) ==")
    linhas = con.execute(
        """SELECT a.avaliacao_id, a.nota, a.texto, a.pedido_id, c.nome, c.endereco
           FROM avaliacoes a JOIN clientes c USING (cliente_id) ORDER BY a.avaliacao_id LIMIT 6""").fetchall()
    entradas = [EntradaAvaliacao(sanitize.referencia_avaliacao(r["avaliacao_id"]), r["nota"],
                                 sanitize.limpar_texto(sanitize.mascarar_pii(r["texto"], [r["nome"]], [r["endereco"]])), ())
                for r in linhas]
    claude = ProvedorClaude(cfg.modelo_classificacao, api_key=cfg.anthropic_api_key).classificar(entradas, cardapio)
    regras = ProvedorRegras().classificar(entradas, cardapio)
    iguais = 0
    for e, c, r in zip(entradas, claude, regras):
        print(f"- {e.ref}: Claude={'FALHOU (rejeitada pela validação)' if c is None else (c.sentimento, list(c.temas))} | regras={(r.sentimento, list(r.temas))}")
        iguais += c is not None and c.sentimento == r.sentimento
    print(f"Sentimento igual ao das regras em {iguais} de {len(entradas)} avaliações.\n")

    print(f"== 2. Rascunho de resposta ({cfg.modelo_geracao}) ==")
    ids = ids_candidatos(con)
    if ids:
        entrada, _, _ = _entrada(con, ids[0])
        texto = GeradorClaude(cfg.modelo_geracao, api_key=cfg.anthropic_api_key).gerar(entrada)
        print(texto if texto else "O Claude devolveu um texto que não passou na validação (o app usaria as regras).")
    print()

    print(f"== 3. Perguntas ({cfg.modelo_geracao}) ==")
    ctx = carregar_contexto(con, com_suspeitas(carregar_avaliacoes(con)))
    agente = AgenteClaude(cfg.modelo_geracao, api_key=cfg.anthropic_api_key)
    for pergunta in PERGUNTAS:
        resposta = agente.perguntar(pergunta, ctx)
        print(f"P: {pergunta}\nConsultas: {[u.nome for u in resposta.usos]}\n{resposta.texto}")
        print(f"Números não verificados: {resposta.numeros_nao_verificados or 'nenhum'}\n")
    print(f"Chamadas à API nas perguntas: {agente.chamadas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
