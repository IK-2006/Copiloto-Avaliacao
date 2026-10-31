# Copiloto de Avaliações para Restaurantes

Ferramenta com IA que ajuda donos de restaurantes de delivery a entender **por que** os clientes
reclamam, **o que resolver primeiro** e **como melhorar os pratos**, e que protege o restaurante
de avaliações falsas.

> Todos os dados são **fictícios**: o restaurante "Cantina Sabor da Vila" foi inventado, com cardápio
> de 19 itens, cerca de 3.000 pedidos (mai–out/2026) e 654 avaliações, geradas com padrões plantados
> para a ferramenta descobrir.

## Estado do projeto

| Etapa | Conteúdo | Situação |
|---|---|---|
| 1 | Dados fictícios, classificação, análise por prato, dashboard básico | **pronta** |
| 2 | Causa raiz cruzando avaliações e dados dos pedidos | a fazer |
| 3 | Plano de ação priorizado e sugestões de melhoria dos pratos | a fazer |
| 4 | Detecção de avaliações suspeitas (métricas com e sem elas) | a fazer |
| 5 | Respostas sugeridas com aprovação e perguntas em linguagem natural | a fazer |
| 6 | Resumo semanal no n8n e deploy online | a fazer |

## Como rodar

Requer Python 3.11 ou mais novo (testado em 3.14).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt      # Linux/macOS: .venv/bin/python

.venv/Scripts/python -m copiloto.datagen                         # gera data/restaurante.db e data/plantados.json
.venv/Scripts/python -m copiloto.classify                        # classifica as avaliações (usa cache)
.venv/Scripts/streamlit run app/streamlit_app.py                 # dashboard em http://localhost:8501
.venv/Scripts/python -m pytest                                   # testes
```

O repositório já inclui `data/restaurante.db` classificado, então basta abrir o dashboard.

### Com ou sem chave da Anthropic

O app tem dois provedores de IA intercambiáveis:

- **Regras** (padrão, offline): léxico de palavras para sentimento, temas e pratos. Não precisa de chave.
- **Claude**: ativado automaticamente quando `ANTHROPIC_API_KEY` está definida (copie `.env.example`
  para `.env`). Usa Haiku 5.5 para classificar. Para reclassificar tudo com o Claude:
  `python -m copiloto.classify --provedor claude --forcar`.

> O caminho do Claude está implementado e coberto por testes com um cliente simulado, mas ainda
> **não foi executado contra a API real**, por falta de chave durante o desenvolvimento.

## Como funciona

```
gerador de dados (seed fixa) ─► SQLite (pedidos, avaliações, clientes, cardápio)
                                     │
        ┌────────────────────────────┴──────────────────────────┐
        ▼                                                       ▼
 camada de IA (Claude | Regras)                      análises em pandas
 anonimiza → classifica → cache                      todo percentual sai daqui, com n
        └────────────────────────┬──────────────────────────────┘
                                 ▼
                       dashboard Streamlit
```

- **Números só do código.** `copiloto/stats.py` devolve cada percentual com sua base (`65% de 120
  avaliações`) e marca **baixa confiança** abaixo de 20 avaliações. A IA nunca calcula percentuais.
- **Análise por prato.** A base de cada prato é o conjunto de avaliações que o citam. Isso mede o que se
  diz do prato quando ele é lembrado, não a taxa de falha em todos os pedidos; por isso a tabela traz
  também quantos pedidos incluíram o prato. Citações a pratos fora do pedido são descartadas.
- **Cache.** Cada classificação é guardada com uma impressão digital do que foi enviado, do provedor e
  da versão. Visitar o dashboard nunca gera chamadas à IA.

## Padrões plantados nos dados

Descritos também em `data/plantados.json`, que traz o gabarito de cada avaliação (usado só por testes).

| # | Padrão | Onde ver |
|---|---|---|
| P1 | Batata frita murcha ou fria em entregas acima de 40 min (80% dos pedidos, contra 10% nos demais) | Análise por prato |
| P2 | Sextas à noite com +16 min de preparo e trânsito, e outros +16 min a partir de 01/10 | Etapa 2 |
| P3 | Ataque de 46 avaliações falsas de 14 a 16/10: nota 1–2, textos quase idênticos, contas novas | Queda da nota na semana de 12/10; Etapa 4 |
| P4 | Açaí derretido em entregas acima de 5 km | Análise por prato |
| P5 | Pudim e Salada Caesar quase não aparecem nas avaliações | Aviso de baixa confiança |
| P6 | Duas avaliações reais com "ignore as instruções anteriores…" | Aba Segurança |

Na versão atual a ferramenta já encontra P1, P4 e P5 (aba **Análise por prato**), mostra o efeito de P3 na
nota semanal e sinaliza P6. Batata Frita lidera o ranking com **58% de 102 avaliações** relatando problema
(o gabarito, escrito pelo gerador, tem 62%; a diferença é o que o classificador de regras não reconhece).

## Qualidade do classificador

Medida contra o gabarito (`python -m copiloto.validacao`), provedor **Regras**:

| Métrica | Resultado |
|---|---|
| Acurácia do sentimento | 90,5% |
| Temas (precisão / revocação / F1) | 1,00 / 0,90 / 0,95 |
| Pratos mencionados (F1) | 1,00 |
| Problema por prato (precisão / revocação / F1) | 1,00 / 0,90 / 0,95 |

**Leia com cautela:** as avaliações e o léxico do classificador foram escritos pela mesma pessoa, então a
precisão perfeita é otimista. Uma parte dos problemas foi escrita com expressões fora do léxico
("parecia que a comida tinha saído da geladeira") justamente para que a revocação não seja 100%: cerca
de 10% dos temas passam despercebidos. Em avaliações reais os números seriam menores.

## Segurança e privacidade

- **Dados pessoais não vão para a IA.** Nome, telefone e endereço ficam só na tabela `clientes`. A IA recebe
  um identificador anônimo, o texto da avaliação com e-mail, telefone, CPF, CEP e o nome e endereço do
  próprio cliente mascarados, e os nomes dos itens do pedido. Um teste captura tudo que seria enviado ao
  modelo e confirma que nenhum dado cadastral aparece.
- **Texto de avaliação é dado, nunca instrução.** O texto vai dentro de JSON delimitado por tags, com `<` e
  `>` neutralizados; o prompt de sistema manda ignorar ordens vindas de avaliações; e, sobretudo, a
  resposta do modelo só é aceita se vier em listas fechadas (sentimento, temas, pratos). Um modelo que
  obedeça à injeção e devolva texto livre é rejeitado, e nada disso chega ao banco. Tentativas
  conhecidas são detectadas e sinalizadas. É defesa em camadas, não garantia absoluta.
- **Segredos só em variáveis de ambiente.** `.env` está no `.gitignore`; `.env.example` mostra as chaves.

## Estrutura

```
copiloto/
  datagen/      gerador de dados fictícios e padrões plantados
  llm/          contrato, provedores (Regras, Claude), anonimização e detecção de injeção
  analytics/    base analítica, análise por prato, séries temporais
  classify.py   pipeline de classificação com cache
  validacao.py  compara a classificação com o gabarito
  stats.py      percentuais com base e aviso de baixa confiança
app/            dashboard Streamlit
tests/          testes automatizados
data/           banco SQLite e gabarito (fictícios)
```
