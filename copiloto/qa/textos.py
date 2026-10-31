"""Respostas em texto montadas por código a partir do que as ferramentas devolveram (modo offline).

Como o texto é montado só com os números dos resultados, ele passa na checagem de números do agente.
"""
from __future__ import annotations

from copiloto.qa.ferramentas import ResultadoFerramenta


def _n(x: float, casas: int = 2) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def _p(d: dict) -> str:
    return f"{d['pct']:.0f}%"


def _kn(d: dict, unidade: str = "avaliações") -> str:
    return f"{_p(d)} ({d['k']} de {d['n']} {unidade})"


def sem_dados(motivo: str) -> str:
    return f"Não consigo responder com os dados disponíveis. {motivo}"


def nota_por_mes(r: ResultadoFerramenta) -> str:
    linhas = ["Nota média por mês (todas as avaliações; entre parênteses, sem as suspeitas):"]
    for m in r.dados["meses"]:
        linhas.append(f"- {m['rotulo']}: {_n(m['todas']['nota'])} em {m['todas']['avaliacoes']} avaliações "
                      f"({_n(m['sem_suspeitas']['nota'])} sem suspeitas)")
    return "\n".join(linhas)


def nota_media(r: ResultadoFerramenta) -> str:
    d = r.dados
    t, s = d["todas"], d["sem_suspeitas"]
    texto = (f"Em {d['periodo']}, a nota média é **{_n(t['nota'])}** em {t['avaliacoes']} avaliações; "
             f"{_kn(t['negativas'])} são negativas.")
    if s["avaliacoes"] != t["avaliacoes"]:
        texto += (f" Sem as avaliações suspeitas (médias e altas), a nota é **{_n(s['nota'])}** em {s['avaliacoes']} "
                  f"avaliações, com {_p(s['negativas'])} negativas.")
    return texto


def ranking_de_pratos(r: ResultadoFerramenta) -> str:
    pratos = r.dados["pratos"]
    if len(pratos) == 1:
        a = pratos[0]
        texto = f"**{a['prato']}**: {_kn(a['com_problema'], 'avaliações que o citam')} relatam algum problema."
        if a["baixa_confianca"]:
            texto += " Atenção: são poucas avaliações (baixa confiança)."
        if a["problemas"]:
            texto += " Problemas mais citados: " + "; ".join(f"{x['rotulo'].lower()} ({_p(x)})" for x in a["problemas"][:3]) + "."
        return texto
    primeiro = pratos[0]
    maior = r.dados["prato_com_mais_reclamacoes_em_numero"]
    texto = (f"O prato com mais problemas é **{primeiro['prato']}**: {_kn(primeiro['com_problema'], 'avaliações que o citam')} "
             "relatam algum problema.")
    if primeiro["problemas"]:
        texto += " Os mais citados: " + "; ".join(f"{x['rotulo'].lower()} ({_p(x)})" for x in primeiro["problemas"][:2]) + "."
    if maior["prato"] == primeiro["prato"]:
        texto += f" Também é o que soma mais reclamações em número ({maior['reclamacoes']})."
    else:
        texto += f" Em número de reclamações, o primeiro é {maior['prato']} ({maior['reclamacoes']})."
    outros = [f"{a['prato']} ({_p(a['com_problema'])} de {a['com_problema']['n']}"
              f"{', baixa confiança' if a['baixa_confianca'] else ''})" for a in pratos[1:4]]
    if outros:
        texto += "\n\nEm seguida: " + "; ".join(outros) + "."
    return texto


def temas_de_reclamacao(r: ResultadoFerramenta) -> str:
    temas = r.dados["temas"][:4]
    itens = "; ".join(f"{t['rotulo'].lower()} ({_p(t)}, {t['k']} de {t['n']})" for t in temas)
    return f"Temas de reclamação mais citados em {r.dados['periodo']}: {itens}."


def causa_raiz(r: ResultadoFerramenta) -> str:
    d = r.dados
    linhas = [f"Sobre **{d['tema'].lower()}**:"]
    if d["condicao_do_pedido"]:
        linhas.append("- **Condição do pedido:** " + d["condicao_do_pedido"][0]["frase"])
    if d["quando_e_onde"]:
        linhas.append("- **Quando e onde:** " + " ".join(p["frase"] for p in d["quando_e_onde"][:2]))
    linhas.append(f"({(d['quando_e_onde'] or d['condicao_do_pedido'])[0]['evidencia']}.)")
    return "\n".join(linhas)


def causa_raiz_do_prato(r: ResultadoFerramenta) -> str:
    p = r.dados["padroes"][0]
    return f"Sobre os problemas de **{r.dados['prato']}**: {p['frase']}"


