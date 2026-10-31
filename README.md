# Copiloto de Avaliações para Restaurantes

Ferramenta com IA que ajuda donos de restaurantes de delivery a entender **por que** os clientes
reclamam, **o que resolver primeiro** e **como melhorar os pratos**, e que protege o restaurante
de avaliações falsas.

> Todos os dados são **fictícios**: o restaurante "Cantina Sabor da Vila" foi inventado, com cardápio
> de 19 itens, cerca de 3.000 pedidos (mai–out/2026) e 654 avaliações, geradas com padrões plantados
> para a ferramenta descobrir.

## O problema e a solução

Um restaurante de delivery recebe centenas de avaliações por mês. O dono não tem tempo de ler todas e, mesmo
lendo, não consegue ligar as reclamações às causas reais (horário, tempo de entrega, prato específico) nem separar
o que é falso do que é real.

O Copiloto transforma avaliações em decisões priorizadas: classifica cada avaliação, cruza com os dados do
pedido para achar **onde** os problemas se concentram, estima **quanto cada correção valeria na nota**, sinaliza
**avaliações suspeitas**, sugere respostas (que o dono aprova) e responde perguntas em português. A regra que
guia tudo: **todo número é calculado em código** (a IA classifica e escreve, mas nunca calcula), sempre com a
base (`58% de 102 avaliações`) e com aviso de baixa confiança quando a amostra é pequena.

## O que o projeto faz

| Funcionalidade | Onde | Em uma frase |
|---|---|---|
| Classificação | `copiloto/classify.py` | sentimento, temas e pratos de cada avaliação, com cache |
| Análise por prato | aba Análise por prato | quais problemas cada item do cardápio mais gera |
| Causa raiz | aba Causa raiz | em que dia, horário, tempo e distância cada problema se concentra |
| Plano de ação | aba Plano de ação | o que resolver primeiro, pelo efeito estimado na nota, com sugestões a avaliar |
| Avaliações suspeitas | aba Suspeitas | sinais, nível e motivo de cada alerta; métricas com e sem as suspeitas |
| Respostas sugeridas | aba Respostas | rascunhos que o dono edita e aprova; nada é publicado |
| Perguntas em português | aba Pergunte aos dados | respostas só com consultas em código, com os números usados e gráfico |
| Resumo semanal | `n8n/`, `api/` | toda segunda, por e-mail, os três pontos que mais precisam de atenção |

Há um roteiro para gravar uma demonstração de 2 minutos em [`docs/roteiro-video.md`](docs/roteiro-video.md).

## Arquitetura

```
gerador de dados (seed fixa) ─► SQLite (pedidos, avaliações, clientes, cardápio, rascunhos)
                                     │
        ┌────────────────────────────┴──────────────────────────┐
        ▼                                                       ▼
 camada de IA (Claude | Regras)                      análises em pandas
 anonimiza → classifica → cache                      todo número sai daqui, com a base n
 rascunhos de resposta, perguntas                    causa raiz, plano, suspeitas, resumo
        └────────────────────────┬──────────────────────────────┘
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       dashboard Streamlit            API FastAPI /weekly-summary ◄─ n8n (segunda, 8h) ─► e-mail
```

- **Funciona sem chave.** O provedor **Regras** (léxico, modelos de frase, roteador de perguntas) roda offline e
  é o padrão. Com `ANTHROPIC_API_KEY`, o **Claude** assume classificação, rascunhos e perguntas livres, e
  qualquer falha ou o limite diário devolvem o app ao modo offline.
- **Números só do código.** `copiloto/stats.py` devolve cada percentual com sua base e marca **baixa confiança**
  abaixo de 20 avaliações. A IA nunca calcula percentuais, e as respostas do modo Claude têm os números
  conferidos contra as consultas.
- **Análise por prato.** A base de cada prato é o conjunto de avaliações que o citam. Isso mede o que se
  diz do prato quando ele é lembrado, não a taxa de falha em todos os pedidos; por isso a tabela traz
  também quantos pedidos incluíram o prato. Citações a pratos fora do pedido são descartadas.
- **Cache.** Cada classificação é guardada com uma impressão digital do que foi enviado, do provedor e
  da versão. Visitar o dashboard nunca gera chamadas à IA.

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
`requirements-lock.txt` traz as versões exatas com que os testes passaram.

### Com ou sem chave da Anthropic

