"""Agentes de perguntas: o modo offline (regras) e o modo com Claude, os dois só com as ferramentas de consulta.

Garantias do desenho:
- o agente nunca vê o banco: só chama ferramentas de leitura com parâmetros validados;
- os números do texto final são checados contra os resultados das ferramentas (`verificar_numeros`);
- quando os dados não permitem responder, a resposta diz isso, com o motivo;
- o gráfico vem de uma ferramenta, nunca é inventado pelo modelo.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

from copiloto import config
from copiloto.llm import limite
from copiloto.qa import textos
from copiloto.qa.ferramentas import FERRAMENTAS, Contexto, ErroDeFerramenta, Grafico, ResultadoFerramenta
from copiloto.qa.roteador import interpretar

log = logging.getLogger(__name__)

TAMANHO_MAX_PERGUNTA = 500
MAX_ITERACOES = 6


class AgenteIndisponivel(RuntimeError):
    """O Claude não pôde responder (falha de rede, recusa, resposta cortada); a pergunta cai para as regras."""


@dataclass
class UsoFerramenta:
    nome: str
    argumentos: dict
    resultado: ResultadoFerramenta | None = None
    erro: str | None = None


@dataclass
class Resposta:
    texto: str
    usos: list[UsoFerramenta] = field(default_factory=list)
    grafico: Grafico | None = None
    origem: str = "regras"                       # "regras" | "claude"
    modelo: str = ""
    sem_dados: bool = False
    numeros_nao_verificados: list[str] = field(default_factory=list)
    aviso: str = ""


# --- Checagem dos números -----------------------------------------------------------------------
_DATA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
_ANO = re.compile(r"\b20\d{2}\b")
_MARCADOR_DE_LISTA = re.compile(r"(?m)^\s*\d+[.)]\s")
_NUMERO = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?")


def _numeros_do_texto(texto: str) -> list[tuple[float, int, str]]:
    """(valor, casas decimais, como apareceu) de cada número do texto, sem datas, anos e marcadores de lista."""
    for padrao in (_MARCADOR_DE_LISTA, _DATA, _ANO):
        texto = padrao.sub(" ", texto)
    achados = []
    for bruto in _NUMERO.findall(texto):
        limpo = bruto.replace(".", "").replace(",", ".") if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", bruto) else bruto.replace(",", ".")
        achados.append((float(limpo), len(limpo.split(".")[1]) if "." in limpo else 0, bruto))
    return achados


def _numeros_dos_dados(valor: Any) -> list[float]:
    if isinstance(valor, bool) or valor is None:
        return []
    if isinstance(valor, (int, float)):
        return [float(valor)]
    if isinstance(valor, str):
        return [v for v, _, _ in _numeros_do_texto(valor)]
    if isinstance(valor, dict):
        return [n for v in valor.values() for n in _numeros_dos_dados(v)]
    if isinstance(valor, (list, tuple)):
        return [n for v in valor for n in _numeros_dos_dados(v)]
    return []


def verificar_numeros(texto: str, usos: list[UsoFerramenta]) -> list[str]:
    """Números do texto que não aparecem (com o mesmo arredondamento) nos resultados das ferramentas.

    Ignora datas, anos, marcadores de lista e inteiros de 0 a 5 (a escala das notas).
    """
    permitidos = [n for u in usos if u.resultado for n in _numeros_dos_dados(u.resultado.dados)]
    faltando = []
    for valor, casas, bruto in _numeros_do_texto(texto):
        if casas == 0 and valor <= 5:
            continue
        tolerancia = 0.5 * 10 ** -casas + 1e-9
        if not any(abs(p - valor) <= tolerancia for p in permitidos):
            faltando.append(bruto)
    return faltando


def _grafico_dos_usos(usos: list[UsoFerramenta]) -> Grafico | None:
    return next((u.resultado.grafico for u in usos if u.resultado and u.resultado.grafico), None)


def _executar(ctx: Contexto, nome: str, argumentos: Any) -> UsoFerramenta:
    uso = UsoFerramenta(nome, argumentos if isinstance(argumentos, dict) else {})
    try:
        if nome not in FERRAMENTAS:
            raise ErroDeFerramenta(f"ferramenta desconhecida: {nome}")
        uso.resultado = FERRAMENTAS[nome].executar(ctx, argumentos)
    except ErroDeFerramenta as erro:
        uso.erro = str(erro)
    return uso


def _validar_pergunta(pergunta: str) -> str:
    pergunta = pergunta.strip()
    if not pergunta:
        raise ValueError("a pergunta está vazia")
    if len(pergunta) > TAMANHO_MAX_PERGUNTA:
        raise ValueError(f"a pergunta passa de {TAMANHO_MAX_PERGUNTA} caracteres")
    return pergunta


# --- Modo offline ---------------------------------------------------------------------------------
class AgenteRegras:
    origem = "regras"
    modelo = "roteador por palavras"

    def perguntar(self, pergunta: str, ctx: Contexto) -> Resposta:
        interpretacao = interpretar(_validar_pergunta(pergunta), ctx)
        base = {"origem": self.origem, "modelo": self.modelo}
        if interpretacao.fora_do_escopo:
            return Resposta(
                "Não tenho dados sobre isso. O que existe aqui são as avaliações e os pedidos (dia, horário, tempos "
                "de preparo e entrega, distância e itens), não informações financeiras ou de outras áreas.",
                sem_dados=True, **base)
        if interpretacao.sem_dados:
            return Resposta(textos.sem_dados(interpretacao.sem_dados), sem_dados=True, **base)
        if not interpretacao.chamadas:
            exemplos = "\n".join(f"- {e}" for e in textos.EXEMPLOS)
            return Resposta(
                "Não entendi a pergunta no modo offline, que só reconhece alguns tipos de pergunta. Experimente, por "
                f"exemplo:\n{exemplos}\n\nPerguntas livres funcionam com a chave do Claude configurada.",
                sem_dados=True, **base)
        usos = [_executar(ctx, c.ferramenta, c.argumentos) for c in interpretacao.chamadas]
        partes, sem_dados = [], False
        for uso in usos:
            if uso.erro:
                partes.append(textos.sem_dados(uso.erro))
                sem_dados = True
            elif uso.resultado.sem_dados:
                partes.append(textos.sem_dados(uso.resultado.motivo))
                sem_dados = True
            else:
                partes.append(textos.COMPOSITORES[uso.nome](uso.resultado))
        return Resposta("\n\n".join(partes), usos, _grafico_dos_usos(usos), sem_dados=sem_dados, **base)


# --- Modo Claude ----------------------------------------------------------------------------------
def montar_system(ctx: Contexto) -> str:
    inicio, fim = ctx.periodo
    return f"""Você responde perguntas do dono de um restaurante de delivery sobre as avaliações dos clientes e os pedidos, \
