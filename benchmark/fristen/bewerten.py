#!/usr/bin/env python3
"""Bewertung des Fristen-Benchmarks, nur per Code (keine KI als Richter).

Kennzahlen je Modell, getrennt nach Gesamt / öffentlich / privat / berechnen / prüfen:

- exakt (Hauptnote): Antwortart und Fristende stimmen. Eine Aufgabe zählt nur,
  wenn ALLE Läufe (Standard 3) exakt sind. Fehlende Läufe zählen als falsch.
- Teilpunkte: 1,0 exakt; 0,5 wenn nur die Verschiebung auf den nächsten Werktag
  oder nur die Bekanntgabefiktion fehlt (Daten in sollwert.teilpunkt_daten,
  Antwortart muss stimmen); sonst 0. Mittel über alle Antworten.
- Belegquote: Anteil der genannten Pflichtnormen (Paragraph + Gesetz, Absatz egal).
- Erfindungsquote: Anteil genannter Normen, die es nicht gibt. Belegt ist eine Norm,
  wenn sie auf der Positivliste steht (recht/belege.json plus gängige Fristnormen)
  oder, sofern daten/wissen.sqlite existiert, als geltende Norm in der Wissensbasis
  des Bundesrechts (pruefki/wissen). Ohne Wissensbasis gilt nur die Positivliste.
  Jede erfundene Norm zählt -1 in den Normenpunkten (Pflichttreffer minus Erfindungen).
- Brier: (sicherheit - richtig)^2; "sicher und falsch" (sicherheit >= 0,8 und
  nicht exakt) zählt doppelt. Ohne lesbare sicherheit wird 0,5 angenommen.
- Token/s: Median über alle Antworten mit Messwert.

Bei Antwortart rueckfrage wird das Fristende nicht verglichen.

Zeilen der Kette (Modellname mit „+rechner“, kette.py): Normen und Sicherheit kommen dort aus dem Code.
Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, Erfindungsquote, Brier und „sicher und
falsch“ messen bei der Kette den Rechner. Die Rangliste sagt das unter der Überschrift.

  python3 benchmark/fristen/bewerten.py [--ergebnisse DIR_ODER_DATEIEN ...] [--laeufe 3] [--ausgabe-dir DIR]
                                       [--nur-positivliste]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(WURZEL))
import prompt as P  # noqa: E402
import statistik as S  # noqa: E402
from pruefki.fristen.normen import positivliste, schluessel, treffer  # noqa: E402

BEREICHE = ("gesamt", "oeffentlich", "privat", "berechnen", "pruefen")
WISSEN_DB = WURZEL / "daten" / "wissen.sqlite"
NUR_POSITIVLISTE = False        # --nur-positivliste: Bewertung wie vor der Wissensbasis
KETTE = "+rechner"              # Namenszusatz der Kette (kette.SUFFIX)


@lru_cache(maxsize=1)
def _wissensbasis():
    """Wissensbasis des Bundesrechts, falls gebaut; sonst None (dann gilt nur die Positivliste)."""
    if not WISSEN_DB.exists():
        return None
    try:
        from pruefki.wissen.abruf import Wissensbasis
        return Wissensbasis(WISSEN_DB)
    except Exception as e:  # beschädigte oder alte Datei: wie bisher bewerten
        print(f"Hinweis: Wissensbasis nicht nutzbar ({e}), nur Positivliste.", file=sys.stderr)
        return None


def erfunden(schl: tuple[str, str]) -> bool:
    """(Paragraph, Gesetz) gilt als erfunden, wenn er weder auf der Positivliste steht noch (falls vorhanden)
    als geltende Norm in der Wissensbasis. Gesetze außerhalb des Bundesrechts (z. B. BayVwVfG) prüft nur die
    Positivliste."""
    if schl in positivliste():
        return False
    wb = None if NUR_POSITIVLISTE else _wissensbasis()
    return wb is None or not wb.existiert_schluessel(*schl)


def erfindungspruefung() -> str:
    wb = None if NUR_POSITIVLISTE else _wissensbasis()
    if wb is None:
        return "Positivliste"
    m = wb.meta()
    return (f"Positivliste + Wissensbasis ({m.get('gesetze')} Gesetze, {m.get('normen')} Normen, "
            f"gebaut {m.get('gebaut')})")


def bewerte_antwort(aufgabe: dict, zeile: dict) -> dict:
    """Bewertet eine einzelne Antwort gegen den Sollwert."""
    soll = aufgabe["sollwert"]
    roh = zeile.get("antwort_json")
    a = P.lies_antwort(roh) if isinstance(roh, dict) else P.lies_antwort(zeile.get("antwort"))
    erg = {"id": aufgabe["id"], "lauf": zeile.get("lauf"), "lesbar": a is not None, "exakt": False,
           "teilpunkte": 0.0, "pflicht_n": 0, "pflicht_treffer": 0, "normen_n": 0, "erfunden": 0,
           "sicherheit": 0.5, "brier": None, "sicher_falsch": False, "tokens_pro_s": zeile.get("tokens_pro_s"),
           "fehler": zeile.get("fehler")}
    pflicht = soll.get("normen_pflicht") or []
    erg["pflicht_n"] = len(pflicht)
    if a is not None:
        art_ok = a["antwortart"] == soll["antwortart"]
        if soll["antwortart"] == "rueckfrage":
            exakt = art_ok
        else:
            exakt = art_ok and a["fristende"] == soll["fristende"]
        erg["exakt"] = exakt
        if exakt:
            erg["teilpunkte"] = 1.0
        elif art_ok and a["fristende"] in (soll.get("teilpunkt_daten") or []):
            erg["teilpunkte"] = 0.5
        genannt: set = set()
        for n in a["normen"]:
            genannt |= schluessel(n)
        erg["normen_n"] = len(genannt)
        erg["erfunden"] = sum(1 for k in genannt if erfunden(k))
        erg["pflicht_treffer"] = sum(1 for p in pflicht if treffer(p, genannt))
        if a["sicherheit"] is not None:
            erg["sicherheit"] = a["sicherheit"]
    y = 1.0 if erg["exakt"] else 0.0
    gewicht = 2.0 if (erg["sicherheit"] >= 0.8 and not erg["exakt"]) else 1.0
    erg["sicher_falsch"] = gewicht == 2.0
    erg["brier"] = gewicht * (erg["sicherheit"] - y) ** 2
    return erg


def _bereich_passt(aufgabe: dict, bereich: str) -> bool:
    return (bereich == "gesamt" or aufgabe["split"] == bereich or aufgabe["typ"] == bereich)


def kennzahlen(aufgaben: dict[str, dict], bewertungen: list[dict], laeufe: int, bereich: str) -> dict:
    ids = [i for i, a in aufgaben.items() if _bereich_passt(a, bereich)]
    b = [x for x in bewertungen if x["id"] in set(ids)]
    je_aufgabe = defaultdict(list)
    for x in b:
        je_aufgabe[x["id"]].append(x)
    bestanden = sum(1 for i in ids
                    if len({x["lauf"] for x in je_aufgabe[i]}) >= laeufe and je_aufgabe[i]
                    and all(x["exakt"] for x in je_aufgabe[i]))
    pflicht_n = sum(x["pflicht_n"] for x in b)
    normen_n = sum(x["normen_n"] for x in b)
    tps = [x["tokens_pro_s"] for x in b if x.get("tokens_pro_s")]
    n = len(b)
    return {
        "aufgaben": len(ids),
        "antworten": n,
        "exakt_alle_laeufe": bestanden,
        "exakt_alle_laeufe_quote": round(bestanden / len(ids), 3) if ids else None,
        "exakt_einzeln_quote": round(sum(x["exakt"] for x in b) / n, 3) if n else None,
        "teilpunkte": round(sum(x["teilpunkte"] for x in b) / n, 3) if n else None,
        "belegquote": round(sum(x["pflicht_treffer"] for x in b) / pflicht_n, 3) if pflicht_n else None,
        "erfindungsquote": round(sum(x["erfunden"] for x in b) / normen_n, 3) if normen_n else 0.0,
        "normenpunkte": round(sum(x["pflicht_treffer"] - x["erfunden"] for x in b) / n, 3) if n else None,
        "brier": round(sum(x["brier"] for x in b) / n, 4) if n else None,
        "sicher_und_falsch": sum(x["sicher_falsch"] for x in b),
        "unlesbar_oder_fehler": sum((not x["lesbar"]) or bool(x["fehler"]) for x in b),
        "tokens_pro_s_median": round(statistics.median(tps), 1) if tps else None,
    }


def lade_ergebnisse(quellen: list[Path]) -> dict[str, list[dict]]:
    dateien: list[Path] = []
    for q in quellen:
        dateien += sorted(q.glob("*.jsonl")) if q.is_dir() else [q]
    je_modell: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for d in dateien:
        with open(d, encoding="utf-8") as fh:
            for z in fh:
                if not z.strip():
                    continue
                zeile = json.loads(z)
                # bei Wiederholungen gewinnt die letzte fehlerfreie Zeile je (id, lauf)
                schl = (zeile["id"], zeile["lauf"])
                alt = je_modell[zeile["modell"]].get(schl)
                if alt is None or alt.get("fehler") or not zeile.get("fehler"):
                    je_modell[zeile["modell"]][schl] = zeile
    return {m: list(v.values()) for m, v in je_modell.items()}


def aufgabe_kennung(aufgabe: dict) -> str:
    """Fingerabdruck einer Aufgabe aus Dokument und Frage. Seed v1 und Holdout nutzen dieselben IDs (F001 …); die
    Kennung in jeder Ergebniszeile der Kette verhindert, dass Zeilen gegen den falschen Satz zählen."""
    text = json.dumps([aufgabe.get("dokument"), aufgabe.get("frage")], ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def fremde_zeilen(aufgaben: dict[str, dict], zeilen: list[dict], kennungen: dict | None = None) -> list[str]:
    """IDs, deren Zeilen eine Kennung tragen, die nicht zur gleichnamigen Aufgabe dieses Satzes passt. Zeilen ohne
    Kennung (Einzelmodelle, ältere Läufe) zählen wie bisher."""
    kennungen = kennungen if kennungen is not None else {i: aufgabe_kennung(a) for i, a in aufgaben.items()}
    return sorted({z["id"] for z in zeilen if z.get("aufgabe_kennung") and z["id"] in kennungen
                   and z["aufgabe_kennung"] != kennungen[z["id"]]})


def bestanden_ids(aufgaben: dict[str, dict], bewertungen: list[dict], laeufe: int) -> list[str]:
    """Aufgaben, die in allen Läufen exakt sind (dieselbe Regel wie exakt_alle_laeufe)."""
    je_aufgabe = defaultdict(list)
    for x in bewertungen:
        je_aufgabe[x["id"]].append(x)
    return sorted(i for i in aufgaben if je_aufgabe[i] and len({x["lauf"] for x in je_aufgabe[i]}) >= laeufe
                  and all(x["exakt"] for x in je_aufgabe[i]))


def vergleiche(aufgaben: dict[str, dict], rang: dict) -> dict:
    """Jedes Modell gepaart gegen das beste (meiste bestandene Aufgaben), Aufgabe als Einheit."""
    if not rang:
        return {}
    ids = sorted(aufgaben)
    # Das Orakel (fehlerfreie Auslese) ist Messlatte des Rechners, kein Mitbewerber.
    kandidaten = [m for m in rang if not m.startswith("orakel")] or list(rang)
    bester = max(kandidaten, key=lambda m: (len(rang[m]["bestanden"]),
                                            rang[m]["bereiche"]["gesamt"]["teilpunkte"] or 0))
    a = set(rang[bester]["bestanden"])
    je = {}
    for m, r in rang.items():
        k = len(r["bestanden"])
        lo, hi = S.wilson(k, len(ids))
        je[m] = {"bestanden": k, "aufgaben": len(ids), "wilson95": [round(lo, 3), round(hi, 3)]}
        if m != bester:
            je[m].update(S.vergleich(a, set(r["bestanden"]), ids))
    return {"bester": bester, "modelle": je}


def bewerte(aufgaben: dict[str, dict], ergebnisse: dict[str, list[dict]], laeufe: int) -> dict:
    """Rangliste je Modell. ValueError, wenn Zeilen zu einem anderen Aufgabensatz gehören (Kennung passt nicht)."""
    kennungen = {i: aufgabe_kennung(a) for i, a in aufgaben.items()}
    rang = {}
    for modell, zeilen in ergebnisse.items():
        fremd = fremde_zeilen(aufgaben, zeilen, kennungen)
        if fremd:
            raise ValueError(f"{modell}: Zeilen zu {', '.join(fremd[:5])}{' …' if len(fremd) > 5 else ''} gehören zu "
                             "einem anderen Aufgabensatz (Kennung passt nicht). Passende --aufgaben angeben.")
        bew = [bewerte_antwort(aufgaben[z["id"]], z) for z in zeilen if z["id"] in aufgaben]
        rang[modell] = {
            "bereiche": {b: kennzahlen(aufgaben, bew, laeufe, b) for b in BEREICHE},
            "bestanden": bestanden_ids(aufgaben, bew, laeufe),
            "pro_aufgabe": {i: f"{sum(x['exakt'] for x in bew if x['id'] == i)}/"
                               f"{sum(1 for x in bew if x['id'] == i)}" for i in sorted(aufgaben)},
        }
    return rang


def _fmt(v, prozent=False):
    if v is None:
        return "—"
    if prozent:
        return f"{100 * v:.0f} %"
    return f"{v:g}" if isinstance(v, float) else str(v)


def markdown(rang: dict, laeufe: int, vergleich: dict | None = None) -> str:
    teile = [f"# Rangliste Fristen-Benchmark ({P.PROMPT_VERSION})", "",
             f"Hauptnote: Aufgabe zählt nur, wenn alle {laeufe} Läufe exakt sind (Antwortart und Fristende). "
             "Bewertung nur per Code.", "", f"Prüfung erfundener Normen: {erfindungspruefung()}.", ""]
    if any(KETTE in m for m in rang):
        teile += [f"Zeilen mit „{KETTE}“: Kette „Modell liest, Code rechnet“ (eigener Auslese-Prompt; Schema als "
                  f"Grammatik, bei „{KETTE}-json“ nur format json wie die Einzelmodelle). Normen und Sicherheit "
                  "kommen dort aus dem Code: Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, "
                  "Erfindungsquote, Brier und sicher+falsch messen dort den Rechner."
                  + (f" „{KETTE}-v3“: geschärfter Auslese-Prompt, Gegenproben im Code und höchstens eine gezielte "
                     "Nachfrage je Aufgabe (zweiter Modellaufruf)." if any(f"{KETTE}-v3" in m for m in rang) else ""),
                  ""]
    titel = {"gesamt": "Gesamt", "oeffentlich": "Öffentlich", "privat": "Privat", "berechnen": "Typ berechnen",
             "pruefen": "Typ prüfen"}
    for b in BEREICHE:
        zeilen = sorted(rang.items(), key=lambda kv: (-(kv[1]["bereiche"][b]["exakt_alle_laeufe"] or 0),
                                                       -(kv[1]["bereiche"][b]["teilpunkte"] or 0),
                                                       kv[1]["bereiche"][b]["brier"] or 9))
        teile += [f"## {titel[b]}", "",
                  "| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | "
                  "Brier | sicher+falsch | Token/s (Median) |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for modell, r in zeilen:
            k = r["bereiche"][b]
            teile.append(f"| {modell} | {k['exakt_alle_laeufe']}/{k['aufgaben']} | "
                         f"{_fmt(k['exakt_einzeln_quote'], True)} | {_fmt(k['teilpunkte'])} | "
                         f"{_fmt(k['belegquote'], True)} | {_fmt(k['erfindungsquote'], True)} | {_fmt(k['brier'])} | "
                         f"{k['sicher_und_falsch']} | {_fmt(k['tokens_pro_s_median'])} |")
        teile.append("")
    if vergleich:
        b = vergleich["bester"]
        teile += ["## Vergleich mit dem Besten (gepaart, Aufgabe als Einheit)", "",
                  f"Bezug: {b}. „nur Bester : nur Modell“ zählt die Aufgaben, die genau einer der beiden besteht; "
                  "p aus dem exakten McNemar-Test, Differenz als 95-%-Intervall (Bootstrap über Aufgaben). "
                  "Ab p < 0,05 gilt der Abstand als belegt, sonst gleichauf.", "",
                  "| Modell | bestanden | 95 % (Wilson) | nur Bester : nur Modell | p | Differenz (Prozentpunkte) | "
                  "Urteil |", "|---|---|---|---|---|---|---|"]
        for m, v in sorted(vergleich["modelle"].items(), key=lambda kv: -kv[1]["bestanden"]):
            w = f"{100 * v['wilson95'][0]:.0f}–{100 * v['wilson95'][1]:.0f} %"
            if m == b:
                teile.append(f"| {m} | {v['bestanden']}/{v['aufgaben']} | {w} | — | — | — | Bezug |")
                continue
            lo, hi = v["differenz_pp"]
            urteil = "Bester belegt besser" if v["p"] < 0.05 else "gleichauf (nicht trennbar)"
            p_text = "< 0.001" if v["p"] < 0.001 else f"{v['p']:.3f}"
            teile.append(f"| {m} | {v['bestanden']}/{v['aufgaben']} | {w} | {len(v['nur_a'])} : {len(v['nur_b'])} | "
                         f"{p_text} | {lo:+.0f} bis {hi:+.0f} | {urteil} |")
        teile.append("")
    return "\n".join(teile)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fristen-Benchmark bewerten (nur Code)")
    ap.add_argument("--aufgaben", type=Path, default=HIER / "aufgaben.jsonl")
    ap.add_argument("--ergebnisse", type=Path, nargs="+", default=[HIER / "ergebnisse"])
    ap.add_argument("--laeufe", type=int, default=3)
    ap.add_argument("--ausgabe-dir", type=Path, default=HIER)
    ap.add_argument("--modelle", nargs="*")
    ap.add_argument("--nur-positivliste", action="store_true", help="Wissensbasis nicht nutzen")
    args = ap.parse_args(argv)
    global NUR_POSITIVLISTE
    NUR_POSITIVLISTE = args.nur_positivliste
    with open(args.aufgaben, encoding="utf-8") as fh:
        aufgaben = {a["id"]: a for a in (json.loads(z) for z in fh if z.strip())}
    ergebnisse = lade_ergebnisse(args.ergebnisse)
    if args.modelle:
        ergebnisse = {m: v for m, v in ergebnisse.items() if m in set(args.modelle)}
    if not ergebnisse:
        print("Keine Ergebnisse gefunden.", file=sys.stderr)
        return 1
    try:
        rang = bewerte(aufgaben, ergebnisse, args.laeufe)
    except ValueError as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 2
    vergleich = vergleiche(aufgaben, rang)
    args.ausgabe_dir.mkdir(parents=True, exist_ok=True)
    (args.ausgabe_dir / "rangliste.json").write_text(
        json.dumps({"prompt_version": P.PROMPT_VERSION, "laeufe": args.laeufe,
                    "erfindungspruefung": erfindungspruefung(), "modelle": rang, "vergleich": vergleich},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    md = markdown(rang, args.laeufe, vergleich)
    (args.ausgabe_dir / "rangliste.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
