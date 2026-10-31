"""Catálogo de sugestões de melhoria, escolhidas por regra a partir do problema encontrado.

Não há IA aqui de propósito: cada sugestão é uma ideia comum no setor, escrita de antemão, e o código
só decide quais mostrar. Elas são hipóteses a testar, não garantia de resultado, e cada uma traz o
indicador para saber se funcionou.
"""
from __future__ import annotations

from dataclasses import dataclass

from copiloto.analytics.impacto import Candidato

AVISO = (
    "Sugestões a avaliar: são ideias comuns no setor, escolhidas conforme o tipo de problema e de prato. "
    "Não são garantia de resultado. Teste em pequena escala e acompanhe o indicador sugerido antes de "
    "ampliar."
)

LIMITE_POR_ACAO = 5


@dataclass(frozen=True)
class Sugestao:
    texto: str
    porque: str
    como_medir: str


def _s(texto: str, porque: str, como_medir: str) -> Sugestao:
    return Sugestao(texto, porque, como_medir)


# Ajustes de operação, por tema de problema.
OPERACAO: dict[str, list[Sugestao]] = {
    "atraso": [
        _s("Mostrar no app um prazo de entrega realista nos horários de pico",
           "Um prazo honesto reduz a frustração de passar do combinado, mesmo quando a entrega continua longa.",
           "% de avaliações que citam atraso nesse horário, nas 4 semanas seguintes."),
        _s("Escalar mais uma pessoa na cozinha e outra na entrega nos horários de pico",
           "No pico o preparo e o deslocamento tendem a ficar mais longos; reforçar os dois ataca as duas causas.",
           "Tempo médio de preparo e de entrega nesse horário."),
        _s("Limitar pedidos simultâneos ou pausar o raio mais distante enquanto a fila estiver cheia",
           "Evita que um pedido novo atrase todos os que já estão na fila.",
           "% de pedidos acima de 40 minutos no horário."),
    ],
    "temperatura": [
        _s("Despachar cada pedido assim que ficar pronto, sem esperar para juntar entregas",
           "Comida que espera no balcão perde calor antes mesmo de sair.",
           "Tempo entre 'pedido pronto' e saída do entregador."),
        _s("Usar bolsa térmica e embalagem fechada com isolamento nas entregas longas",
           "O calor se perde sobretudo nos trajetos acima de 40 minutos.",
           "% de avaliações que citam comida fria em entregas acima de 40 min."),
        _s("Sincronizar a saída da cozinha com a chegada do entregador",
           "O pedido deixa de esfriar à espera de quem vai levá-lo.",
           "Tempo médio de espera do pedido pronto no balcão."),
    ],
    "textura": [
        _s("Usar embalagens com respiro para o vapor sair (furos ou papel absorvente)",
           "Em caixa fechada o vapor amolece a comida durante o trajeto.",
           "% de avaliações que citam comida murcha ou mole."),
        _s("Enviar à parte o que amolece (molhos, saladas, coberturas)",
           "Separar o úmido do que precisa ficar seco preserva a textura.",
           "% de avaliações que citam textura nos pratos afetados."),
    ],
    "embalagem": [
        _s("Trocar por embalagem com tampa firme e lacre, e testar com um pedido de 40 minutos de trajeto",
           "Vazamento e caixa aberta costumam vir de embalagem que só foi testada na cozinha.",
           "Nº de avaliações que citam embalagem por semana."),
    ],
    "sabor": [
        _s("Padronizar as receitas com ficha técnica (pesos, tempo e ponto de sal)",
           "Variação entre cozinheiros costuma ser a origem de comida fraca ou salgada.",
           "% de avaliações que citam sabor, por prato."),
        _s("Fazer uma degustação interna semanal dos pratos mais citados",
           "Pega desvio antes de virar avaliação.",
           "Nº de reclamações de sabor por prato."),
    ],
    "quantidade": [
        _s("Padronizar as porções com medida (gramatura ou balança) e informar no cardápio",
           "Cliente que sabe o que esperar reclama menos de 'pouca comida'.",
           "% de avaliações que citam quantidade."),
    ],
    "atendimento": [
        _s("Responder mensagens e avaliações em até 24 horas com um roteiro padrão",
           "Resposta rápida costuma converter uma reclamação em oportunidade de recuperar o cliente.",
           "Tempo médio de resposta e % de avaliações que citam atendimento."),
        _s("Treinar atendentes e entregadores nos casos que mais se repetem",
           "Foco nos motivos recorrentes rende mais que treinamento genérico.",
           "% de avaliações que citam atendimento."),
    ],
    "pedido_errado": [
        _s("Conferir o pedido com checklist antes de lacrar a sacola",
           "A maioria dos erros acontece na expedição, no último passo.",
           "Nº de avaliações com pedido errado ou item faltando por semana."),
        _s("Etiquetar a sacola com o número do pedido e a lista de itens",
           "Facilita a conferência por quem embala e por quem recebe.",
           "Nº de avaliações com pedido errado por semana."),
    ],
}

# Extras conforme as condições do segmento da causa raiz.
EXTRAS_DISTANCIA = [
    _s("Usar embalagem térmica para entregas acima de 5 km e avaliar o raio ou uma taxa progressiva por distância",
       "Quanto mais longo o trajeto, maior a perda de temperatura e de textura.",
       "% de avaliações com problema nos pedidos acima de 5 km."),
]
EXTRAS_PICO = [
    _s("Montar uma escala própria para o pico (por exemplo, sexta das 18h às 22h) e revisar o que muda depois de 4 semanas",
       "O problema se concentra nesse dia e horário; atacar o pico rende mais que mexer no restante da semana.",
       "Nota média e tempo de entrega nesse horário, comparados às 4 semanas anteriores."),
]

