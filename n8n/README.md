# Resumo semanal no n8n

Toda **segunda-feira às 8h** (horário de Brasília) o n8n busca o resumo da semana na API do projeto e o envia por
**e-mail**, com os três pontos que mais precisam de atenção. O n8n só agenda e envia: os números e o texto vêm
da API (`GET /weekly-summary`), calculados em código, sem IA e sem dados pessoais de clientes.

```
Toda segunda às 8h ─► Buscar o resumo na API ─► Enviar o e-mail
 (Schedule Trigger)    (HTTP Request + token)    (SMTP)
```

O arquivo `workflow.json` não contém segredos: o token da API e o SMTP são **credenciais do n8n**, e os endereços
vêm de variáveis de ambiente.

## Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `COPILOTO_API_URL` | endereço da API (padrão `http://api:8000`, o nome do serviço no compose) |
| `RESUMO_EMAIL_PARA` | destinatário do resumo (obrigatória) |
| `RESUMO_EMAIL_DE` | remetente (padrão `copiloto@localhost`; alguns provedores exigem o endereço da conta SMTP) |
| `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` | o workflow lê as variáveis acima com `$env`; no n8n 2.x isso vem bloqueado por padrão |

## Opção A: Docker (recomendada)

```bash
cp .env.example .env        # preencha COPILOTO_API_TOKEN, N8N_ENCRYPTION_KEY e RESUMO_EMAIL_PARA
docker compose up -d        # sobe a API (porta 8000) e o n8n (porta 5678), ambos só em 127.0.0.1
```

Gere os valores secretos com, por exemplo, `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Guarde o `N8N_ENCRYPTION_KEY`: sem ele, as credenciais salvas no n8n ficam ilegíveis.

## Opção B: sem Docker (Node e Python instalados)

Boa para testar. O n8n avisa que rodar fora de um contêiner está obsoleto; em uso contínuo, prefira a opção A.

```bash
# terminal 1: a API
COPILOTO_API_TOKEN=um-token-longo .venv/bin/uvicorn api.main:app --port 8000      # Windows: .venv\Scripts\uvicorn

# terminal 2: o n8n
N8N_BLOCK_ENV_ACCESS_IN_NODE=false COPILOTO_API_URL=http://127.0.0.1:8000 \
RESUMO_EMAIL_PARA=voce@exemplo.com npx n8n@2.45.7 start
```

No PowerShell, defina cada variável com `$env:NOME = "valor"` antes de rodar os comandos.

## Configurar no n8n (uma vez)

1. Abra http://localhost:5678, crie a conta de administrador e escolha **Import from file** em um workflow
   novo: selecione `n8n/workflow.json`.
2. Crie a credencial **Header Auth** chamada `Token da API do Copiloto`: nome `X-API-Token`, valor igual ao
   `COPILOTO_API_TOKEN`. Selecione-a no nó "Buscar o resumo na API".
3. Crie a credencial **SMTP** chamada `SMTP do resumo semanal` e selecione-a no nó "Enviar o e-mail". Para o
   Gmail: host `smtp.gmail.com`, porta `465`, SSL ligado, usuário o seu e-mail e senha uma **senha de app**
   (nunca a senha da conta).
4. Clique em **Execute workflow** para testar: o e-mail deve chegar em poucos segundos.
5. Ative o workflow (chave **Active**). A partir daí ele roda sozinho toda segunda às 8h.

## Testar sem uma conta de e-mail

```bash
python scripts/smtp_de_teste.py caixa_de_teste     # SMTP local que grava cada e-mail como .eml
```

Na credencial SMTP use host `127.0.0.1` (ou `host.docker.internal` se o n8n estiver no Docker), porta `1025`, sem
usuário, sem senha e sem SSL. Não use esse servidor em produção.

## Detalhes do resumo

- A semana são os 7 dias que terminam em `ate` (padrão: o último dia com avaliações). Nos dados fictícios, que
  terminam em 31/10/2026, a primeira semana é 25/10 a 31/10. Em uso real, a API usa o último dia com dados.
- Os três pontos seguem uma ordem fixa: possível ataque de avaliações falsas (últimos 28 dias), queda da nota,
  temas em alta, piora no tempo de entrega e, para completar, as ações do plano de ação (ver
  `copiloto/resumo_semanal.py`). Por padrão as avaliações suspeitas ficam fora dos números; o parâmetro `modo`
  da API muda isso.
- Para ver o JSON: `curl -H "X-API-Token: $COPILOTO_API_TOKEN" http://localhost:8000/weekly-summary`.
