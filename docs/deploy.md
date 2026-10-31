# Publicar o dashboard online (Streamlit Community Cloud)

O dashboard é um app Streamlit (`app/streamlit_app.py`) que lê o banco SQLite versionado em `data/restaurante.db`
(dados **fictícios**). Não precisa de servidor próprio: o Streamlit Community Cloud é gratuito e publica a partir do
GitHub. O último passo exige o login na sua conta do GitHub, então ele é seu; o repositório já está pronto.

## Passo a passo

1. **Envie o repositório ao GitHub** (público, para o plano gratuito do Streamlit). Verifique antes que não há
   `.env` nem chaves: `git ls-files | grep -i env` deve mostrar só `.env.example`.
2. Acesse https://share.streamlit.io, entre com o GitHub e clique em **Create app**.
3. Escolha o repositório e a branch, e informe o arquivo principal: `app/streamlit_app.py`.
4. Em **Advanced settings**, escolha o **Python 3.12** (a versão em que o app foi testado é a 3.14, e o código
   exige 3.11 ou mais novo; as dependências são instaladas de `requirements.txt`).
5. (Opcional) Em **Secrets**, cole as chaves que quiser ligar:

   ```toml
   # Sem esta linha o app roda no modo offline (regras), o que já basta para a demonstração.
   ANTHROPIC_API_KEY = "sk-ant-..."
   # Limite de chamadas ao Claude por dia: protege você de custo se alguém usar o demo em excesso.
   COPILOTO_LIMITE_DIARIO_LLM = "50"
   ```

6. Clique em **Deploy**. Em alguns minutos o app abre em `https://<nome>.streamlit.app`. Coloque esse endereço em
   `COPILOTO_DASHBOARD_URL` (`.env`) para o link aparecer no e-mail do resumo semanal.

## O que esperar

- **Sem chave:** tudo funciona, incluindo respostas e perguntas, no modo offline.
- **Com chave:** respostas e perguntas livres usam o Claude, com limite diário (cada pergunta pode gastar até
  6 chamadas). Se o limite acabar ou o Claude falhar, o app volta sozinho ao modo offline.
- **Escritas não persistem:** os rascunhos de resposta e o contador de uso são gravados no banco dentro do
  contêiner, e o Streamlit Cloud reinicia o contêiner de tempos em tempos. Para a demonstração isso é
  aceitável; para uso real, aponte `COPILOTO_DB` para um banco persistente.
- **Qualquer visitante vê o mesmo estado:** o demo público não tem login. Não coloque dados reais nele.

## Versões testadas

`requirements-lock.txt` guarda as versões exatas com que os testes passaram (Python 3.14). Para reproduzir:
`pip install -r requirements-lock.txt`.
