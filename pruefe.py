#!/usr/bin/env python3
"""Einen Brief prüfen lassen: kleines Modell liest aus, Code rechnet, Wissensbasis belegt.

Nur erfundene Briefe verwenden, keine echten Personendaten.

  python3 pruefe.py brief.txt                                   # Frist berechnen
  python3 pruefe.py brief.txt --frage "Bis wann muss die Klage eingegangen sein?"
  python3 pruefe.py brief.txt --typ pruefen --frage "Stimmt das genannte Fristende?"
  python3 pruefe.py brief.txt --host http://rechner.local:11434 --modell qwen3.5:9b
  cat brief.txt | python3 pruefe.py -                           # von der Standardeingabe

Ablauf wie im Benchmark (Kette v3): Auslese mit JSON-Schema, Gegenproben im Code, höchstens eine gezielte
Nachfrage, dann rechnet pruefki.fristen.rechner. Jede genannte Norm wird in der Wissensbasis nachgeschlagen und
mit ihrem Wortlaut ausgegeben; was dort nicht steht, wird als „nicht belegt“ markiert.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

WURZEL = Path(__file__).resolve().parent
for p in (WURZEL, WURZEL / "benchmark" / "fristen"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import kette as K  # noqa: E402
import prompt_kette as PK  # noqa: E402
import run_ollama as RO  # noqa: E402

WISSEN_DB = WURZEL / "daten" / "wissen.sqlite"
STANDARD_FRAGE = {"berechnen": "Bis zu welchem Tag (einschließlich) muss der Rechtsbehelf spätestens eingegangen sein?",
                  "pruefen": "Prüfen Sie das im Schreiben genannte Fristende. Antworten Sie mit kein_befund (richtig), "
                             "befund (falsch) oder rueckfrage (eine nötige Angabe fehlt). Nennen Sie im Feld "
                             "fristende das richtige Datum (bei rueckfrage null)."}
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def _datum_lang(iso: str | None) -> str:
    if not iso:
        return "—"
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{WOCHENTAGE[d.weekday()]}, {d:%d.%m.%Y}"


def belege(normen: list[str]) -> list[tuple[str, str]]:
    """(Zitat, Belegtext) je Norm aus der Wissensbasis; ohne Wissensbasis oder Treffer: Hinweis statt Text."""
    if not WISSEN_DB.exists():
        return [(n, "(Wissensbasis fehlt: daten/wissen.sqlite)") for n in normen]
    from pruefki.wissen.abruf import Wissensbasis
    wb = Wissensbasis(WISSEN_DB)
    out = []
    try:
        for n in normen:
            t = wb.norm(n)
            if t is None:
                out.append((n, "NICHT BELEGT: steht so nicht in der Wissensbasis (Bundesrecht)."))
                continue
            wortlaut = (t.absatz_text if t.absatz and t.absatz_text else t.text) or "(ohne Text)"
            kopf = f"{t.titel} · {t.gesetz_titel}" + ("" if t.status == "geltend" else f" · Status: {t.status}")
            out.append((n, f"{kopf}\n{wortlaut}\nQuelle: {t.ansicht_url} (Stand {t.stand})"))
    finally:
        wb.schliessen()
    return out


def pruefe(dokument: str, frage: str, typ: str, modell: str, host: str, num_ctx: int = 8192,
           timeout: float = 300.0, chat_fn=None) -> dict:
    """Ein Brief durch die Kette. Gibt die Ergebniszeile zurück (wie im Benchmark, ohne Sollwert)."""
    chat_fn = chat_fn or RO.chat
    aufgabe = {"id": "PRUEFUNG", "dokument": dokument, "frage": frage, "typ": typ}
    fassung = PK.FASSUNGEN[PK.STANDARD]
    args = argparse.Namespace(think=False, timeout=timeout, keep_alive="10m")
    optionen = {"num_ctx": num_ctx, "num_predict": 1024}
    zustand = {"format": "schema"}
    r, _ = K._auslese_chat(chat_fn, host, modell, fassung.nachrichten(aufgabe), args, optionen, zustand,
                           schema=fassung.schema)
    roh = (r.get("message") or {}).get("content", "")
    teil = K.verarbeite(aufgabe, roh, fassung.name)
    feld = K.nachfrage_feld(teil.get("rechnung"))
    if feld:
        r2, _ = K._auslese_chat(chat_fn, host, modell, PK.nachfrage_nachrichten(aufgabe, feld), args, optionen,
                                zustand, schema=PK.nachfrage_schema(feld))
        teil = K.verarbeite(aufgabe, roh, fassung.name, nachfrage=(feld, (r2.get("message") or {}).get("content", "")))
    teil["nachgefragt"] = feld
    return teil


def bericht(teil: dict, mit_belegen: bool = True) -> str:
    a = teil.get("antwort_json") or {}
    if not a:
        return "Keine verwertbare Antwort: Das Modell hat nichts Lesbares geliefert."
    art = a.get("antwortart")
    zeilen = []
    if art in ("berechnet", "kein_befund", "befund"):
        satz = {"berechnet": "Fristende", "kein_befund": "Kein Befund. Das genannte Fristende stimmt",
                "befund": "BEFUND: Das genannte Fristende stimmt nicht. Richtig wäre"}[art]
        zeilen.append(f"{satz}: {_datum_lang(a.get('fristende'))}")
    else:
        zeilen.append("RÜCKFRAGE: Eine nötige Angabe fehlt im Schreiben, ohne sie lässt sich nicht sicher rechnen.")
    if a.get("sicherheit") is not None:
        zeilen.append(f"Sicherheit (vom Code geschätzt): {a['sicherheit']:.0%}".replace(".", ","))
    if a.get("begruendung"):
        zeilen += ["", "Rechenweg:", textwrap.fill(a["begruendung"], 100)]
    r = teil.get("rechnung") or {}
    for titel, schl in (("Annahmen", "annahmen"), ("Zweifel", "zweifel"), ("Fehlt", "fehlend")):
        if r.get(schl):
            zeilen.append(f"{titel}: " + "; ".join(map(str, r[schl])))
    if teil.get("gegenproben"):
        zeilen.append("Gegenproben im Code: " + "; ".join(
            f"{g.get('regel')} {g.get('feld')}: {g.get('grund')}" for g in teil["gegenproben"]))
    if teil.get("nachgefragt"):
        zeilen.append(f"Nachgefragt beim Modell: {teil['nachgefragt']}")
    normen = a.get("normen") or []
    if normen and mit_belegen:
        zeilen += ["", "Belege aus der Wissensbasis:"]
        for zitat, text in belege(normen):
            zeilen += ["", f"■ {zitat}", textwrap.indent(text, "  ")]
    elif normen:
        zeilen += ["", "Normen: " + ", ".join(normen)]
    return "\n".join(zeilen)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Einen (erfundenen) Brief auf Fristen prüfen")
    ap.add_argument("datei", help="Textdatei mit dem Schreiben, '-' für Standardeingabe")
    ap.add_argument("--frage", default=None)
    ap.add_argument("--typ", choices=["berechnen", "pruefen"], default="berechnen")
    ap.add_argument("--modell", default="qwen3:8b")
    ap.add_argument("--host", default=RO.HOST)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--ohne-belege", action="store_true", help="Normtexte nicht ausgeben")
    ap.add_argument("--json", action="store_true", help="Rohergebnis als JSON")
    args = ap.parse_args(argv)
    dokument = sys.stdin.read() if args.datei == "-" else Path(args.datei).read_text(encoding="utf-8")
    teil = pruefe(dokument.strip(), args.frage or STANDARD_FRAGE[args.typ], args.typ, args.modell, args.host,
                  args.num_ctx)
    if args.json:
        print(json.dumps(teil, ensure_ascii=False, indent=1, default=str))
    else:
        print(bericht(teil, mit_belegen=not args.ohne_belege))
    return 0


if __name__ == "__main__":
    sys.exit(main())
