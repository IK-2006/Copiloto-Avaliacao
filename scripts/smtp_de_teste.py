"""Servidor SMTP local de teste, sem dependências: aceita qualquer e-mail e grava cada mensagem em uma pasta.

Serve para testar o fluxo do n8n sem uma conta de e-mail de verdade:

    python scripts/smtp_de_teste.py caixa_de_teste [porta]      # porta padrão: 1025

No n8n, crie a credencial SMTP com host 127.0.0.1 (ou host.docker.internal, se o n8n estiver no Docker),
porta 1025, sem usuário, sem senha e sem SSL/TLS. Cada e-mail enviado vira um arquivo .eml na pasta.
Não use em produção: não há autenticação nem criptografia.
"""
import asyncio
import pathlib
import sys

PASTA = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "caixa_de_teste")
PORTA = int(sys.argv[2]) if len(sys.argv) > 2 else 1025
PASTA.mkdir(parents=True, exist_ok=True)
contador = 0


async def sessao(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    global contador

    async def dizer(linha: str) -> None:
        escritor.write((linha + "\r\n").encode())
        await escritor.drain()

    await dizer("220 smtp de teste pronto")
    dados: list[str] = []
    em_data = False
    while linha := await leitor.readline():
        texto = linha.decode("utf-8", "replace")
        if em_data:
            if texto in (".\r\n", ".\n"):
                em_data = False
                contador += 1
                # newline="": mantém o CRLF do SMTP como veio (no Windows, o padrão duplicaria o retorno de carro)
                (PASTA / f"email_{contador}.eml").write_text("".join(dados), encoding="utf-8", newline="")
                print(f"e-mail {contador} gravado em {PASTA}", flush=True)
                dados = []
                await dizer("250 2.0.0 aceito")
            else:
                dados.append(texto[1:] if texto.startswith("..") else texto)
            continue
        comando = texto.strip().upper()
        if comando.startswith(("EHLO", "HELO")):
            escritor.write(b"250-teste\r\n250-8BITMIME\r\n250 SMTPUTF8\r\n")
            await escritor.drain()
        elif comando.startswith(("MAIL", "RCPT", "RSET", "NOOP")):
            await dizer("250 ok")
        elif comando == "DATA":
            em_data = True
            await dizer("354 envie e termine com uma linha só com ponto")
        elif comando == "QUIT":
            await dizer("221 tchau")
            break
        else:
            await dizer("502 comando nao suportado")
    escritor.close()


async def main() -> None:
    servidor = await asyncio.start_server(sessao, "127.0.0.1", PORTA)
    print(f"SMTP de teste em 127.0.0.1:{PORTA} (Ctrl+C para parar)", flush=True)
    async with servidor:
        await servidor.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