- **Sem chave** (padrão): tudo funciona no modo offline.
- **Com chave:** copie `.env.example` para `.env` e preencha `ANTHROPIC_API_KEY`. Classificação com Haiku 5.5; rascunhos
  e perguntas com Sonnet 5.5, com limite diário (`COPILOTO_LIMITE_DIARIO_LLM`). Para reclassificar tudo com o
  Claude: `python -m copiloto.classify --provedor claude --forcar`. Para conferir a chave e os três usos do Claude
  (classificação, rascunho de resposta e perguntas) antes de usar o app: `python scripts/check_claude.py`
  (cerca de 10 chamadas pequenas, sem gravar nada no banco).

> O caminho do Claude está implementado e coberto por testes com um cliente simulado, mas ainda
> **não foi executado contra a API real**, por falta de chave durante o desenvolvimento.

## Padrões plantados nos dados

Descritos também em `data/plantados.json`, que traz o gabarito de cada avaliação (usado só por testes).

| # | Padrão | Onde ver |
|---|---|---|
| P1 | Batata frita murcha ou fria em entregas acima de 40 min (80% dos pedidos, contra 10% nos demais) | Análise por prato |
| P2 | Sextas à noite com +16 min de preparo e trânsito, e outros +16 min a partir de 01/10 | Aba Causa raiz |
| P3 | Ataque de 46 avaliações falsas de 14 a 16/10: nota 1–2, textos quase idênticos, contas novas | Aba Suspeitas; queda da nota na semana de 12/10; alerta de tendência |
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
se X sumisse e que o resto fica igual. Não mede o efeito de nenhuma medida específica. A tabela acima inclui
as avaliações do ataque (P3) que têm pedido. Com o filtro **"Excluir suspeitas médias e altas"** da barra
lateral, o plano é recalculado: a nota de hoje sobe de 3,79 para **3,88**, a referência de 4,28 para 4,41 e o
cenário completo chega a 4,41 (conservador: 4,14). A ordem das três primeiras ações não muda (a primeira vai
de 3,88 para 4,11).

### Sugestões de melhoria

Cada ação traz sugestões **a avaliar**, com o motivo e o indicador para saber se funcionou. Para a batata
murcha, por exemplo: embalagem com furos de ventilação, molho e sal à parte, ajuste do tempo de fritura. Elas
vêm de um **catálogo escrito à mão** (`copiloto/sugestoes.py`), escolhido por regra conforme o tema, o prato e
as condições do segmento (pico, distância). Não há IA nesse passo e nada disso é garantia de resultado.

## Avaliações suspeitas

A aba **Suspeitas** (`copiloto/analytics/suspeitas.py`) **só sinaliza**: nada é apagado, ocultado nem
contestado, e a decisão de contestar na plataforma é do dono. Cada avaliação soma pontos por sinal e recebe
um nível e os motivos em linguagem simples.

| Sinal | Pontos | Como é medido |
|---|---|---|
| Sem pedido correspondente | 2 | a avaliação não aponta para nenhum pedido |
| Conta nova | 1 | conta criada há menos de 7 dias e com no máximo 1 pedido (cliente novo avaliando o primeiro pedido é normal, por isso pesa pouco) |
| Rajada de notas baixas | 1 | o dia tem muito mais avaliações de nota 1–2 do que o normal (Poisson, p < 0,001, mínimo de 5) |
| Texto muito parecido | 3 | cosseno >= 0,8 sobre trechos de 3 a 5 letras com pelo menos 2 outras avaliações, de 3 contas diferentes, em até 7 dias |

Níveis: 1–2 baixo, 3–4 médio, 5 ou mais alto. Nenhum sinal sozinho passa de "médio": **"alto" exige
combinação**. A aba mostra o episódio detectado, a nota e as avaliações negativas com e sem as suspeitas, um
gráfico das notas 1–2 por dia, a lista com os motivos e um CSV para anexar a uma contestação. A barra
lateral tem o filtro global (incluir todas, excluir médias e altas, excluir só as altas) e o gráfico semanal
da visão geral mostra sempre as duas linhas.

**Resultado nos dados fictícios** (`python -m copiloto.validacao`, contra o gabarito do gerador):

| Nível | Falsas detectadas | Genuínas acusadas | Precisão | Revocação |
|---|---|---|---|---|
| Médio ou alto | 44 de 46 | 1 de 608 | 0,98 | 0,96 |
| Só alto | 40 de 46 | 0 de 608 | 1,00 | 0,87 |