em português do Brasil, de forma clara e curta (no máximo uns 180 palavras).

Dados disponíveis: avaliações e pedidos de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (a última avaliação é de {fim:%d/%m/%Y}; \
"este mês" é {fim:%m/%Y}). Filtro de suspeitas em uso: {ctx.base}.

Regras:
- Consulte SEMPRE as ferramentas antes de responder. Use só números que vieram delas; nunca calcule, estime ou invente \
um número. Se precisar de um valor que nenhuma ferramenta entrega, diga que não tem.
- Mostre os números usados, sempre com a base (por exemplo, "58% de 102 avaliações") e diga quando houver baixa confiança.
- Se as ferramentas indicarem que não há dados, ou se a pergunta for sobre algo que os dados não cobrem (faturamento, \
concorrentes, períodos fora do intervalo), diga isso com clareza e não responda por suposição.
- Quando houver avaliações suspeitas, diga qual é o efeito delas. Padrões encontrados são coincidências no tempo, não \
prova de causa; sugestões são hipóteses a testar.
- Não cite nomes de ferramentas nem detalhes técnicos. Use markdown simples (negrito e listas), sem títulos."""


class AgenteClaude:
    origem = "claude"

    def __init__(self, modelo: str, client: anthropic.Anthropic | None = None, api_key: str | None = None,
                 ao_chamar=None) -> None:
        self.modelo = modelo
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._ao_chamar = ao_chamar or (lambda: None)
        self.chamadas = 0

    def perguntar(self, pergunta: str, ctx: Contexto) -> Resposta:
        mensagens: list[dict] = [{"role": "user", "content": _validar_pergunta(pergunta)}]
        ferramentas = [f.schema() for f in FERRAMENTAS.values()]
        system = montar_system(ctx)
        usos: list[UsoFerramenta] = []
        reescreveu = False
        for _ in range(MAX_ITERACOES):
            resposta = self._chamar(system, ferramentas, mensagens)
            mensagens.append({"role": "assistant", "content": resposta.content})
            if resposta.stop_reason == "tool_use":
                blocos = []
                for bloco in resposta.content:
                    if bloco.type != "tool_use":
                        continue
                    uso = _executar(ctx, bloco.name, bloco.input)
                    usos.append(uso)
                    conteudo = uso.resultado.para_modelo() if uso.resultado else f"Erro: {uso.erro}"
                    blocos.append({"type": "tool_result", "tool_use_id": bloco.id, "content": conteudo,
                                   **({"is_error": True} if uso.erro else {})})
                mensagens.append({"role": "user", "content": blocos})
                continue
            if resposta.stop_reason in ("refusal", "max_tokens"):
                raise AgenteIndisponivel(f"resposta interrompida ({resposta.stop_reason})")
            texto = "".join(b.text for b in resposta.content if b.type == "text").strip()
            if not texto:
                raise AgenteIndisponivel("resposta vazia")
            faltando = verificar_numeros(texto, usos)
            if faltando and not reescreveu:
                reescreveu = True
                mensagens.append({"role": "user", "content": (
                    f"Os números {', '.join(faltando)} do seu texto não aparecem nos resultados das consultas. "
                    "Reescreva a resposta usando apenas números que vieram das consultas, ou consulte as ferramentas.")})
                continue
            return Resposta(
                texto + (f"\n\n⚠️ Confira: os números {', '.join(faltando)} não vieram diretamente das consultas." if faltando else ""),
                usos, _grafico_dos_usos(usos), origem=self.origem, modelo=self.modelo,
                sem_dados=bool(usos) and all(u.erro or (u.resultado and u.resultado.sem_dados) for u in usos),
                numeros_nao_verificados=faltando)
        raise AgenteIndisponivel("o agente não chegou a uma resposta no limite de consultas")

    def _chamar(self, system: str, ferramentas: list[dict], mensagens: list[dict]):
        try:
            self.chamadas += 1
            self._ao_chamar()
            return self._client.messages.create(
                model=self.modelo, max_tokens=4000, system=system, tools=ferramentas, messages=mensagens,
                output_config={"effort": "medium"},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as erro:
            raise AgenteIndisponivel(str(erro)) from erro


# --- Escolha do agente ----------------------------------------------------------------------------
def responder(pergunta: str, ctx: Contexto, cfg: config.Config | None = None, client: Any = None) -> Resposta:
    """Claude se houver chave e o limite diário permitir; senão (ou se falhar) o modo offline."""
    cfg = cfg or config.carregar()
    aviso = ""
    if cfg.anthropic_api_key or client is not None:
        if limite.pode_usar(ctx.con, cfg.limite_diario_llm):
            agente = AgenteClaude(cfg.modelo_geracao, client=client, api_key=cfg.anthropic_api_key,
                                  ao_chamar=lambda: limite.registrar(ctx.con))
            try:
                return agente.perguntar(pergunta, ctx)
            except AgenteIndisponivel as erro:
                log.warning("Claude indisponível: %s", erro)
                aviso = "O Claude não pôde responder agora; esta resposta veio do modo offline."
        else:
            aviso = "O limite diário de chamadas ao Claude foi atingido; esta resposta veio do modo offline."
    resposta = AgenteRegras().perguntar(pergunta, ctx)
    resposta.aviso = aviso
    return resposta