# Sugestões por prato: (prato, tema) vale mais que (categoria, tema).
_PORCAO_TEXTURA = [
    _s("Embalar com furos de ventilação ou papel absorvente no fundo",
       "A porção frita cozinha no próprio vapor dentro da caixa fechada e perde a crocância.",
       "% de avaliações que citam o prato como murcho ou mole."),
    _s("Enviar o molho e o sal à parte",
       "O molho umedece a porção durante o trajeto.",
       "% de avaliações que citam o prato como murcho ou mole."),
    _s("Ajustar o tempo e a temperatura de fritura (por exemplo, dupla fritura) e deixar escorrer bem antes de embalar",
       "Fritura no ponto e sem excesso de óleo segura a crocância por mais tempo.",
       "% de avaliações que citam o prato como murcho ou mole."),
]
_PORCAO_TEMPERATURA = [
    _s("Fritar por último, embalar logo antes da saída e usar caixa de papelão em vez de plástico",
       "A porção sai mais quente e o papelão absorve a umidade sem reter calor demais.",
       "% de avaliações que citam o prato como frio."),
]

PRATOS: dict[tuple[str, str], list[Sugestao]] = {
    ("Batata Frita", "textura"): _PORCAO_TEXTURA,
    ("Batata Frita", "temperatura"): _PORCAO_TEMPERATURA,
    ("Açaí 500ml", "temperatura"): [
        _s("Usar embalagem térmica com gelo reutilizável para entregas longas",
           "O açaí derrete com o tempo e a distância; o isolamento ganha minutos.",
           "% de avaliações que citam açaí derretido em entregas acima de 5 km."),
        _s("Enviar coberturas e frutas em potes separados e o creme bem congelado",
           "Menos calor trocado dentro da embalagem e menos líquido ao abrir.",
           "% de avaliações que citam açaí derretido."),
        _s("Avisar no app, ou não oferecer o açaí, para endereços acima de 5 km",
           "Em trajetos longos o açaí tende a derreter antes de chegar, mesmo com boa embalagem.",
           "Nº de reclamações de açaí e de pedidos de açaí acima de 5 km."),
    ],
}

CATEGORIAS: dict[tuple[str, str], list[Sugestao]] = {
    ("Porções", "textura"): _PORCAO_TEXTURA,
    ("Porções", "temperatura"): _PORCAO_TEMPERATURA,
    ("Hambúrgueres", "textura"): [
        _s("Torrar o pão na chapa com manteiga e enviar alface e tomate à parte",
           "O pão tostado resiste mais à umidade do hambúrguer e dos vegetais.",
           "% de avaliações que citam o hambúrguer como mole ou ressecado."),
    ],
    ("Hambúrgueres", "temperatura"): [
        _s("Embalar cada hambúrguer em papel alumínio ou papel manteiga antes da caixa",
           "Retém o calor e evita que o pão suado esfrie.",
           "% de avaliações que citam o hambúrguer como frio."),
    ],
    ("Pizzas", "temperatura"): [
        _s("Usar caixa de papelão com respiro dentro de bolsa térmica",
           "Mantém a pizza quente sem encharcar a massa.",
           "% de avaliações que citam a pizza como fria."),
    ],
    ("Pizzas", "textura"): [
        _s("Colocar papel absorvente sob a pizza e deixar um respiro na caixa",
           "A massa não amolece com o vapor.",
           "% de avaliações que citam a pizza como mole."),
    ],
    ("Massas", "temperatura"): [
        _s("Embalar a massa em recipiente de alumínio com tampa, dentro da bolsa térmica",
           "O alumínio retém calor melhor que o plástico.",
           "% de avaliações que citam a massa como fria."),
    ],
    ("Massas", "textura"): [
        _s("Enviar o molho à parte para a massa não passar do ponto",
           "A massa continua cozinhando no molho quente dentro da caixa.",
           "% de avaliações que citam a massa como mole."),
    ],
}


def sugestoes_para(candidato: Candidato, categorias: dict[str, str] | None = None) -> list[Sugestao]:
    """Sugestões a avaliar para uma ação do plano, sem repetição e no máximo `LIMITE_POR_ACAO`."""
    categorias = categorias or {}
    escolhidas: list[Sugestao] = []

    def adicionar(itens: list[Sugestao]) -> None:
        for item in itens:
            if item not in escolhidas:
                escolhidas.append(item)

    if candidato.tipo == "prato" and candidato.prato:
        categoria = categorias.get(candidato.prato, "")
        for tema in candidato.temas[:2]:
            adicionar(PRATOS.get((candidato.prato, tema)) or CATEGORIAS.get((categoria, tema)) or OPERACAO[tema][:1])
    else:
        # O que é específico do segmento (pico, distância) vem antes das ideias gerais por tema.
        condicoes = {c for _, p in candidato.padroes for c in p.condicoes}
        if any(c in ("de sexta-feira", "de sábado", "de domingo", "à noite") for c in condicoes):
            adicionar(EXTRAS_PICO)
        if any(c.startswith("a mais de") for c in condicoes):
            adicionar(EXTRAS_DISTANCIA)
        for tema in candidato.temas:
            adicionar(OPERACAO[tema][:2])
    return escolhidas[:LIMITE_POR_ACAO]
