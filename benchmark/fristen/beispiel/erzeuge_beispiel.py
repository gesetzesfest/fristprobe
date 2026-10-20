#!/usr/bin/env python3
"""Baut eine künstliche Antwortdatei, um bewerten.py ohne Ollama zu testen.

Drei erfundene „Modelle“, je drei Läufe:
  beispiel-perfekt  antwortet immer mit dem Sollwert und den Pflichtnormen (Erwartung: 50/50)
  beispiel-naiv     vergisst Fiktion bzw. Verschiebung (Teilpunkt-Datum), sagt bei Prüfaufgaben
                    immer kein_befund, nennt eine erfundene Norm und ist dabei sehr sicher
  beispiel-kaputt   Lauf 1 kein JSON, Lauf 2 fehlt ganz, Lauf 3 richtig

  python3 benchmark/fristen/beispiel/erzeuge_beispiel.py
  python3 benchmark/fristen/run_antworten.py benchmark/fristen/beispiel/antworten.jsonl \
      --ausgabe-dir benchmark/fristen/beispiel/ergebnisse --datum 2026-10-14
  python3 benchmark/fristen/bewerten.py --ergebnisse benchmark/fristen/beispiel/ergebnisse \
      --ausgabe-dir benchmark/fristen/beispiel
"""

from __future__ import annotations

import json
from pathlib import Path

HIER = Path(__file__).resolve().parent
AUFGABEN = HIER.parent / "aufgaben.jsonl"


def _erste(p):
    return p[0] if isinstance(p, list) else p


def perfekt(a):
    s = a["sollwert"]
    return {"antwortart": s["antwortart"], "fristende": s["fristende"],
            "normen": [_erste(p) for p in s["normen_pflicht"]], "sicherheit": 0.9, "begruendung": "Sollwert."}


def naiv(a):
    s = a["sollwert"]
    if a["typ"] == "pruefen":
        return {"antwortart": "kein_befund", "fristende": a["parameter"].get("genannt"),
                "normen": ["§ 999 SGG"], "sicherheit": 0.95, "begruendung": "Sieht plausibel aus."}
    datum = (s.get("teilpunkt_daten") or [s["fristende"]])[0]
    return {"antwortart": "berechnet", "fristende": datum, "normen": [_erste(s["normen_pflicht"][0]), "§ 999 SGG"],
            "sicherheit": 0.95, "begruendung": "Ohne Fiktion und Verschiebung gerechnet."}


def main():
    aufgaben = [json.loads(z) for z in AUFGABEN.read_text("utf-8").splitlines() if z.strip()]
    zeilen = []
    for lauf in (1, 2, 3):
        for a in aufgaben:
            zeilen.append({"modell": "beispiel-perfekt", "id": a["id"], "lauf": lauf, "antwort": perfekt(a)})
            zeilen.append({"modell": "beispiel-naiv", "id": a["id"], "lauf": lauf,
                           "antwort": json.dumps(naiv(a), ensure_ascii=False)})
            if lauf == 1:
                zeilen.append({"modell": "beispiel-kaputt", "id": a["id"], "lauf": 1,
                               "antwort": "Ich denke, die Frist endet irgendwann im Frühjahr."})
            elif lauf == 3:
                zeilen.append({"modell": "beispiel-kaputt", "id": a["id"], "lauf": 3,
                               "antwort": "```json\n" + json.dumps(perfekt(a), ensure_ascii=False) + "\n```"})
    with open(HIER / "antworten.jsonl", "w", encoding="utf-8") as fh:
        for z in zeilen:
            fh.write(json.dumps(z, ensure_ascii=False) + "\n")
    print(f"{len(zeilen)} Beispielantworten nach {HIER / 'antworten.jsonl'} geschrieben.")


if __name__ == "__main__":
    main()
