#!/usr/bin/env python3
"""Schreibt alle Aufgaben OHNE Sollwert als Prompt-Datei (JSONL: id, system, user).

Damit kann der Mentor Opus-Agenten blind antworten lassen: Die Datei
enthält nur, was ein Modell sehen darf. Kein Sollwert, kein Rechenweg, keine
Parameter, kein Prüfhinweis.

Antworten kommen danach als JSONL (modell, id, lauf, antwort) zurück und
werden mit run_antworten.py eingelesen.

  python3 benchmark/fristen/opus_auftrag.py [--split alle|oeffentlich|privat] [--ausgabe PFAD]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import prompt as P  # noqa: E402

VERBOTEN = ("sollwert", "rechenweg", "parameter", "pruefhinweis", "falle")


def zeilen(aufgaben: list[dict]) -> list[dict]:
    out = []
    for a in aufgaben:
        z = {"id": a["id"], "system": P.SYSTEM_PROMPT, "user": P.nutzer_nachricht(a)}
        text = json.dumps(z, ensure_ascii=False)
        # Schutz gegen versehentliches Durchsickern des Sollwerts über Feldnamen
        assert not any(f'"{v}"' in text for v in VERBOTEN), a["id"]
        out.append(z)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--aufgaben", type=Path, default=HIER / "aufgaben.jsonl")
    ap.add_argument("--ausgabe", type=Path, default=HIER / "opus_auftrag.jsonl")
    ap.add_argument("--split", choices=["alle", "oeffentlich", "privat"], default="alle")
    args = ap.parse_args(argv)
    with open(args.aufgaben, encoding="utf-8") as fh:
        aufgaben = [json.loads(z) for z in fh if z.strip()]
    if args.split != "alle":
        aufgaben = [a for a in aufgaben if a["split"] == args.split]
    with open(args.ausgabe, "w", encoding="utf-8") as fh:
        for z in zeilen(aufgaben):
            fh.write(json.dumps(z, ensure_ascii=False) + "\n")
    print(f"{len(aufgaben)} Aufträge nach {args.ausgabe} geschrieben (Prompt {P.PROMPT_VERSION}, {P.prompt_hash()}).")
    print("Antwortformat zurück: JSONL mit modell, id, lauf, antwort -> run_antworten.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
