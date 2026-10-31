"""Gera o restaurante fictício: clientes, pedidos, avaliações e o gabarito dos padrões plantados.

Padrões plantados (ver `descrever_padroes`):
  P1  Batata Frita chega murcha/fria em entregas longas (> 40 min).
  P2  Atrasos e comida fria nas sextas à noite; piora a partir de 01/10/2026.
  P3  Ataque de avaliações falsas entre 14 e 16/10/2026.
  P4  Açaí chega derretido em entregas acima de 5 km.
  P5  Pudim e Salada Caesar têm poucas avaliações (amostra pequena).
  P6  Duas avaliações tentam injetar instruções no classificador.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from copiloto import db
from copiloto.datagen import frases
from copiloto.datagen.cardapio import ITENS, NOME_RESTAURANTE

SEED_PADRAO = 2026
INICIO = date(2026, 5, 1)
FIM = date(2026, 10, 31)
N_PEDIDOS_ALVO = 3000
N_CLIENTES = 850
PIORA_SEXTA_DESDE = datetime(2026, 10, 1)
ATAQUE_DIAS = (date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 16))
N_FALSAS = 46

PESO_DIA_SEMANA = [0.80, 0.80, 0.85, 0.95, 1.45, 1.50, 1.25]
PESO_HORA = {11: 3, 12: 9, 13: 8, 14: 3, 15: 1, 16: 1, 17: 3, 18: 8, 19: 14, 20: 16, 21: 14, 22: 8, 23: 3}

PESO_TEMA = {  # gravidade de cada problema na nota
    "atraso": 1.0, "temperatura": 0.75, "textura": 0.45, "embalagem": 0.5,
    "sabor": 1.0, "quantidade": 0.5, "atendimento": 1.0, "pedido_errado": 1.3,
}

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João",
         "Karina", "Lucas", "Mariana", "Nicolas", "Olívia", "Pedro", "Quésia", "Rafael", "Sofia", "Thiago",
         "Úrsula", "Vinícius", "Wesley", "Yasmin", "Zeca", "Renata", "Marcos", "Patrícia", "Fábio", "Juliana"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento",
              "Lima", "Araújo", "Fernandes", "Carvalho", "Gomes", "Martins", "Rocha", "Ribeiro", "Barbosa"]
RUAS = ["Rua das Flores", "Av. Brasil", "Rua do Comércio", "Rua XV de Novembro", "Av. Paulista",
        "Rua das Palmeiras", "Rua São João", "Av. Central", "Rua dos Ipês", "Rua Bela Vista"]


@dataclass
class Pedido:
    id: int
    cliente_idx: int
    criado_em: datetime
    preparo: float
    entrega: float
    dist: float
    itens: list[tuple[int, int]]          # (índice no cardápio, quantidade)
    valor: float
    sexta_pico: bool

    @property
    def turno(self) -> str:
        h = self.criado_em.hour
        return "almoço" if h < 15 else "tarde" if h < 18 else "noite"


@dataclass
class Avaliacao:
    id: int
    pedido_id: int | None
    cliente_idx: int
    criado_em: datetime
    nota: int
    texto: str
    gabarito: dict = field(default_factory=dict)


def _ref(salt: str, cliente_id: int) -> str:
    return "cli_" + hashlib.sha256(f"{salt}:{cliente_id}".encode()).hexdigest()[:10]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def _escolha(rng: np.random.Generator, itens: list, p: list[float] | None = None):
    return itens[int(rng.choice(len(itens), p=p))]


# --- Pedidos -------------------------------------------------------------------------------
def _gerar_pedidos(rng: np.random.Generator) -> list[Pedido]:
    dias = [INICIO + timedelta(days=i) for i in range((FIM - INICIO).days + 1)]
    pesos_dia = np.array([PESO_DIA_SEMANA[d.weekday()] for d in dias])
    medias = N_PEDIDOS_ALVO * pesos_dia / pesos_dia.sum()
    horas = list(PESO_HORA)
    p_hora = np.array([PESO_HORA[h] for h in horas], dtype=float)
    p_hora /= p_hora.sum()
    p_item = np.array([i.peso for i in ITENS], dtype=float)
    p_item /= p_item.sum()

    pedidos: list[Pedido] = []
    for dia, media in zip(dias, medias):
        for _ in range(int(rng.poisson(media))):
            hora = horas[int(rng.choice(len(horas), p=p_hora))]
            criado = datetime(dia.year, dia.month, dia.day, hora, int(rng.integers(0, 60)), int(rng.integers(0, 60)))
            sexta_pico = dia.weekday() == 4 and 18 <= hora <= 22
            sabado_noite = dia.weekday() == 5 and hora >= 18

            dist = float(np.clip(rng.gamma(2.2, 1.4), 0.4, 12.0))
            preparo = rng.normal(17, 4) + (8 if sexta_pico else 0) + (3 if sabado_noite else 0)
            if sexta_pico and criado >= PIORA_SEXTA_DESDE:
                preparo += 6
            preparo = float(np.clip(preparo, 8, 55))
            deslocamento = 6 + 3.2 * dist + rng.normal(0, 4) + (8 if sexta_pico else 0)
            if sexta_pico and criado >= PIORA_SEXTA_DESDE:
                deslocamento += 10
            entrega = preparo + max(5.0, float(deslocamento))

            k = int(_escolha(rng, [1, 2, 3, 4], [0.25, 0.40, 0.25, 0.10]))
            idxs = rng.choice(len(ITENS), size=k, replace=False, p=p_item)
            itens = [(int(i), 2 if rng.random() < 0.08 else 1) for i in idxs]
            valor = sum(ITENS[i].preco * q for i, q in itens) + 3 + 0.8 * dist
            pedidos.append(Pedido(
                id=len(pedidos) + 1,
                cliente_idx=-1,
                criado_em=criado,
                preparo=round(preparo, 1),
                entrega=round(entrega, 1),
                dist=round(dist, 1),
                itens=itens,
                valor=round(valor, 2),
                sexta_pico=sexta_pico,
            ))
    pedidos.sort(key=lambda p: p.criado_em)
    for n, p in enumerate(pedidos, start=1):
        p.id = n
    return pedidos


# --- Achados (problemas) por pedido --------------------------------------------------------
def _achados_do_pedido(rng: np.random.Generator, p: Pedido) -> list[tuple[str, int | None]]:
    """Lista de (tema, índice do item ou None) que ocorreram neste pedido."""
    achados: set[tuple[str, int | None]] = set()
    entrega = p.entrega

    # atraso = quanto passou do prazo prometido, que cresce com a distância
    excesso = entrega - (28 + 2.2 * p.dist)
    p_atraso = 0.008 + 0.80 * _sigmoid((excesso - 12) / 4.5)
    if rng.random() < p_atraso:
        achados.add(("atraso", None))

    if entrega <= 40:
        p_temp = 0.01
    elif p.sexta_pico:
        p_temp = 0.70 if entrega <= 55 else 0.88
    else:
        p_temp = 0.04 if entrega <= 50 else 0.10
    if rng.random() < p_temp:
        quentes = [i for i, _ in p.itens if ITENS[i].quente]
        marcados = [i for i in quentes if rng.random() < 0.5]
        for i in marcados:
            achados.add(("temperatura", i))
        if not marcados or rng.random() < 0.4:
            achados.add(("temperatura", None))

    for tema, prob in (("embalagem", 0.020), ("sabor", 0.025), ("quantidade", 0.015), ("pedido_errado", 0.022)):
        if rng.random() < prob:
            item = None
            if tema in ("sabor", "quantidade", "pedido_errado") and rng.random() < 0.5:
                item = p.itens[int(rng.integers(len(p.itens)))][0]
            achados.add((tema, item))
    if rng.random() < (0.015 + (0.03 if ("atraso", None) in achados else 0)):
        achados.add(("atendimento", None))

    # P1: batata murcha/fria em entregas longas
    idx_batata = next(i for i, it in enumerate(ITENS) if it.nome == "Batata Frita")
    if any(i == idx_batata for i, _ in p.itens):
        if rng.random() < (0.80 if entrega > 40 else 0.10):
            achados.add(("textura", idx_batata))
            if rng.random() < 0.25:
                achados.add(("temperatura", idx_batata))

    # P4: açaí derretido em entregas longas (distância)
    idx_acai = next(i for i, it in enumerate(ITENS) if it.nome == "Açaí 500ml")
    if any(i == idx_acai for i, _ in p.itens):
        if rng.random() < (0.90 if p.dist > 5 else 0.03):
            achados.add(("temperatura", idx_acai))

    return sorted(achados, key=lambda a: (a[0], -1 if a[1] is None else a[1]))


# --- Texto da avaliação -------------------------------------------------------------------
def _sentimento(rng: np.random.Generator, achados: list[tuple[str, int | None]]) -> str:
    if not achados:
        return str(_escolha(rng, ["positivo", "neutro", "negativo"], [0.88, 0.11, 0.01]))
    temas = {t for t, _ in achados}
    gravidade = sum(PESO_TEMA[t] for t in temas) + rng.normal(0, 0.3)
    p_neg = float(np.clip((gravidade - 0.55) / 1.3, 0.03, 0.95))
    if rng.random() < p_neg:
        return "negativo"
    return "neutro" if rng.random() < 0.60 else "positivo"


def _nota(rng: np.random.Generator, sentimento: str) -> int:
    tabela = {
        "positivo": ([5, 4, 3], [0.78, 0.20, 0.02]),
        "neutro": ([3, 4, 2, 5], [0.45, 0.30, 0.15, 0.10]),
        "negativo": ([1, 2, 3, 4], [0.35, 0.40, 0.20, 0.05]),
    }
    notas, probs = tabela[sentimento]
    return int(_escolha(rng, notas, probs))


def _montar_texto(
    rng: np.random.Generator, p: Pedido, achados: list[tuple[str, int | None]], sentimento: str
) -> tuple[str, dict]:
    """Escreve o texto e devolve também o que realmente foi dito (gabarito)."""
    frases_txt: list[str] = []
    temas_ditos: set[str] = set()
    pratos_ditos: dict[str, set[str]] = {}

    por_item: dict[int, list[str]] = {}
    gerais: list[str] = []
    for tema, item in achados:
        if rng.random() > 0.88:
            continue  # o cliente não menciona este problema
        if item is not None and rng.random() < 0.92:
            por_item.setdefault(item, []).append(tema)
        else:
            gerais.append(tema)

    for item_idx, temas in por_item.items():
        item = ITENS[item_idx]
        combinada = frases.frase_combinada(rng, item) if set(temas) >= {"textura", "temperatura"} else None
        if combinada and rng.random() < 0.5:
            frases_txt.append(combinada)
            temas_ditos.update(temas)
            pratos_ditos.setdefault(item.nome, set()).update(temas)
            continue
        for tema in temas:
            frases_txt.append(frases.frase_achado(rng, tema, item=item, minutos=int(round(p.entrega, -1))))
            temas_ditos.add(tema)
            pratos_ditos.setdefault(item.nome, set()).add(tema)
    for tema in gerais:
        frases_txt.append(frases.frase_achado(rng, tema, minutos=int(round(p.entrega, -1))))
        temas_ditos.add(tema)

    prob_elogio = {"positivo": 0.65, "neutro": 0.40, "negativo": 0.10}[sentimento]
    if rng.random() < prob_elogio:
        candidatos = [i for i, _ in p.itens if ITENS[i].nome not in pratos_ditos]
        if candidatos:
            n = 1 if rng.random() < 0.7 or len(candidatos) == 1 else 2
            for i in rng.choice(candidatos, size=min(n, len(candidatos)), replace=False):
                item = ITENS[int(i)]
                frases_txt.append(frases.frase_elogio_item(rng, item))
                pratos_ditos.setdefault(item.nome, set())
    if sentimento == "positivo" and rng.random() < 0.5:
        frases_txt.append(frases.elogio_geral(rng))
    if sentimento == "neutro" and not temas_ditos and rng.random() < 0.6:
        frases_txt.append(frases.neutro_geral(rng))
    if sentimento != "negativo" and temas_ditos and rng.random() < 0.5:
        frases_txt.append(frases.sufixo_ameno(rng))

    rng.shuffle(frases_txt)
    abertura = frases.abertura(rng, sentimento)
    texto = " ".join(x for x in [abertura, *frases_txt] if x).strip()
    if not texto:
        texto = frases.neutro_geral(rng)
    texto = frases.aplicar_ruido(rng, texto, sentimento)

    gabarito = {
        "sentimento": sentimento,
        "temas": sorted(temas_ditos),
        "pratos": [{"prato": n, "problemas": sorted(t)} for n, t in sorted(pratos_ditos.items())],
        "falsa": False,
        "injecao": False,
    }
    return texto, gabarito


# --- Avaliações genuínas ------------------------------------------------------------------
def _gerar_avaliacoes(rng: np.random.Generator, pedidos: list[Pedido]) -> list[Avaliacao]:
    avaliacoes: list[Avaliacao] = []
    limite = datetime(FIM.year, FIM.month, FIM.day, 23, 59, 59)
    for p in pedidos:
        achados = _achados_do_pedido(rng, p)
        if rng.random() >= (0.26 if achados else 0.18):
            continue
        sentimento = _sentimento(rng, achados)
        texto, gab = _montar_texto(rng, p, achados, sentimento)
        espera = float(rng.exponential(2.0) * 60) + 20  # minutos após a entrega
        criado = min(p.criado_em + timedelta(minutes=p.entrega + espera), limite)
        avaliacoes.append(Avaliacao(
            id=0, pedido_id=p.id, cliente_idx=p.cliente_idx, criado_em=criado.replace(microsecond=0),
            nota=_nota(rng, sentimento), texto=texto, gabarito=gab,
        ))
    return avaliacoes


def _plantar_injecoes(rng: np.random.Generator, avaliacoes: list[Avaliacao]) -> None:
    """P6: acrescenta uma tentativa de injeção a duas avaliações negativas reais."""
    candidatas = [a for a in avaliacoes if a.gabarito["sentimento"] == "negativo" and a.gabarito["temas"]]
    escolhidas = rng.choice(len(candidatas), size=len(frases.INJECOES), replace=False)
    for k, idx in enumerate(escolhidas):
        a = candidatas[int(idx)]
        a.texto = f"{a.texto} {frases.INJECOES[k]}"
        a.gabarito["injecao"] = True


# --- Ataque de avaliações falsas ------------------------------------------------------------
def _variar_falsa(rng: np.random.Generator, base: str) -> str:
    texto = base
    for original, opcoes in frases.FALSAS_SINONIMOS:
        if original in texto and rng.random() < 0.5:
            texto = texto.replace(original, str(_escolha(rng, opcoes)), 1)
    if rng.random() < 0.3:
        texto = texto.replace("!", "!!", 1)
    return texto


# --- Orquestração ----------------------------------------------------------------------------
def gerar(caminho_db: str | Path, caminho_gabarito: str | Path, seed: int = SEED_PADRAO, salt: str = "copiloto-demo") -> dict:
    rng = np.random.default_rng(seed)
    pedidos = _gerar_pedidos(rng)

    # Clientes: peso estilo "cliente fiel"; 60% existiam antes de maio.
    pesos_cli = rng.pareto(1.6, N_CLIENTES) + 1
    pesos_cli /= pesos_cli.sum()
    veterano = rng.random(N_CLIENTES) < 0.60
    primeiro_pedido: dict[int, datetime] = {}
    for p in pedidos:
        p.cliente_idx = int(rng.choice(N_CLIENTES, p=pesos_cli))
        primeiro_pedido.setdefault(p.cliente_idx, p.criado_em)

    avaliacoes = _gerar_avaliacoes(rng, pedidos)
    _plantar_injecoes(rng, avaliacoes)

    # Cadastro de clientes (só quem pediu).
    clientes: dict[int, dict] = {}
    for idx, primeiro in sorted(primeiro_pedido.items()):
        criado = (datetime.combine(INICIO, datetime.min.time()) - timedelta(days=int(rng.integers(30, 400)), hours=int(rng.integers(0, 24)))
                  if veterano[idx] else primeiro - timedelta(minutes=int(rng.integers(1, 120))))
        clientes[idx] = _novo_cliente(rng, criado)
    id_cliente = {idx: n for n, idx in enumerate(sorted(clientes), start=1)}

    # P3: ataque coordenado (cada conta falsa posta 1-2 avaliações, em contas criadas dias antes)
    proximo_idx = max(clientes) + 1
    proximo_pedido = len(pedidos) + 1
    inicio_ataque = datetime.combine(ATAQUE_DIAS[0], datetime.min.time())
    for conta in range(proximo_idx, proximo_idx + N_FALSAS // 2 + 1):
        clientes[conta] = _novo_cliente(rng, inicio_ataque - timedelta(hours=int(rng.integers(2, 60))))
        id_cliente[conta] = len(id_cliente) + 1
    falsas: list[Avaliacao] = []
    pedidos_falsos: list[Pedido] = []
    dias = list(ATAQUE_DIAS)
    for n in range(N_FALSAS):
        dia = dias[int(rng.choice(len(dias), p=[0.25, 0.45, 0.30]))]
        publicado = datetime(dia.year, dia.month, dia.day, int(rng.integers(9, 24)), int(rng.integers(0, 60)), int(rng.integers(0, 60)))
        conta = proximo_idx + n // 2
        modelo_idx = int(rng.integers(len(frases.FALSAS_BASE)))
        pedido_id = None
        if rng.random() < 0.38:               # parte tem um pedido de fachada, pequeno e recente
            refri = next(i for i, it in enumerate(ITENS) if it.nome == "Refrigerante Lata")
            ped = Pedido(proximo_pedido, conta, publicado - timedelta(hours=1, minutes=int(rng.integers(0, 30))),
                         15.0, 32.0, 2.0, [(refri, 1)], round(ITENS[refri].preco + 5, 2), False)
            pedidos_falsos.append(ped)
            pedido_id = ped.id
            proximo_pedido += 1
        falsas.append(Avaliacao(
            id=0, pedido_id=pedido_id, cliente_idx=conta, criado_em=publicado,
            nota=1 if rng.random() < 0.85 else 2,
            texto=_variar_falsa(rng, frases.FALSAS_BASE[modelo_idx]),
            gabarito={"sentimento": "negativo", "temas": frases.FALSAS_TEMAS[modelo_idx], "pratos": [],
                      "falsa": True, "injecao": False},
        ))
    pedidos_todos = pedidos + pedidos_falsos
    todas = sorted(avaliacoes + falsas, key=lambda a: a.criado_em)
    for n, av in enumerate(todas, start=1):
        av.id = n

    _gravar(caminho_db, pedidos_todos, todas, clientes, id_cliente, salt)
    resumo = _gravar_gabarito(caminho_gabarito, todas, pedidos_todos, seed)
    return resumo


def _novo_cliente(rng: np.random.Generator, criado_em: datetime) -> dict:
    nome = f"{_escolha(rng, NOMES)} {_escolha(rng, SOBRENOMES)}"
    telefone = f"({int(rng.integers(11, 99))}) 9{int(rng.integers(1000, 9999))}-{int(rng.integers(1000, 9999))}"
    endereco = f"{_escolha(rng, RUAS)}, {int(rng.integers(10, 2000))}"
    return {"nome": nome, "telefone": telefone, "endereco": endereco, "criado_em": criado_em}


def _gravar(caminho_db, pedidos, avaliacoes, clientes, id_cliente, salt) -> None:
    caminho = Path(caminho_db)
    if caminho.exists():
        caminho.unlink()
    con = db.conectar(caminho)
    db.criar_schema(con)
    fmt = "%Y-%m-%d %H:%M:%S"
    con.executemany(
        "INSERT INTO cardapio VALUES (?,?,?,?,?,?)",
        [(n, i.nome, i.categoria, i.preco, i.genero, json.dumps(list(i.aliases), ensure_ascii=False))
         for n, i in enumerate(ITENS, start=1)],
    )
    con.executemany(
        "INSERT INTO clientes VALUES (?,?,?,?,?,?)",
        [(id_cliente[idx], _ref(salt, id_cliente[idx]), c["nome"], c["telefone"], c["endereco"], c["criado_em"].strftime(fmt))
         for idx, c in sorted(clientes.items(), key=lambda kv: id_cliente[kv[0]])],
    )
    con.executemany(
        "INSERT INTO pedidos VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(p.id, id_cliente[p.cliente_idx], p.criado_em.strftime(fmt), p.criado_em.weekday(), p.criado_em.hour,
          p.turno, p.preparo, p.entrega, p.dist, p.valor) for p in pedidos],
    )
    con.executemany(
        "INSERT INTO pedido_itens VALUES (?,?,?)",
        [(p.id, i + 1, q) for p in pedidos for i, q in p.itens],
    )
    con.executemany(
        "INSERT INTO avaliacoes VALUES (?,?,?,?,?,?)",
        [(a.id, a.pedido_id, id_cliente[a.cliente_idx], a.criado_em.strftime(fmt), a.nota, a.texto) for a in avaliacoes],
    )
    con.commit()
    con.close()


def descrever_padroes() -> list[dict]:
    return [
        {"id": "P1", "titulo": "Batata frita murcha/fria em entregas longas",
         "regra": "80% dos pedidos com batata e entrega > 40 min têm problema (10% nos demais).",
         "onde_ver": "Análise por prato → Batata Frita"},
        {"id": "P2", "titulo": "Atrasos e comida fria nas sextas à noite",
         "regra": "Sexta, 18h–22h: +16 min de preparo e trânsito; a partir de 01/10/2026 mais +16 min.",
         "onde_ver": "Causa raiz (Etapa 2) e evolução semanal de atraso"},
        {"id": "P3", "titulo": "Ataque de avaliações falsas",
         "regra": f"{N_FALSAS} avaliações de nota 1–2 entre 14 e 16/10/2026, textos quase idênticos, "
                  "contas novas, a maioria sem pedido.",
         "onde_ver": "Detecção de suspeitas (Etapa 4) e queda da nota em outubro"},
        {"id": "P4", "titulo": "Açaí derretido em entregas > 5 km",
         "regra": "90% dos pedidos com açaí e distância > 5 km têm problema (3% nos demais).",
         "onde_ver": "Análise por prato → Açaí 500ml"},
        {"id": "P5", "titulo": "Pratos com poucas avaliações",
         "regra": "Pudim e Salada Caesar quase não são pedidos: aparecem com aviso de baixa confiança.",
         "onde_ver": "Análise por prato"},
        {"id": "P6", "titulo": "Tentativas de prompt injection",
         "regra": "Duas avaliações reais negativas trazem 'ignore as instruções anteriores…'.",
         "onde_ver": "Painel de segurança; testes de injeção"},
    ]


def _gravar_gabarito(caminho, avaliacoes, pedidos, seed) -> dict:
    por_id = {a.id: {**a.gabarito, "nota": a.nota} for a in avaliacoes}
    resumo = {
        "restaurante": NOME_RESTAURANTE,
        "seed": seed,
        "periodo": [INICIO.isoformat(), FIM.isoformat()],
        "pedidos": len(pedidos),
        "avaliacoes": len(avaliacoes),
        "avaliacoes_falsas": sum(1 for a in avaliacoes if a.gabarito["falsa"]),
        "avaliacoes_com_injecao": [a.id for a in avaliacoes if a.gabarito["injecao"]],
        "ataque_dias": [d.isoformat() for d in ATAQUE_DIAS],
    }
    Path(caminho).write_text(
        json.dumps({"resumo": resumo, "padroes": descrever_padroes(), "avaliacoes": por_id},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return resumo
