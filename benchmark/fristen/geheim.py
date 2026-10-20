#!/usr/bin/env python3
"""Geheime Seeds mit öffentlichem Hash (Plan Geheimhaltung, wissen 2026-10-20-geheimhaltung-testsatz).

Der Generator ist öffentlich. Wer den Seed kennt, kann den Testsatz nachbauen. Deshalb:
  1. `neu NAME` zieht einen zufälligen Seed und ein Salz, erzeugt den Satz nach geheim/NAME/aufgaben.jsonl
     und trägt nur den Hash in geheim_hashes.json ein (öffentlich, darf ins Repo).
  2. Gemessen wird mit `kette.py --aufgaben geheim/NAME/aufgaben.jsonl --ausgabe-dir geheim/NAME/ergebnisse`.
     Ins Repo kommen danach nur rangliste.json/.md.
  3. `freigeben NAME` schreibt Seed und Salz in geheim_hashes.json, wenn der Satz verbraucht ist (z. B. nach einem
     Lauf über eine fremde API). Dann kann jeder mit `pruefe NAME` nachrechnen, dass der Satz vorher feststand.

Der Ordner geheim/ steht in .gitignore. Seeds nie in Dateinamen, Commits oder Chats.

  python3.12 benchmark/fristen/geheim.py neu frisch-a --vorlagen 2
  python3.12 benchmark/fristen/geheim.py liste
  python3.12 benchmark/fristen/geheim.py freigeben frisch-a
  python3.12 benchmark/fristen/geheim.py pruefe frisch-a
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
from datetime import date
from pathlib import Path

FRISTEN = Path(__file__).resolve().parent
WURZEL = FRISTEN.parent.parent
sys.path.insert(0, str(FRISTEN))

import generator as G  # noqa: E402

GEHEIM = WURZEL / "geheim"
HASHES = FRISTEN / "geheim_hashes.json"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def satz_hash(name: str, seed: int, salz: str) -> str:
    return hashlib.sha256(f"fristprobe:{name}:{seed}:{salz}".encode()).hexdigest()


def aufgaben_hash(aufgaben: list[dict]) -> str:
    text = "".join(json.dumps(a, ensure_ascii=False, sort_keys=True) + "\n" for a in aufgaben)
    return hashlib.sha256(text.encode()).hexdigest()


def _lies(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


def _schreib(pfad: Path, daten: dict) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def neu(name: str, vorlagen: int = 1, *, geheim: Path = GEHEIM, hashes: Path = HASHES, heute: str | None = None) -> dict:
    if not NAME.match(name):
        raise SystemExit("Name nur aus a-z, 0-9 und -, ohne Seed oder Datum mit Uhrzeit")
    oeffentlich, privat = _lies(hashes), _lies(geheim / "seeds.json")
    if name in oeffentlich or name in privat:
        raise SystemExit(f"{name} gibt es schon")
    seed, salz = secrets.randbits(63), secrets.token_hex(16)
    aufgaben = G.erzeuge(seed, vorlagen)
    (geheim / name).mkdir(parents=True, exist_ok=True)
    G.schreibe(aufgaben, geheim / name / "aufgaben.jsonl")
    heute = heute or date.today().isoformat()
    privat[name] = {"seed": seed, "salz": salz, "vorlagen": vorlagen, "datum": heute}
    eintrag = {"hash": satz_hash(name, seed, salz), "aufgaben_hash": aufgaben_hash(aufgaben),
               "vorlagen": vorlagen, "datum": heute, "aufgaben": len(aufgaben)}
    oeffentlich[name] = eintrag
    _schreib(geheim / "seeds.json", privat)
    _schreib(hashes, oeffentlich)
    return eintrag


def freigeben(name: str, *, geheim: Path = GEHEIM, hashes: Path = HASHES) -> dict:
    oeffentlich, privat = _lies(hashes), _lies(geheim / "seeds.json")
    if name not in privat or name not in oeffentlich:
        raise SystemExit(f"{name} unbekannt")
    oeffentlich[name].update(seed=privat[name]["seed"], salz=privat[name]["salz"])
    _schreib(hashes, oeffentlich)
    return oeffentlich[name]


def pruefe(name: str, *, hashes: Path = HASHES) -> list[str]:
    """Für jeden nachrechenbar, sobald Seed und Salz freigegeben sind. Leere Liste = stimmt."""
    e = _lies(hashes).get(name)
    if e is None:
        return [f"{name} steht nicht in {hashes.name}"]
    if "seed" not in e:
        return [f"{name} ist noch geheim"]
    fehler = []
    if satz_hash(name, e["seed"], e["salz"]) != e["hash"]:
        fehler.append("Hash passt nicht zu Seed und Salz")
    if e["vorlagen"] == 2 and not (FRISTEN / "vorlagen2.py").exists():
        fehler.append("Aufgaben nicht nachgerechnet: Vorlagen v2 sind nicht öffentlich")
    elif aufgaben_hash(G.erzeuge(e["seed"], e["vorlagen"])) != e["aufgaben_hash"]:
        fehler.append("Generator erzeugt heute andere Aufgaben als damals (Codeänderung?)")
    return fehler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="befehl", required=True)
    n = sub.add_parser("neu")
    n.add_argument("name")
    n.add_argument("--vorlagen", type=int, choices=[1, 2], default=1)
    sub.add_parser("liste")
    for b in ("freigeben", "pruefe"):
        sub.add_parser(b).add_argument("name")
    a = ap.parse_args(argv)
    if a.befehl == "neu":
        e = neu(a.name, a.vorlagen)
        print(f"{a.name}: {e['aufgaben']} Aufgaben nach geheim/{a.name}/aufgaben.jsonl, Hash {e['hash']}")
    elif a.befehl == "liste":
        for name, e in sorted(_lies(HASHES).items()):
            print(f"{name}  {e['datum']}  v{e['vorlagen']}  {'freigegeben' if 'seed' in e else 'geheim'}  {e['hash'][:16]}…")
    elif a.befehl == "freigeben":
        freigeben(a.name)
        print(f"{a.name}: Seed und Salz stehen jetzt in {HASHES.name}")
    else:
        fehler = pruefe(a.name)
        print("\n".join(fehler) or f"{a.name}: stimmt")
        return 1 if fehler else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
