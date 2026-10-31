"""Compara a classificação com o gabarito dos dados fictícios.

Só existe porque os dados são sintéticos: o gabarito registra o que o gerador escreveu em cada
avaliação. Nenhuma parte do app usa o gabarito; ele serve a testes e ao README.

Uso: python -m copiloto.validacao
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from copiloto import config, db


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precisao": round(p, 3), "revocacao": round(r, 3), "f1": round(f, 3)}


def comparar(con: sqlite3.Connection, caminho_gabarito: str | Path) -> dict:
    gab = {int(k): v for k, v in json.loads(Path(caminho_gabarito).read_text(encoding="utf-8"))["avaliacoes"].items()}
    linhas = con.execute("SELECT avaliacao_id, sentimento, temas, pratos FROM classificacoes").fetchall()

    acertos_sent = 0
    tema = {"tp": 0, "fp": 0, "fn": 0}
    prato = {"tp": 0, "fp": 0, "fn": 0}
    prato_problema = {"tp": 0, "fp": 0, "fn": 0}
    for r in linhas:
        g = gab[r["avaliacao_id"]]
        acertos_sent += r["sentimento"] == g["sentimento"]

        pred_t, ver_t = set(json.loads(r["temas"])), set(g["temas"])
        tema["tp"] += len(pred_t & ver_t)
        tema["fp"] += len(pred_t - ver_t)
        tema["fn"] += len(ver_t - pred_t)

        pred_p = {p["prato"]: set(p["problemas"]) for p in json.loads(r["pratos"])}
        ver_p = {p["prato"]: set(p["problemas"]) for p in g["pratos"]}
        prato["tp"] += len(pred_p.keys() & ver_p.keys())
        prato["fp"] += len(pred_p.keys() - ver_p.keys())
        prato["fn"] += len(ver_p.keys() - pred_p.keys())
        for nome in ver_p.keys() | pred_p.keys():
            pares_pred = {(nome, t) for t in pred_p.get(nome, ())}
            pares_ver = {(nome, t) for t in ver_p.get(nome, ())}
            prato_problema["tp"] += len(pares_pred & pares_ver)
            prato_problema["fp"] += len(pares_pred - pares_ver)
            prato_problema["fn"] += len(pares_ver - pares_pred)

    n = len(linhas)
    return {
        "avaliacoes": n,
        "acuracia_sentimento": round(acertos_sent / n, 3) if n else 0.0,
        "temas": _prf(**tema),
        "pratos_mencionados": _prf(**prato),
        "problema_por_prato": _prf(**prato_problema),
    }


def main() -> None:
    cfg = config.carregar()
    con = db.conectar(cfg.db_path)
    resultado = comparar(con, cfg.db_path.parent / "plantados.json")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