def plano_de_acao(r: ResultadoFerramenta) -> str:
    d = r.dados
    linhas = [f"Em ordem de efeito estimado na nota (hoje {_n(d['nota_atual'])}):"]
    for a in d["acoes"]:
        aviso = " (baixa confiança)" if a["baixa_confianca"] else ""
        linhas.append(f"{a['prioridade']}. **{a['titulo']}**: nota de {_n(a['nota_antes'])} para {_n(a['nota_depois'])} "
                      f"(no cenário conservador, +{_n(a['ganho_conservador'])}); {a['avaliacoes_afetadas']['k']} avaliações afetadas{aviso}.")
    linhas.append(f"Com todo o plano a nota iria a {_n(d['nota_com_todo_o_plano']['completo'])} (conservador: "
                  f"{_n(d['nota_com_todo_o_plano']['conservador'])}). É uma estimativa, não uma previsão.")
    return "\n".join(linhas)


def avaliacoes_suspeitas(r: ResultadoFerramenta) -> str:
    d = r.dados
    n = d["niveis"]
    linhas = [f"Há {n['alto']} avaliações suspeitas de nível alto, {n['médio']} médias e {n['baixo']} baixas, em {d['total_de_avaliacoes']} avaliações."]
    for e in d["episodios"]:
        linhas.append("- " + e["resumo"])
    linhas.append(f"Sem as suspeitas (médias e altas), a nota vai de {_n(d['nota_com_todas'])} para {_n(d['nota_sem_suspeitas'])}. "
                  "A ferramenta só sinaliza: a decisão de contestar é sua.")
    return "\n".join(linhas)


def explicar_variacao_da_nota(r: ResultadoFerramenta) -> str:
    d = r.dados
    nota, t, s = d["nota"], d["nota"]["todas"], d["nota"]["sem_suspeitas"]
    sentido = "queda" if t["queda"] > 0 else "alta"
    linhas = [f"Em {d['mes']} a nota média foi **{_n(t['no_mes'])}**, contra {_n(t['meses_anteriores'])} nos meses anteriores "
              f"({sentido} de {_n(abs(t['queda']))})."]
    susp = d["suspeitas_no_mes"]
    if susp["avaliacoes"]["k"] and nota["efeito_das_suspeitas"] > 0.05:
        linhas.append(
            f"- **Avaliações suspeitas:** {susp['avaliacoes']['k']} das {susp['avaliacoes']['n']} avaliações do mês "
            f"({_p(susp['avaliacoes'])}) são suspeitas (médias ou altas), com nota média {_n(susp['nota_media'], 1)}. "
            f"Sem elas, a nota do mês é {_n(s['no_mes'])} contra {_n(s['meses_anteriores'])} antes, e a {sentido} cai de "
            f"{_n(abs(t['queda']))} para {_n(abs(s['queda']))}. Ou seja, {_n(nota['efeito_das_suspeitas'])} pontos vêm das suspeitas."
        )
    crescentes = [x for x in d["temas"] if x["significativo"]]
    if crescentes:
        linhas.append("- **Temas que ficaram mais frequentes** (já sem as suspeitas): " + "; ".join(
            f"{x['rotulo'].lower()} ({x['no_mes']['pct']:.0f}% das avaliações, contra {x['meses_anteriores']['pct']:.0f}% antes)"
            for x in crescentes) + ".")
    else:
        linhas.append("- **Temas de reclamação:** nenhum ficou significativamente mais frequente no mês, pelo teste estatístico.")
    for seg in d["entrega"]["segmentos"]:
        linhas.append(f"- **Tempo de entrega:** em {seg['segmento']}, passou de {seg['meses_anteriores']:.0f} min para "
                      f"{seg['no_mes']:.0f} min (+{seg['diferenca_min']:.0f} min, {seg['pedidos_no_mes']} pedidos no mês).")
    if d["entrega"]["segmentos"] and nota["efeito_das_suspeitas"] > 0.05:
        linhas.append(f"Em resumo: a maior parte da {sentido} vem das avaliações suspeitas; os {_n(abs(s['queda']))} restantes "
                      "coincidem com a piora no tempo de entrega, o que não prova que ela seja a causa.")
    return "\n".join(linhas)


COMPOSITORES = {
    "nota_por_mes": nota_por_mes, "nota_media": nota_media, "ranking_de_pratos": ranking_de_pratos,
    "temas_de_reclamacao": temas_de_reclamacao, "causa_raiz": causa_raiz, "causa_raiz_do_prato": causa_raiz_do_prato,
    "plano_de_acao": plano_de_acao, "avaliacoes_suspeitas": avaliacoes_suspeitas,
    "explicar_variacao_da_nota": explicar_variacao_da_nota,
}

EXEMPLOS = [
    "Por que minha nota caiu em outubro?",
    "Qual prato mais gera reclamação?",
    "Por que a comida chega fria?",
    "O que devo resolver primeiro?",
    "Existem avaliações suspeitas?",
    "Quais são as principais reclamações?",
    "Como evoluiu a nota ao longo dos meses?",
]
