# Roteiro do vídeo de demonstração (cerca de 1min50)

**Mensagem central:** a ferramenta transforma centenas de avaliações em decisões claras, *encontra os padrões
que plantamos nos dados* e diz com honestidade o que sabe e o que não sabe.

Todos os números abaixo saem do dashboard com os dados fictícios. Se você regenerar os dados (outra *seed*),
confira cada número na tabela do fim antes de gravar.

## Antes de gravar

- Grave em tela cheia, 1920×1080, navegador com zoom de 110% e o dashboard em modo largo.
- Rode o dashboard sobre uma **cópia** do banco, para não deixar rascunhos de teste no original:
  ```bash
  cp data/restaurante.db /tmp/demo.db && COPILOTO_DB=/tmp/demo.db streamlit run app/streamlit_app.py
  ```
  (No PowerShell: `$env:COPILOTO_DB = "C:\temp\demo.db"`.)
- Deixe sem a chave do Claude: o modo offline é determinístico e dá exatamente as respostas deste roteiro.
- Tenha o e-mail do resumo semanal já na caixa de entrada (ou o arquivo `.eml` do SMTP de teste) para a última cena.
- Ordem das abas: Visão geral, Pergunte aos dados, Suspeitas, Causa raiz, Análise por prato, Plano de ação, Respostas.

## Cenas

| Tempo | Na tela | Fala (sugestão) |
|---|---|---|
| 0:00–0:10 | **Visão geral**: gráfico de nota por semana, com a queda na semana de 12/10 | "Um restaurante de delivery recebe centenas de avaliações por mês. Ninguém consegue ler tudo e ligar cada reclamação a uma causa. Aqui estão seis meses de dados fictícios, e a nota caiu em outubro." |
| 0:10–0:28 | **Pergunte aos dados**: clicar em *Por que minha nota caiu em outubro?* e deixar a resposta aparecer; abrir "Números usados" | "Pergunto em português. A resposta separa o que é falso do que é real: da queda de 0,94, 0,75 ponto vem de 44 avaliações suspeitas. O resto coincide com a entrega, que na sexta à noite passou de 48 para 64 minutos. E cada número vem de uma consulta calculada em código, não da IA." |
| 0:28–0:42 | **Suspeitas**: alerta do ataque (14 a 16/10), gráfico de notas 1–2 por dia; depois marcar *Excluir suspeitas médias e altas* na barra lateral | "A ferramenta detectou um ataque de avaliações falsas: textos quase iguais, contas novas, metade sem pedido. Ela só sinaliza; contestar é decisão do dono. Sem as suspeitas, a nota vai de 3,69 para 3,88." |
| 0:42–0:57 | **Causa raiz**: tema *Comida fria*, cartão "Quando e onde" e o gráfico mês a mês | "Por que a comida chega fria? 66% das reclamações vêm de pedidos de sexta à noite, que são só 13% dos pedidos. E o problema piorou em outubro. Se não houver padrão consistente, a ferramenta diz que não há." |
| 0:57–1:10 | **Análise por prato**: ranking, com as barras cinzas de baixa confiança | "Por prato: 58% das 102 avaliações da batata frita relatam problema. Pratos com poucas avaliações aparecem em cinza, com aviso de baixa confiança. Toda porcentagem mostra a base." |
| 1:10–1:25 | **Plano de ação**: primeira ação e o "Como a estimativa foi calculada"; abrir "Sugestões a avaliar" | "O plano ordena o que resolver primeiro pelo efeito na nota: a primeira ação leva de 3,88 para 4,11. As sugestões, como furos de ventilação na embalagem, são hipóteses a testar, não garantia." |
| 1:25–1:38 | **Respostas**: gerar rascunhos, editar um texto, clicar em Aprovar | "Para cada avaliação negativa, um rascunho de resposta que eu edito e aprovo. O app nunca publica nada sozinho, e o nome do cliente nunca vai para a IA." |
| 1:38–1:50 | **E-mail do resumo semanal** aberto, com os três pontos; fechar no README | "Toda segunda às 8h, o n8n envia por e-mail os três pontos que mais precisam de atenção. Os dados são fictícios, com padrões plantados, e o README mostra como a ferramenta encontra cada um." |

## Números do roteiro e onde conferi

| Número | Onde aparece |
|---|---|
| Nota 3,91 → 2,97 (queda de 0,94); 0,75 pelas suspeitas; 44 de 156 avaliações do mês | Pergunte aos dados: *Por que minha nota caiu em outubro?* |
| Entrega na sexta à noite: 48 → 64 min | mesma resposta; aba Causa raiz, "Por que as entregas demoram?" |
| Nota 3,69 → 3,88 sem as suspeitas | aba Suspeitas |
| 66% das reclamações de comida fria, 13% dos pedidos | aba Causa raiz, "Quando e onde" |
| Batata frita: 58% de 102 avaliações | aba Análise por prato |
| Primeira ação do plano: 3,88 → 4,11 | aba Plano de ação (com o filtro *Excluir suspeitas médias e altas*) |

O plano da cena de 1:10 usa o filtro de suspeitas ligado; se você deixar o filtro em *Incluir todas*, a primeira
ação vai de 3,79 para 4,00 e a fala deve acompanhar.

## Se precisar de menos de 1 minuto

Mantenha as cenas de 0:10, 0:28 e 0:42 (a pergunta, as suspeitas e a causa raiz) e feche com a frase final.
