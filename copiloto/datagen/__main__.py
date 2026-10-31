"""Uso: python -m copiloto.datagen [--seed 2026] [--db data/restaurante.db]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from copiloto import config
from copiloto.datagen.gerador import SEED_PADRAO, gerar


def main() -> None:
    cfg = config.carregar()
    ap = argparse.ArgumentParser(description="Gera o restaurante fictício e o gabarito dos padrões plantados.")
    ap.add_argument("--seed", type=int, default=SEED_PADRAO)
    ap.add_argument("--db", type=Path, default=cfg.db_path)
    ap.add_argument("--gabarito", type=Path, default=cfg.db_path.parent / "plantados.json")
    args = ap.parse_args()

    resumo = gerar(args.db, args.gabarito, seed=args.seed, salt=cfg.salt_anonimizacao)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print(f"\nBanco:    {args.db}\nGabarito: {args.gabarito}")


if __name__ == "__main__":
    main()
