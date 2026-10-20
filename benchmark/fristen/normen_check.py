#!/usr/bin/env python3
"""Prüft die Normen des Fristen-Benchmarks gegen die Wissensbasis des Bundesrechts.

1. Jede Norm aus sollwert.normen_pflicht und sollwert.normen_ok in aufgaben.jsonl: Gibt es sie als geltende Norm,
   und gibt es den genannten Absatz? (pruefki.wissen.abruf, Quelle gesetze-im-internet.de)
2. Dieselben Normen als Bewertungsschlüssel (Paragraph, Gesetz), so wie bewerten.py sie vergleicht.
3. Zur Information: Einträge der Positivliste (recht/belege.json plus GAENGIGE_NORMEN), die in der Wissensbasis
   nicht als geltende Norm stehen.

  python3.12 benchmark/fristen/normen_check.py      # -> benchmark/fristen/normen_check.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
sys.path.insert(0, str(WURZEL))
from pruefki.fristen.normen import positivliste, schluessel  # noqa: E402
from pruefki.wissen.abruf import Wissensbasis  # noqa: E402
from pruefki.wissen.index import DB_STANDARD  # noqa: E402


def sollnormen(aufgaben: list[dict]) -> dict[str, Counter]:
    """Norm -> Zähler je Rolle ('Pflicht', 'ok')."""
    out: dict[str, Counter] = defaultdict(Counter)
    for a in aufgaben:
        for p in a["sollwert"]["normen_pflicht"]:
            for n in (p if isinstance(p, list) else [p]):
                out[n]["Pflicht"] += 1
        for n in a["sollwert"]["normen_ok"]:
            out[n]["ok"] += 1
    return out


def pruefe(wb: Wissensbasis, aufgaben: list[dict]) -> dict:
    normen = sollnormen(aufgaben)
    zeilen = []
    for n in sorted(normen, key=lambda x: (x.split()[-1], x)):
        for e in wb.pruefe(n) or [{"norm": n, "ergebnis": "nicht_erkannt", "zitat": None, "titel": None,
                                    "absatz": None, "absatz_ok": None, "stand": None}]:
            zeilen.append({"eingabe": n, "rollen": dict(normen[n]), **e})
    schl = sorted({k for n in normen for k in schluessel(n)}, key=lambda k: (k[1], k[0]))
    schl_erg = {k: wb.existiert_schluessel(*k) for k in schl}
    pos = sorted(positivliste(), key=lambda k: (k[1], k[0]))
    pos_erg = {k: wb.existiert_schluessel(*k) for k in pos}
    gruende = {k: grund(wb, *k) for k, v in pos_erg.items() if not v}
    return {"zeilen": zeilen, "schluessel": schl_erg, "positivliste": pos_erg, "gruende": gruende}


def _anzeige(p: str, g: str) -> str:
    return f"{'Art.' if p.startswith('art') else '§'} {p.removeprefix('art')} {g}"


def grund(wb: Wissensbasis, p: str, g: str) -> str:
    """Warum ein Positivlisten-Schlüssel nicht als geltende Norm in der Wissensbasis steht."""
    k = wb.gesetz_kuerzel(g)
    if k is None:
        return "Gesetz nicht in der Wissensbasis (Landesrecht oder Änderungsgesetz ohne eigene Fassung)"
    if not p.startswith("art"):
        t = wb.finde(k, "art" + p)
        if t and t.status == "geltend":
            return f"als § nicht vorhanden, das Gesetz zählt nach Artikeln: {t.zitat} existiert"
        unter = wb.con.execute("SELECT zitat FROM normen WHERE gesetz_kuerzel = ? AND enbez_norm GLOB ? "
                               "AND status = 'geltend' ORDER BY position LIMIT 3", (k, f"art*§{p}")).fetchall()
        if unter:
            return ("nur unter einem Artikel vorhanden (" + ", ".join(r[0] for r in unter) + "); "
                    "pruefki.fristen.normen.schluessel verliert den Artikel")
    t = wb.finde(k, p if p.startswith("art") else "§" + p)
    if t is None:
        g_row = wb.gesetz(g) or {}
        return f"nicht im geltenden Text ({g_row.get('abk', g)}, {g_row.get('stand', '')})"
    return f"{t.status} ({t.zitat}" + (f" {t.titel}" if t.titel else "") + ")"


def _rollen(r: dict) -> str:
    return ", ".join(f"{k} {v}×" for k, v in sorted(r.items()))


def markdown(erg: dict, meta: dict) -> str:
    zeilen = erg["zeilen"]
    ok = sum(z["ergebnis"] == "ok" for z in zeilen)
    eingaben = len({z["eingabe"] for z in zeilen})
    schl = erg["schluessel"]
    schl_ok = sum(1 for v in schl.values() if v)
    pos = erg["positivliste"]
    t = [
        "# Normen-Check Fristen-Benchmark",
        "",
        f"Wissensbasis: {meta.get('gesetze')} Gesetze, {meta.get('normen')} Normen, gebaut {meta.get('gebaut')}. "
        f"Quelle: {meta.get('quelle')}.",
        "",
        "## Ergebnis",
        "",
        f"- Normen in `normen_pflicht` und `normen_ok` (verschiedene Schreibweisen): {eingaben}",
        f"- davon als geltende Norm gefunden, genannter Absatz, Satz und Nummer vorhanden: **{ok} von {len(zeilen)}**",
        f"- Bewertungsschlüssel (Paragraph, Gesetz) wie in `bewerten.py`: **{schl_ok} von {len(schl)}** vorhanden",
        f"- Positivliste: {sum(1 for v in pos.values() if v)} von {len(pos)} Einträgen als geltende Norm im "
        f"Bundesrecht, {sum(1 for v in pos.values() if v is None)} mit Gesetz außerhalb der Wissensbasis, "
        f"{sum(1 for v in pos.values() if v is False)} nicht gefunden (Abschnitt 3)",
        "",
        "Geprüft wird: Gesetz über die Alias-Tabelle auflösen, Norm über die Bezeichnung finden, Status `geltend`, "
        "bei „Abs. n“ muss der Absatz „(n)“ im Normtext stehen, bei „Satz n“ muss der Absatz mindestens n Satzenden "
        "haben, bei „Nr. n“ muss „n.“ als Listenmarke stehen.",
        "",
        "## 1. Normen aus aufgaben.jsonl",
        "",
        "| Norm in aufgaben.jsonl | Rolle | Fundstelle | Titel | Abs. | Ergebnis | Stand |",
        "|---|---|---|---|---|---|---|",
    ]
    for z in zeilen:
        absatz = "—" if not z["absatz"] else ("ja" if z["absatz_ok"] else "fehlt")
        t.append(f"| {z['eingabe']} | {_rollen(z['rollen'])} | {z['zitat'] or '—'} | {z['titel'] or ''} | {absatz} | "
                 f"{z['ergebnis']} | {z['stand'] or ''} |")
    t += ["", "## 2. Bewertungsschlüssel", "",
          "Diese Schlüssel vergleicht `bewerten.py` (Absatz und Satz fallen weg).", ""]
    t.append(", ".join(f"{'§ ' if not p.startswith('art') else 'Art. '}{p.removeprefix('art')} {g}"
                       f"{'' if v else ' (FEHLT)'}" for (p, g), v in schl.items()))
    fehlend = [k for k, v in pos.items() if not v]
    t += ["", "## 3. Positivliste ohne geltende Norm in der Wissensbasis", "",
          "Zur Information. In der Bewertung bleiben diese Einträge belegt (Positivliste oder Wissensbasis).", ""]
    if not fehlend:
        t.append("Keine.")
    t += [f"- {_anzeige(*k)}: {erg['gruende'][k]}" for k in fehlend]
    return "\n".join(t) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normen des Fristen-Benchmarks gegen die Wissensbasis prüfen")
    ap.add_argument("--aufgaben", type=Path, default=HIER / "aufgaben.jsonl")
    ap.add_argument("--db", type=Path, default=DB_STANDARD)
    ap.add_argument("--ausgabe", type=Path, default=HIER / "normen_check.md")
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"Wissensbasis fehlt: {args.db} (python3.12 -m pruefki.wissen.index --neu)", file=sys.stderr)
        return 2
    wb = Wissensbasis(args.db)
    aufgaben = [json.loads(z) for z in args.aufgaben.read_text("utf-8").splitlines() if z.strip()]
    erg = pruefe(wb, aufgaben)
    md = markdown(erg, wb.meta())
    args.ausgabe.write_text(md, encoding="utf-8")
    print(md.split("## 1.")[0].strip())
    alles_ok = all(z["ergebnis"] == "ok" for z in erg["zeilen"]) and all(erg["schluessel"].values())
    return 0 if alles_ok else 1


if __name__ == "__main__":
    sys.exit(main())