O episódio aparece como "44 avaliações suspeitas de 14/10 a 16/10, com nota média 1,0. Dessas, 24 (55%) não
têm pedido, 40 (91%) vêm de contas novas e 44 (100%) têm texto parecido com o de outras". Sem as suspeitas, a
nota média vai de 3,69 para **3,88** e as avaliações negativas de 28% para 23%; o alerta de tendência de
atendimento (ver acima) some. As duas avaliações com injeção de prompt não são confundidas com ataque.

**Os erros e os limites:**

- O falso alarme é um elogio genérico ("Nota 10. Comida deliciosa, chegou antes do prazo.") que três contas
  escreveram igual em poucos dias: parece cópia e pode ser coincidência. Por isso cada alerta traz o motivo.
- As 2 falsas perdidas são cópias curtas ("Comida com cabelo e muito suja…") com uma palavra trocada que
  só aparece nas duas ("humilhação"): cada uma tem apenas 1 texto parecido, e o sinal exige pelo menos 2.
  Ainda assim recebem 2 pontos (conta nova e rajada).
- Uma rajada isolada de 5 notas baixas em 28/08 também é marcada (1 ponto, nível baixo).
- Os dados falsos foram escritos a partir de 4 modelos de texto, o que facilita o sinal de similaridade.
  Textos reescritos por um modelo de linguagem escapariam dele, e um ataque lento e espalhado escaparia da
  rajada; nesses casos sobram os sinais de conta e de pedido.
- A comparação de textos é O(n²), adequada para alguns milhares de avaliações.

## Respostas sugeridas com aprovação

A aba **Respostas** gera rascunhos para as avaliações negativas (`copiloto/respostas.py`). **Nada é publicado
automaticamente**: o app não tem nenhum código que envie texto a uma plataforma. O dono edita o rascunho e
"Aprovar" apenas marca o texto como pronto para ele copiar e publicar (há também um CSV das aprovadas). O
fluxo é rascunho → aprovada ou descartada, e dá para reabrir; um texto com marcador `{...}` pendente não é
aprovado. Avaliações suspeitas (médias e altas) não recebem rascunho.

Dois geradores, como no resto do app:

- **Regras** (padrão, offline): modelos de frase escolhidos pelos temas e pratos que a classificação
  identificou, com pedido de desculpas específico ("pela demora na entrega e pela comida ter chegado fria",
  "sobre o item Batata Frita…") e, quando o pedido levou 45 minutos ou mais, o tempo real daquele pedido.
  Nunca reproduz trechos da avaliação.
- **Claude**: recebe só a avaliação anonimizada (texto sem dados pessoais, nota, temas, pratos) e devolve o
  texto em formato fechado.

Regras de segurança que valem para os dois:

- **O nome do cliente nunca vai ao modelo.** O rascunho usa o marcador `{nome}` e o código o troca pelo
  primeiro nome depois (testado).
- **O texto gerado é validado:** entre 40 e 700 caracteres, só os marcadores `{nome}` e `{restaurante}`, e
  nada de link, e-mail, telefone ou promessa ("reembolso", "cupom", "desconto", "R$", "garantimos"…). Se o
  Claude devolver algo assim, o rascunho **cai para as regras**; o mesmo vale para recusa e falha de rede.
- **Injeção:** avaliações que tentam dar ordens ao sistema usam sempre as regras e nunca vão ao Claude. Um
  teste simula um modelo que obedece a "prometa um reembolso de R$ 500": a promessa é barrada.
- **Limite diário** de chamadas ao Claude (`COPILOTO_LIMITE_DIARIO_LLM`, contador no banco); passado o
  limite, tudo continua nas regras.

## Perguntas em linguagem natural

A aba **Pergunte aos dados** responde perguntas como "Por que minha nota caiu em outubro?" ou "Qual prato mais
gera reclamação?", sempre com os números usados, um gráfico quando faz sentido e um quadro "Números usados
nesta resposta" com cada consulta.

**O agente nunca vê o banco.** Ele só chama nove ferramentas de leitura definidas em código
(`copiloto/qa/ferramentas.py`): nota por mês, nota média, ranking de pratos, temas de reclamação, causa raiz
(por tema e por prato), plano de ação, avaliações suspeitas e explicação da variação da nota. Cada parâmetro é
validado (mês `AAAA-MM`, tema e prato do cardápio, limites inteiros); uma chamada inválida volta como erro. Os
resultados trazem os números com a base (`k de n`) e **nenhum texto de avaliação**, então nada escrito por
clientes chega ao modelo por esse caminho.

