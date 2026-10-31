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
| 2 | Causa raiz cruzando avaliações e dados dos pedidos; alertas de tendência | **pronta** |
| 3 | Plano de ação priorizado pelo impacto na nota e sugestões de melhoria dos pratos | **pronta** |
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
| P2 | Sextas à noite com +16 min de preparo e trânsito, e outros +16 min a partir de 01/10 | Aba Causa raiz |
| P3 | Ataque de 46 avaliações falsas de 14 a 16/10: nota 1–2, textos quase idênticos, contas novas | Queda da nota na semana de 12/10; alerta de tendência; Etapa 4 |
| P4 | Açaí derretido em entregas acima de 5 km | Análise por prato; Causa raiz por prato |
| P5 | Pudim e Salada Caesar quase não aparecem nas avaliações | Aviso de baixa confiança |
| P6 | Duas avaliações reais com "ignore as instruções anteriores…" | Aba Segurança |

### O que a ferramenta já encontra

| Padrão | Resultado (calculado em código, sem a IA) |
|---|---|
| P1 | Batata Frita lidera o ranking de pratos: **58% de 102 avaliações** relatam problema (o gabarito tem 62%; a diferença é o que o classificador de regras não reconhece). 73% das reclamações da batata (43 de 59) vêm de pedidos com entrega acima de 40 min, que são 28% dos pedidos: 66% das avaliações desse grupo citam problema, contra 14% nos demais |
| P2 | **66% das reclamações de comida fria (61 de 92) vêm de pedidos de sexta à noite, que são 13% dos pedidos**: nesse grupo, 60% das avaliações citam o problema, contra 6% nos demais (10× mais). Para atraso, 52% (43 de 82). 40% das entregas acima de 40 min vêm da sexta à noite, e o tempo médio de entrega nesse horário salta de cerca de 48 min (mai–set) para cerca de 63 min em outubro, enquanto o resto fica estável |
| P3 | A nota semanal cai para cerca de 1,9 na semana do ataque; o alerta de tendência acusa "reclamações de atendimento subiram 347%", porque as falsas dizem "atendimento péssimo" (sem elas, o alerta some) |
| P4 | 73% das reclamações do açaí (11 de 15) vêm de pedidos a mais de 5 km, com aviso de baixa confiança (só 16 avaliações no grupo) |
| P5, P6 | Aviso de baixa confiança e aba Segurança |

Sabor, embalagem, quantidade e pedido errado **não** recebem causa raiz: os dados não mostram concentração
e a ferramenta não inventa uma.

## Como funciona a causa raiz

`copiloto/analytics/causa_raiz.py` testa todas as combinações de até três condições do pedido (dia da
semana, turno, entrega acima de 30/40/50 min, preparo acima de 22/28 min, distância acima de 3/5 km) e
responde a três perguntas, sempre com `k de n` e baixa confiança quando n < 20:

1. **Qual condição do pedido?** Em geral aponta o mecanismo, como "entrega acima de 40 min".
2. **Quando e onde?** Mesma busca só com dia, turno e distância, para chegar a "sexta-feira, à noite".
3. **Por que as entregas demoram?** Mesma busca sobre todos os pedidos (não só os avaliados), com o
   tempo de preparo e de deslocamento dentro e fora do segmento.

Cada padrão traz a parcela das reclamações que ele concentra, a fatia dos pedidos que ele ocupa, a taxa do
problema dentro e fora do segmento e quantas vezes ela é maior. Para que o acaso não vire padrão:

- teste exato de Fisher com **correção de Bonferroni** pelo número de segmentos testados. Em 40 sorteios
  sem relação nenhuma com os pedidos, a ferramenta acusou padrão em 1; sem a correção, em 39
  (`tests/test_causa_raiz.py`);
- exigências mínimas de amostra (12 reclamações no total, 6 e 10 avaliações no segmento) e de efeito
  (pelo menos 1,5× mais frequente);
