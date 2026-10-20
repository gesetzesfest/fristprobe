#!/usr/bin/env python3
"""Fehleranalyse der Kette „Modell liest, Code rechnet“: Welche Felder liest das Modell falsch aus?

Vergleicht je Antwort die ausgelesenen Felder (Spalte ``felder`` in ergebnisse/*+rechner.jsonl) mit den
wahren Feldern aus aufgaben.jsonl/parameter (kette.orakel_felder) und zählt je Feld, wie oft es falsch war.
„nötig“ heißt: Das Feld geht bei dieser Aufgabe in die Rechnung ein (so wie im Orakel-Lauf) und die
Abweichung ändert sie. „gleichwertig“ heißt: Die Felder weichen vom Orakel ab, ergeben aber dieselbe
Rechnung (gleiche Funktion, gleiche Argumente, bei Prüfaufgaben dasselbe genannte Datum), etwa
„persoenliche_uebergabe“ mit datum_zugang statt „zustellungsurkunde“ mit datum_zustellung. Solche Abweichungen
zählen nicht als „falsch, nötig“. Danach listet es die Aufgaben mit falschen Feldern und ob die Antwort
trotzdem exakt war.

Bei v3-Läufen (…+rechner-v3) ist ``felder`` das, womit gerechnet wurde (nach Gegenproben und Nachfrage);
``--quelle auslese`` vergleicht stattdessen die erste Auslese des Modells (Spalte ``felder_auslese``). Dazu
zählt die Analyse Nachfragen (gestellt, übernommen, je Feld) und Gegenproben je Regel.

  python3 benchmark/fristen/fehleranalyse.py [--ergebnisse DIR_ODER_DATEIEN ...] [--modelle M ...]
                                             [--laeufe 3] [--quelle felder|auslese]
                                             [--ausgabe PFAD.md] [--json PFAD.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import bewerten as B  # noqa: E402
import kette as K  # noqa: E402
import prompt_kette as PK  # noqa: E402


def lade_kette(quellen: list[Path]) -> dict[str, list[dict]]:
    """Zeilen der Kette je Modell (bei Wiederholungen gewinnt die letzte fehlerfreie Zeile je id und Lauf)."""
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
                if "felder" not in zeile and not str(zeile.get("modell", "")).endswith(K.SUFFIX):
                    continue
                schl = (zeile["id"], zeile["lauf"])
                alt = je_modell[zeile["modell"]].get(schl)
                if alt is None or alt.get("fehler") or not zeile.get("fehler"):
                    je_modell[zeile["modell"]][schl] = zeile
    return {m: sorted(v.values(), key=lambda x: (x["id"], x["lauf"])) for m, v in je_modell.items()}


def _wahr(aufgabe: dict) -> tuple[dict, list[str], set[str]]:
    wahr, pruefbar = K.orakel_felder(aufgabe)
    noetig = set(K.rechne(wahr, aufgabe["typ"], aufgabe.get("frage", ""))["rechnung"]["benutzt"])
    return wahr, pruefbar, noetig


def _abbildung(aufgabe: dict, felder: dict) -> tuple:
    """Was der Code aus den Feldern rechnet: (Funktion, Argumente, genanntes Datum bei Prüfaufgaben)."""
    r = K.rechne(felder, aufgabe["typ"], aufgabe.get("frage", ""))["rechnung"]
    genannt = felder.get("genanntes_fristende") if aufgabe["typ"] == "pruefen" else None
    return r["funktion"], r["argumente"], genannt


def vergleiche(aufgabe: dict, felder: dict) -> list[dict]:
    """Falsch ausgelesene Felder einer Antwort: [{feld, soll, ist, noetig, gleichwertig}].

    noetig: Das Feld geht in die Rechnung ein und die Rechnung weicht vom Orakel ab."""
    wahr, pruefbar, noetig = _wahr(aufgabe)
    diffs = [n for n in pruefbar if not K.gleich(n, wahr[n], felder.get(n))]
    gleichwertig = bool(diffs) and _abbildung(aufgabe, felder) == _abbildung(aufgabe, wahr)
    return [{"feld": n, "soll": wahr[n], "ist": felder.get(n), "noetig": n in noetig and not gleichwertig,
             "gleichwertig": gleichwertig} for n in diffs]


def analysiere(aufgaben: dict[str, dict], zeilen: list[dict], laeufe: int = 3, quelle: str = "felder") -> dict:
    """quelle: "felder" (womit gerechnet wurde) oder "auslese" (erste Auslese des Modells, nur v3-Zeilen).
    ValueError, wenn Zeilen zu einem anderen Aufgabensatz gehören (bewerten.fremde_zeilen)."""
    fremd = B.fremde_zeilen(aufgaben, zeilen)
    if fremd:
        raise ValueError(f"Zeilen zu {', '.join(fremd[:5])} gehören zu einem anderen Aufgabensatz (Kennung passt "
                         "nicht). Passende --aufgaben angeben.")
    nachfragen: Counter = Counter()
    nachfragen_ok: Counter = Counter()
    gegenproben: Counter = Counter()
    felder_stat = {n: {"geprueft": 0, "falsch": 0, "falsch_noetig": 0, "gleichwertig": 0, "aufgaben": Counter()}
                   for n in PK.FELDNAMEN}
    je_aufgabe: dict[str, dict] = {}
    antworten = unlesbar = fehler = 0
    for z in zeilen:
        a = aufgaben.get(z["id"])
        if a is None:
            continue
        ja = je_aufgabe.setdefault(z["id"], {"art": a["art"], "typ": a["typ"], "laeufe": 0, "exakt": 0,
                                             "falsch": defaultdict(list), "unlesbar": 0, "fehler": 0})
        ja["laeufe"] += 1
        if K.ist_exakt(a, z.get("antwort_json")):
            ja["exakt"] += 1
        antworten += 1
        if z.get("fehler"):
            fehler += 1
            ja["fehler"] += 1
            continue
        nf = z.get("nachfrage")
        if nf:
            nachfragen[nf.get("feld")] += 1
            nachfragen_ok[nf.get("feld")] += bool(nf.get("uebernommen"))
        for e in z.get("gegenproben") or []:
            gegenproben[e.get("regel")] += 1
        felder = z.get("felder_auslese") if quelle == "auslese" and "felder_auslese" in z else z.get("felder")
        if felder is None:
            unlesbar += 1
            ja["unlesbar"] += 1
            continue
        _, pruefbar, _ = _wahr(a)
        for n in pruefbar:
            felder_stat[n]["geprueft"] += 1
        for d in vergleiche(a, felder):
            s = felder_stat[d["feld"]]
            s["falsch"] += 1
            s["falsch_noetig"] += int(d["noetig"])
            s["gleichwertig"] += int(d["gleichwertig"])
            s["aufgaben"][z["id"]] += 1
            ja["falsch"][d["feld"]].append({"soll": d["soll"], "ist": d["ist"], "noetig": d["noetig"],
                                            "gleichwertig": d["gleichwertig"]})
    voll = sum(1 for v in je_aufgabe.values() if v["laeufe"] >= laeufe and v["exakt"] == v["laeufe"])
    return {
        "antworten": antworten, "unlesbar": unlesbar, "fehler": fehler,
        "exakt_alle_laeufe": f"{voll}/{len(aufgaben)}", "quelle": quelle,
        "nachfragen": {"gestellt": sum(nachfragen.values()), "uebernommen": sum(nachfragen_ok.values()),
                       "je_feld": {f: [nachfragen[f], nachfragen_ok[f]] for f in sorted(nachfragen)}},
        "gegenproben": dict(sorted(gegenproben.items())),
        "felder": {n: {**s, "aufgaben": dict(s["aufgaben"])} for n, s in felder_stat.items() if s["geprueft"]},
        "aufgaben": {i: {**v, "falsch": dict(v["falsch"])} for i, v in sorted(je_aufgabe.items())},
    }


def _wert(v) -> str:
    return "null" if v is None else str(v)


def markdown(ergebnis: dict[str, dict]) -> str:
    teile = ["# Fehleranalyse der Kette (Modell liest, Code rechnet)", "",
             "Vergleich der ausgelesenen Felder mit den wahren Feldern aus aufgaben.jsonl/parameter. "
             "„nötig“: Das Feld geht bei dieser Aufgabe in die Rechnung ein und die Abweichung ändert sie. "
             "„gleichwertig“: anders gelesen, aber dieselbe Rechnung wie mit den wahren Feldern.", ""]
    for modell, an in ergebnis.items():
        teile += [f"## {modell}", "",
                  f"Antworten: {an['antworten']}, unlesbar: {an['unlesbar']}, Fehler: {an['fehler']}, "
                  f"exakt in allen Läufen: {an['exakt_alle_laeufe']}", ""]
        nf = an.get("nachfragen") or {}
        if nf.get("gestellt") or an.get("gegenproben"):
            je = ", ".join(f"{f} {g}/{u}" for f, (g, u) in nf.get("je_feld", {}).items()) or "—"
            gp = ", ".join(f"{r} {k}" for r, k in an.get("gegenproben", {}).items()) or "—"
            teile += [f"Nachfragen: {nf.get('gestellt', 0)}, davon Wert übernommen: {nf.get('uebernommen', 0)} "
                      f"(je Feld gestellt/übernommen: {je}). Gegenproben je Regel: {gp}. Verglichen: "
                      f"{'erste Auslese' if an.get('quelle') == 'auslese' else 'Felder der Rechnung'}.", ""]
        teile += ["| Feld | geprüft | falsch | davon nötig | davon gleichwertig | Quote | Aufgaben (Anzahl falsch) |",
                  "|---|---|---|---|---|---|---|"]
        for n, s in sorted(an["felder"].items(), key=lambda kv: (-kv[1]["falsch_noetig"], -kv[1]["falsch"],
                                                                  PK.FELDNAMEN.index(kv[0]))):
            quote = f"{100 * s['falsch'] / s['geprueft']:.0f} %" if s["geprueft"] else "—"
            ids = ", ".join(f"{i} ({k})" for i, k in sorted(s["aufgaben"].items())) or "—"
            teile.append(f"| {n} | {s['geprueft']} | {s['falsch']} | {s['falsch_noetig']} | {s['gleichwertig']} | "
                         f"{quote} | {ids} |")
        teile += ["", "### Aufgaben mit falsch gelesenen Feldern", ""]
        if not any(v["falsch"] or v["unlesbar"] or v["fehler"] for v in an["aufgaben"].values()):
            teile += ["Keine.", ""]
            continue
        teile += ["| Aufgabe | art | typ | exakt | falsche Felder (soll -> ist, Anzahl) |", "|---|---|---|---|---|"]
        for i, v in an["aufgaben"].items():
            if not v["falsch"] and not v["unlesbar"] and not v["fehler"]:
                continue
            teile_f = []
            for n, liste in v["falsch"].items():
                ist = Counter(_wert(x["ist"]) for x in liste)
                stern = ("" if any(x["noetig"] for x in liste)
                         else " (gleichwertig)" if all(x.get("gleichwertig") for x in liste) else " (nicht nötig)")
                teile_f.append(f"{n}{stern}: {_wert(liste[0]['soll'])} -> "
                               + ", ".join(f"{w} ({k}x)" for w, k in ist.most_common()))
            if v["unlesbar"]:
                teile_f.append(f"unlesbar ({v['unlesbar']}x)")
            if v["fehler"]:
                teile_f.append(f"Fehler ({v['fehler']}x)")
            teile.append(f"| {i} | {v['art']} | {v['typ']} | {v['exakt']}/{v['laeufe']} | {'; '.join(teile_f)} |")
        teile.append("")
    return "\n".join(teile)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fehleranalyse der Kette: falsch ausgelesene Felder zählen")
    ap.add_argument("--aufgaben", type=Path, default=HIER / "aufgaben.jsonl")
    ap.add_argument("--ergebnisse", type=Path, nargs="+", default=[HIER / "ergebnisse"])
    ap.add_argument("--modelle", nargs="*")
    ap.add_argument("--laeufe", type=int, default=3)
    ap.add_argument("--quelle", choices=["felder", "auslese"], default="felder",
                    help="felder: womit gerechnet wurde; auslese: erste Auslese des Modells (v3)")
    ap.add_argument("--ausgabe", type=Path, help="Markdown zusätzlich in diese Datei schreiben")
    ap.add_argument("--json", type=Path, help="Ergebnis als JSON in diese Datei schreiben")
    args = ap.parse_args(argv)
    with open(args.aufgaben, encoding="utf-8") as fh:
        aufgaben = {a["id"]: a for a in (json.loads(z) for z in fh if z.strip())}
    zeilen = lade_kette(args.ergebnisse)
    if args.modelle:
        zeilen = {m: v for m, v in zeilen.items() if m in set(args.modelle)}
    if not zeilen:
        print("Keine Ergebnisse der Kette gefunden (Dateien *+rechner.jsonl).", file=sys.stderr)
        return 1
    try:
        ergebnis = {m: analysiere(aufgaben, z, args.laeufe, args.quelle) for m, z in sorted(zeilen.items())}
    except ValueError as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 2
    md = markdown(ergebnis)
    if args.ausgabe:
        args.ausgabe.write_text(md + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