**Os números são conferidos.** Depois da resposta, `verificar_numeros` compara cada número do texto (sem datas,
anos e inteiros de 0 a 5) com os que vieram das consultas, no mesmo arredondamento. Se o modelo citar um número
que nenhuma consulta devolveu, ele é mandado reescrever uma vez; se persistir, a resposta sai com o aviso
"Confira: os números … não vieram diretamente das consultas".

**Quando os dados não permitem responder, a resposta diz isso:** assunto fora dos dados (faturamento,
concorrentes), período sem avaliações ("os dados vão de 01/05/2026 a 31/10/2026; não há avaliações em 2025"),
amostra pequena ou tema sem padrão ("nenhuma condição do pedido concentra de forma consistente…").

Os dois modos:

- **Offline (padrão, sem chave):** um roteador por palavras reconhece os tipos de pergunta acima, extrai mês,
  prato e tema, chama as ferramentas e monta o texto em código. Quando não entende, diz isso e mostra exemplos.
  Perguntas livres não funcionam nesse modo.
- **Claude:** com `ANTHROPIC_API_KEY`, o modelo escolhe as ferramentas em um laço de consultas (no máximo 6).
  Se o Claude falhar ou o limite diário acabar, a pergunta cai para o modo offline com um aviso.

**"Por que minha nota caiu em outubro?"** (resposta do modo offline, tudo calculado em código): a nota foi de
3,91 nos meses anteriores para **2,97** (queda de 0,94). Das 156 avaliações do mês, 44 (28%) são suspeitas, com
nota média 1,1; sem elas a nota é 3,72 e a queda cai para 0,19, ou seja, **0,75 ponto vem das suspeitas**. Nenhum
tema de reclamação ficou significativamente mais frequente no mês (o aumento de atraso, +34%, não passa no
teste, então não é afirmado). O tempo de entrega nos pedidos de sexta à noite passou de 48 para 64 min
(+16 min, 84 pedidos), e a resposta fecha dizendo que isso coincide com os 0,19 restantes, "o que não prova que
ela seja a causa".

## Resumo semanal por e-mail (n8n)

Toda **segunda-feira às 8h** um fluxo do n8n busca o resumo na API do projeto e o envia por e-mail. O texto traz
a semana (avaliações, nota média, negativas) e os **três pontos que mais precisam de atenção**, cada um com os
números, uma sugestão a avaliar e o aviso de que sugestões não são garantia (`copiloto/resumo_semanal.py`). Nos
dados fictícios, a primeira semana (25/10 a 31/10) traz:

1. **Possível ataque de avaliações falsas:** 44 avaliações suspeitas de 14/10 a 16/10, com nota média 1,0.
2. **Entregas mais lentas em pedidos de sexta-feira, à noite:** 64 min nas últimas 4 semanas, contra 49 min
   antes (+15 min); resolver isso leva a nota de 3,88 para 4,11 (conservador: +0,11).
3. **Melhorar Batata Frita:** nota de 4,19 para 4,26 se resolvido (conservador: +0,04).

Os pontos seguem uma ordem fixa (ataque recente, queda da nota, temas em alta, piora de entrega e ações do plano);
quando a ação do plano trata do mesmo segmento de um ponto de entrega, os dois viram um só.

- **Sem IA e sem dados pessoais:** o resumo é calculado em código e funciona offline; a API devolve só números
  agregados (testado: nenhum nome, telefone ou endereço de cliente).
- **API** (`api/main.py`): `GET /weekly-summary` devolve `assunto`, `texto`, `html`, métricas e pontos;
  `GET /health` para verificação. Com `COPILOTO_API_TOKEN` definido, exige o cabeçalho `X-API-Token`
  (comparação em tempo constante). Parâmetros: `ate` (último dia da semana) e `modo` (filtro de suspeitas).
- **Workflow** (`n8n/workflow.json`): Schedule Trigger (segunda, 8h, horário de Brasília) → HTTP Request (com
  nova tentativa) → Send Email. Não contém segredos: o token da API e o SMTP são credenciais do n8n.