- os candidatos são ordenados por cobertura x precisão, e os que só repetem outro já escolhido somem.

**Limite importante:** quem avalia não é uma amostra aleatória dos clientes (quem teve problema costuma
avaliar mais). As taxas descrevem as avaliações, não todos os pedidos, e o padrão aponta onde procurar a
causa, não prova que ela é a causa.

Os **alertas de tendência** comparam os últimos 28 dias com o período anterior e só disparam com pelo menos
6 reclamações recentes, aumento de 40% ou mais e teste de Fisher abaixo de 5%.

## Plano de ação e impacto na nota

A aba **Plano de ação** lista o que resolver primeiro, em ordem de efeito estimado na nota média
(`copiloto/analytics/impacto.py`). Nos dados fictícios, sobre as 630 avaliações de pedidos (nota média de
hoje: 3,79):

| Prioridade | Ação | Nota (cenário completo) | Ganho conservador |
|---|---|---|---|
| 1 | Resolver atrasos, comida fria e comida murcha em pedidos de sexta-feira, à noite (79 avaliações) | 3,79 → 4,00 | +0,10 |
| 2 | Resolver atrasos (demais casos) | 4,00 → 4,07 | +0,04 |
| 3 | Melhorar Batata Frita | 4,07 → 4,14 | +0,03 |
| … | pedidos errados, atendimento, açaí, sabor, embalagem (todos com baixa confiança) | até 4,29 | |

Com o plano inteiro, a nota iria de 3,79 para **4,29 no cenário completo** e **4,04 no conservador**.

**Como a conta é feita:**

1. Quem não reclama de nada dá, em média, nota 4,28: essa é a referência de "experiência boa".
2. Cada reclamação (avaliação, tema) é uma unidade que uma ação pode resolver. Resolvê-la é supor que a
   avaliação passaria a valer a nota de referência. Se a avaliação cita vários problemas, a distância até
   a referência é dividida entre eles, e avaliações que já estão acima da referência não mudam.
3. As ações entram de forma gulosa: a próxima é a que mais eleva a média **dado o que as anteriores já
   resolveram**, para não contar a mesma avaliação duas vezes. A soma dos ganhos bate com um recálculo
   independente da média (`tests/test_impacto.py`).
4. O **cenário conservador** supõe só metade do ganho, porque nem todo cliente volta a dar a nota de quem
   nunca reclamou.

As ações vêm da causa raiz (temas que compartilham o mesmo dia e horário viram uma ação só), dos pratos com
problemas citados e do que sobra de cada tema. Uma ação só entra se resolver pelo menos 6 reclamações novas
e elevar a nota em pelo menos 0,005; as de menos de 20 avaliações aparecem com aviso de baixa confiança.

**É uma estimativa, não uma previsão.** Supõe que quem reclamou de X avaliaria como quem não reclama de nada
se X sumisse e que o resto fica igual. Não mede o efeito de nenhuma medida específica. Hoje o cálculo inclui
as avaliações do ataque (P3) que têm pedido; sem as falsas, a nota de hoje e a referência são mais altas, e a
Etapa 4 permitirá tirar as suspeitas do cálculo.

### Sugestões de melhoria

Cada ação traz sugestões **a avaliar**, com o motivo e o indicador para saber se funcionou. Para a batata
murcha, por exemplo: embalagem com furos de ventilação, molho e sal à parte, ajuste do tempo de fritura. Elas
vêm de um **catálogo escrito à mão** (`copiloto/sugestoes.py`), escolhido por regra conforme o tema, o prato e
as condições do segmento (pico, distância). Não há IA nesse passo e nada disso é garantia de resultado.

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
  analytics/    base analítica, análise por prato, séries temporais, causa raiz, alertas de tendência
  classify.py   pipeline de classificação com cache
  validacao.py  compara a classificação com o gabarito
  stats.py      percentuais com base e aviso de baixa confiança
app/            dashboard Streamlit
tests/          testes automatizados
data/           banco SQLite e gabarito (fictícios)
```
