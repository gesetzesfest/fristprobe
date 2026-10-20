"""Gespeicherte Auslesen der Kette mit anderem Code nachrechnen, ohne Modell (nur Standardbibliothek).

Für Änderungen, die nur den Code nach der Auslese betreffen (Gegenproben, Rechner): Jede Ergebniszeile behält
ihre rohe Auslese (`auslese`) und die Antwort der Nachfrage (`nachfrage.auslese`). Beides läuft erneut durch
`kette.verarbeite`; `bewerten.bewerte_antwort` zählt alt gegen neu. Gleiche Modellausgaben, also ein gepaarter
Vergleich (McNemar je Aufgabe, bestanden = alle Läufe exakt).

- neu: der Code dieses Checkouts oder von `--code DIR`.
- alt: mit `--basis DIR` derselbe Weg mit dem Code eines anderen Checkouts (etwa `git worktree add /tmp/basis
  HEAD`): Das misst nur die Änderung. Ohne `--basis` ist alt die gespeicherte Antwort des Laufs; dann steckt jede
  Code-Änderung seit dem Lauf im Vergleich (Drift).

Grenzen: Will der Code eine Nachfrage zu einem anderen Feld als damals (oder überhaupt eine, wo damals keine war),
fehlt deren Antwort. Solche Zeilen werden ohne Nachfrage gerechnet und je Zeile als `nachfrage_anders` markiert;
`belastbar` wiederholt den Vergleich ohne die betroffenen Aufgaben. Ablationen (`…-ohne-gegenprobe`,
`…-ohne-nachfrage`) werden so nachgerechnet, wie sie liefen. Zeilen ohne `aufgabe_kennung` (ältere Läufe) zählen
nur mit `--ohne-kennung`, weil sonst nichts prüft, dass sie zum Aufgabensatz gehören.

  git worktree add /tmp/basis HEAD
  python3 benchmark/fristen/nachrechnen.py --basis /tmp/basis --aufgaben benchmark/fristen/aufgaben.jsonl \
      --ergebnisse benchmark/fristen/ergebnisse/windows-seed
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent


def _code_wurzel(argv: list[str]) -> Path:
    """--code DIR vor den Importen lesen: aus diesem Checkout werden kette, bewerten und pruefki geladen."""
    for i, a in enumerate(argv):
        if a == "--code" and i + 1 < len(argv):
            return Path(argv[i + 1]).resolve()
        if a.startswith("--code="):
            return Path(a.split("=", 1)[1]).resolve()
    return HIER.parents[1]


CODE = _code_wurzel(sys.argv[1:])
for _p in (str(CODE), str(CODE / "benchmark" / "fristen")):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import bewerten as B  # noqa: E402
import kette as K  # noqa: E402
import statistik as S  # noqa: E402


def nachrechne_zeile(aufgabe: dict, zeile: dict) -> dict:
    """Eine Ergebniszeile der Kette neu verarbeiten: Bewertung, Regeln der Gegenproben, Nachfrage-Abgleich."""
    fassung = "v2" if zeile.get("prompt_version", "").endswith("-v2") else "v3"
    modell = zeile.get("modell", "")
    gegenprobe = "-ohne-gegenprobe" not in modell
    mit_nachfrage = fassung != "v2" and "-ohne-nachfrage" not in modell
    roh = zeile.get("auslese")
    teil = K.verarbeite(aufgabe, roh, fassung, gegenprobe=gegenprobe)
    feld_neu = K.nachfrage_feld(teil.get("rechnung")) if mit_nachfrage else None
    alt_nf = zeile.get("nachfrage") or None
    feld_alt = alt_nf.get("feld") if alt_nf else None
    if feld_neu and feld_neu == feld_alt:
        teil = K.verarbeite(aufgabe, roh, fassung, nachfrage=(feld_neu, alt_nf.get("auslese")), gegenprobe=gegenprobe)
    b = B.bewerte_antwort(aufgabe, {"antwort_json": teil.get("antwort_json"), "lauf": zeile.get("lauf")})
    return {"id": aufgabe["id"], "lauf": zeile.get("lauf"), "exakt": b["exakt"], "sicherheit": b["sicherheit"],
            "sicher_falsch": b["sicher_falsch"], "nachfrage_anders": feld_neu != feld_alt,
            "regeln": sorted({e["regel"] for e in teil.get("gegenproben") or []})}


def gespeichert(aufgabe: dict, zeile: dict) -> dict:
    """Die gespeicherte Antwort der Zeile, bewertet wie eine nachgerechnete."""
    b = B.bewerte_antwort(aufgabe, zeile)
    return {"id": aufgabe["id"], "lauf": zeile.get("lauf"), "exakt": b["exakt"], "sicherheit": b["sicherheit"],
            "sicher_falsch": b["sicher_falsch"], "nachfrage_anders": False,
            "regeln": sorted({e["regel"] for e in zeile.get("gegenproben") or []})}


def auswahl(aufgaben: dict[str, dict], zeilen: list[dict], ohne_kennung: bool = False) -> tuple[list[dict], dict]:
    """Zeilen, die zum Aufgabensatz gehören; dazu die Zähler der verworfenen."""
    fremd = set(B.fremde_zeilen(aufgaben, zeilen))
    gut, weg = [], {"fremd": sorted(fremd), "ohne_kennung": 0, "fehler": 0, "unbekannt": 0}
    for z in zeilen:
        if z["id"] not in aufgaben:
            weg["unbekannt"] += 1
        elif z["id"] in fremd:
            continue
        elif z.get("fehler"):
            weg["fehler"] += 1
        elif not z.get("aufgabe_kennung") and not ohne_kennung:
            weg["ohne_kennung"] += 1
        else:
            gut.append(z)
    return gut, weg


def _vergleich(aufgaben: dict, alt: list[dict], neu: list[dict], laeufe: int, ids: list[str]) -> dict:
    a = set(B.bestanden_ids(aufgaben, alt, laeufe)) & set(ids)
    n = set(B.bestanden_ids(aufgaben, neu, laeufe)) & set(ids)
    return {"aufgaben": len(ids), "bestanden": [len(a), len(n)], "vergleich": S.vergleich(a, n, ids)}


def vergleiche(aufgaben: dict[str, dict], alt: list[dict], neu: list[dict]) -> dict:
    """Alt gegen neu je (id, lauf) gepaart: Kennzahlen, belastbarer Teil, geänderte Zeilen."""
    paar = {(e["id"], e["lauf"]): e for e in alt}
    neu = [e for e in neu if (e["id"], e["lauf"]) in paar]
    alt = [paar[(e["id"], e["lauf"])] for e in neu]
    laeufe = max((e["lauf"] or 1 for e in neu), default=1)
    ids = sorted({e["id"] for e in neu})
    geschaetzt = {e["id"] for e in [*alt, *neu] if e["nachfrage_anders"]}
    geaendert = [{"id": n["id"], "lauf": n["lauf"], "exakt": [a["exakt"], n["exakt"]],
                  "sicherheit": [a["sicherheit"], n["sicherheit"]],
                  "regeln_dazu": sorted(set(n["regeln"]) - set(a["regeln"])),
                  "regeln_weg": sorted(set(a["regeln"]) - set(n["regeln"])),
                  "nachfrage_anders": a["nachfrage_anders"] or n["nachfrage_anders"]}
                 for a, n in zip(alt, neu) if (a["exakt"], a["sicherheit"]) != (n["exakt"], n["sicherheit"])]
    return {"laeufe": laeufe, "zeilen": len(neu),
            "exakt_zeilen": [sum(e["exakt"] for e in alt), sum(e["exakt"] for e in neu)],
            "sicher_falsch": [sum(e["sicher_falsch"] for e in alt), sum(e["sicher_falsch"] for e in neu)],
            **_vergleich(aufgaben, alt, neu, laeufe, ids),
            "nachfrage_anders": sorted(geschaetzt),
            "belastbar": _vergleich(aufgaben, alt, neu, laeufe, [i for i in ids if i not in geschaetzt]),
            "geaendert": geaendert}


def nachrechne(aufgaben: dict[str, dict], zeilen: list[dict], basis: list[dict] | None = None,
               ohne_kennung: bool = False) -> dict:
    """Alle Zeilen eines Modells nachrechnen. ``basis``: nachgerechnete Zeilen des alten Codes (sonst gilt die
    gespeicherte Antwort als alt)."""
    gut, weg = auswahl(aufgaben, zeilen, ohne_kennung)
    neu = [nachrechne_zeile(aufgaben[z["id"]], z) for z in gut]
    alt = basis if basis is not None else [gespeichert(aufgaben[z["id"]], z) for z in gut]
    return {"alt": "basis" if basis is not None else "gespeichert", "verworfen": weg, **vergleiche(aufgaben, alt, neu)}


def _lade(args) -> tuple[dict, dict]:
    with open(args.aufgaben, encoding="utf-8") as fh:
        aufgaben = {a["id"]: a for a in map(json.loads, filter(str.strip, fh))}
    je_modell = {m: z for m, z in sorted(B.lade_ergebnisse(args.ergebnisse).items())
                 if (not args.modell or m == args.modell) and any(x.get("quelle") == "kette" for x in z)}
    return aufgaben, je_modell


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--aufgaben", type=Path, required=True, help="Aufgabensatz (jsonl), gegen den bewertet wird")
    ap.add_argument("--ergebnisse", type=Path, nargs="+", required=True, help="Ergebnisdateien oder -ordner")
    ap.add_argument("--modell", help="nur diese Kette (Name wie in der Rangliste)")
    ap.add_argument("--code", type=Path, help="Checkout, dessen Code neu rechnet (Standard: dieser)")
    ap.add_argument("--basis", type=Path, help="Checkout mit dem alten Code; ohne: gespeicherte Antworten")
    ap.add_argument("--ohne-kennung", action="store_true", help="auch Zeilen ohne aufgabe_kennung zählen")
    ap.add_argument("--nur-zeilen", action="store_true", help=argparse.SUPPRESS)   # für --basis (Unterprozess)
    args = ap.parse_args(argv)
    aufgaben, je_modell = _lade(args)
    if args.nur_zeilen:
        aus = {m: [nachrechne_zeile(aufgaben[z["id"]], z) for z in auswahl(aufgaben, zeilen, args.ohne_kennung)[0]]
               for m, zeilen in je_modell.items()}
    else:
        basis = None
        if args.basis:
            befehl = [sys.executable, str(Path(__file__).resolve()), "--nur-zeilen", "--code", str(args.basis),
                      "--aufgaben", str(args.aufgaben), "--ergebnisse", *map(str, args.ergebnisse)]
            befehl += ["--modell", args.modell] if args.modell else []
            befehl += ["--ohne-kennung"] if args.ohne_kennung else []
            basis = json.loads(subprocess.run(befehl, capture_output=True, text=True, check=True).stdout)
        aus = {m: nachrechne(aufgaben, zeilen, basis.get(m, []) if basis is not None else None, args.ohne_kennung)
               for m, zeilen in je_modell.items()}
    json.dump(aus, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