- **Como subir:** `docker compose up -d` (API e n8n) ou `npx n8n` e `uvicorn` sem Docker. Passo a passo,
  credenciais e um SMTP de teste local em [`n8n/README.md`](n8n/README.md).

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
- **Respostas e perguntas seguem as mesmas regras:** o nome do cliente nunca é enviado, o texto gerado é
  validado e cai para as regras se for inválido, e as ferramentas de consulta devolvem só números (ver as duas
  seções acima).
- **Segredos só em variáveis de ambiente.** `.env` está no `.gitignore`; `.env.example` mostra as chaves.

## Publicar online

O dashboard vai ao **Streamlit Community Cloud** (gratuito) a partir do GitHub, com o banco fictício versionado.
O passo a passo, os *secrets* opcionais (chave do Claude e limite diário) e as limitações do demo público estão em
[`docs/deploy.md`](docs/deploy.md). O último clique exige o login na conta do GitHub.

## Limites e o que não foi verificado

- **Claude real:** o caminho do Claude (classificação, rascunhos e perguntas) está coberto por testes com um
  cliente simulado, mas **nunca rodou contra a API**. `python scripts/check_claude.py` confere os três usos com a
  sua chave.
- **n8n:** o fluxo foi verificado de ponta a ponta com o **n8n 2.45.7**, instalado com `npx` e executado pelo binário do pacote (sem Docker): o workflow
  foi importado com as credenciais de token e de SMTP; uma execução manual passou pelos nós de HTTP e de e-mail;
  e, com o gatilho trocado para "a cada minuto", o agendador do n8n disparou sozinho e o e-mail chegou a um SMTP
  local de teste, com assunto, texto e HTML corretos. **Não esperei uma segunda-feira** para ver o gatilho real
  das 8h (a regra é a do próprio nó: semanal, segunda, 8h, horário de Brasília) e **não testei com um provedor
  SMTP real**. O n8n avisa que rodar fora de contêiner está obsoleto; para uso contínuo, prefira o Docker.
- **Docker:** o `docker-compose.yml` e o `Dockerfile` da API **não foram executados**, porque o Docker não estava
  instalado na máquina de desenvolvimento; os testes só conferem os arquivos (imagem fixa, portas locais,
  variáveis obrigatórias, nenhum segredo).
- **Deploy:** a publicação no Streamlit Community Cloud não foi feita (exige o login no GitHub). O app foi testado
  em Python 3.14; o Cloud usará a versão escolhida nas configurações (recomendada: 3.12).
- **Dados sintéticos:** os padrões foram plantados pelo mesmo autor das ferramentas. A acurácia do classificador de
  regras e a detecção de suspeitas ficam otimistas nesses dados; em avaliações reais os números seriam menores.
  Pendências típicas do mundo real (textos longos, ironia, avaliações reescritas por IA) não estão representadas.
- **Modo offline:** o roteador de perguntas só reconhece alguns tipos de pergunta; perguntas livres exigem o Claude.
- **Estimativas de impacto:** o ganho na nota é um contrafactual simples, não uma previsão nem o efeito de uma
  medida específica. Padrões da causa raiz apontam onde procurar, não provam a causa.
- **Demo público:** não tem login, todos os visitantes veem o mesmo estado, e os rascunhos e o contador de uso
  gravados no banco não persistem entre reinícios do Streamlit Cloud.
- **Escala:** a comparação de textos das suspeitas é O(n²), adequada para alguns milhares de avaliações.

## Estrutura

```
copiloto/
  datagen/        gerador de dados fictícios e padrões plantados
  llm/            contrato, provedores (Regras, Claude), anonimização, detecção de injeção, limite diário
  analytics/      base analítica, análise por prato, séries, causa raiz, plano de ação, suspeitas,
                  alertas de tendência, variação da nota
  qa/             ferramentas de consulta, agente offline (regras) e agente Claude, checagem de números
  respostas.py    rascunhos de resposta, edição e aprovação
  resumo_semanal.py  os três pontos da semana, em texto e HTML
  classify.py     pipeline de classificação com cache
  validacao.py    compara classificação e suspeitas com o gabarito
  stats.py        percentuais com base e aviso de baixa confiança
app/              dashboard Streamlit (um módulo por aba maior)
api/              API FastAPI do resumo semanal (e Dockerfile)
n8n/              workflow do resumo semanal e guia de configuração
docs/             roteiro do vídeo e guia de deploy
scripts/          check_claude.py (confere sua chave) e smtp_de_teste.py (SMTP local de teste)
tests/            testes automatizados
data/             banco SQLite e gabarito (fictícios)
docker-compose.yml  API + n8n
```
