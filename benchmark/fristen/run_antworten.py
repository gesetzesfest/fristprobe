#!/usr/bin/env python3
"""Liest fremd erzeugte Antworten (z. B. von Opus-Agenten) ins Ergebnisformat ein.

Eingabe: JSONL-Zeilen mit modell, id, lauf, antwort (Text oder JSON-Objekt),
optional dauer_s. Ausgabe: benchmark/fristen/ergebnisse/<datum>-<modell>.jsonl,
gleiches Format wie run_ollama.py (Token-Felder bleiben leer).

  python3 benchmark/fristen/run_antworten.py antworten.jsonl [--datum 2026-10-15] [--ausgabe-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import prompt as P  # noqa: E402
from run_ollama import dateiname  # noqa: E402


def einlesen(pfade: list[Path], aufgaben: dict[str, dict], datum: str, ausgabe_dir: Path) -> dict[str, int]:
    je_modell: dict[str, list[dict]] = defaultdict(list)
    unbekannt = 0
    for pfad in pfade:
        with open(pfad, encoding="utf-8") as fh:
            for nr, z in enumerate(fh, 1):
                if not z.strip():
                    continue
                d = json.loads(z)
                for feld in ("modell", "id", "lauf", "antwort"):
                    if feld not in d:
                        raise ValueError(f"{pfad}:{nr}: Feld {feld!r} fehlt")
                a = aufgaben.get(d["id"])
                if a is None:
                    unbekannt += 1
                    continue
                roh = d["antwort"]
                je_modell[d["modell"]].append({
                    "modell": d["modell"], "id": d["id"], "lauf": int(d["lauf"]), "split": a["split"],
                    "typ": a["typ"], "zeit": d.get("zeit") or datetime.now().isoformat(timespec="seconds"),
                    "quelle": d.get("quelle", "extern"), "prompt_version": P.PROMPT_VERSION,
                    "prompt_hash": P.prompt_hash(), "think": d.get("think"), "optionen": d.get("optionen"),
                    "antwort": roh if isinstance(roh, str) else json.dumps(roh, ensure_ascii=False),
                    "denken": None, "antwort_json": P.lies_antwort(roh),
                    "eval_count": None, "eval_duration": None, "load_duration": None,
                    "prompt_eval_count": None, "prompt_eval_duration": None, "total_duration": None,
                    "tokens_pro_s": None, "fehler": None, "dauer_s": d.get("dauer_s"),
                })
    ausgabe_dir.mkdir(parents=True, exist_ok=True)
    zaehler = {}
    for modell, zeilen in je_modell.items():
        ziel = ausgabe_dir / f"{datum}-{dateiname(modell)}.jsonl"
        with open(ziel, "w", encoding="utf-8") as fh:
            for zeile in sorted(zeilen, key=lambda x: (x["lauf"], x["id"])):
                fh.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        zaehler[modell] = len(zeilen)
    if unbekannt:
        print(f"Warnung: {unbekannt} Antworten zu unbekannten Aufgaben übersprungen.", file=sys.stderr)
    return zaehler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("eingabe", type=Path, nargs="+")
    ap.add_argument("--aufgaben", type=Path, default=HIER / "aufgaben.jsonl")
    ap.add_argument("--ausgabe-dir", type=Path, default=HIER / "ergebnisse")
    ap.add_argument("--datum", default=date.today().isoformat())
    args = ap.parse_args(argv)
    with open(args.aufgaben, encoding="utf-8") as fh:
        aufgaben = {a["id"]: a for a in (json.loads(z) for z in fh if z.strip())}
    zaehler = einlesen(args.eingabe, aufgaben, args.datum, args.ausgabe_dir)
    for m, n in zaehler.items():
        print(f"{m}: {n} Antworten -> {args.ausgabe_dir}/{args.datum}-{dateiname(m)}.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
