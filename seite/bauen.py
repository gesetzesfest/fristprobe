#!/usr/bin/env python3
"""Baut die Benchmark-Seite Fristprobe als statische Mehrseiten-Site aus den Ranglisten im Repo. Nur Standardbibliothek.

Für Kunden und für KI-Agenten zugleich:
- Alles Wichtige steht als Text im HTML. GPTBot, ClaudeBot und PerplexityBot führen kein JavaScript aus.
- Je Seite ein Thema, eine H1, Fragen als H2, die ersten zwei Sätze beantworten die Frage, Stand und Code-Version sichtbar.
- Echte HTML-Tabellen, Daten als CSV und JSON mit festen Namen, robots.txt erlaubt die Such-Crawler.

Ausgabe: seite/dist/ (zum Hochladen) und seite/vorschau.html (Startseite ohne Kopf, für das private Artefakt).
Aufruf: python3 seite/bauen.py
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from datetime import date
from html import escape
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
ERG = WURZEL / "benchmark" / "fristen" / "ergebnisse"
DIST = WURZEL / "seite" / "dist"
BESTES = "qwen3:8b+rechner-v3"
DACH = "Gesetzesfest"     # Marke und Domain gesetzesfest.de
KONTAKT = "[Kontaktadresse]"
URL = "https://gesetzesfest.de"
FRISCH = ["windows-frisch20261018", "windows-frisch20261019", "windows-frisch20261020", "windows-frisch20261021",
          "windows-frisch20261022", "windows-frisch20261023", "mac-vorlagen2-20261025", "mac-vorlagen2-20261026",
          "mac-vorlagen2-20261027", "mac-vorlagen2-20261028", "mac-vorlagen2-20261029"]
NAMEN = {"qwen3:8b+rechner-v3": "Qwen3 8B", "qwen3.5:9b+rechner-v3": "Qwen3.5 9B",
         "gemma3:4b+rechner-v3": "Gemma 3 4B", "qwen3:4b+rechner-v3": "Qwen3 4B",
         "gemma4:e4b-it-qat+rechner-v3": "Gemma 4 E4B", "qwen3:8b+rechner": "Qwen3 8B (ältere Kette v2)",
         "orakel+rechner-v3": "Obergrenze: fehlerfreies Auslesen"}
BEISPIEL = ("vorlagen2/aufgaben_seed20261026.jsonl", "F012")
FAMILIEN = ["Widerspruch nach SGB II", "Widerspruch nach VwVfG", "Einspruch nach AO", "Klage vor dem Sozialgericht",
            "Klage vor dem Verwaltungsgericht", "Kündigungsschutzklage", "Kündigung Arbeitsvertrag",
            "Kündigung Mietvertrag", "Jahresfrist ohne Belehrung"]
NAV = [("rangliste.html", "Rangliste"), ("pruefreihe-fristen.html", "Prüfreihen"), ("methode.html", "Methode"),
       ("daten.html", "Daten"), ("faq.html", "FAQ"), ("ueber.html", "Über uns")]


# ----------------------------------------------------------------- Daten

def lies(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def wilson(k: int, n: int, z: float = 1.959964) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    nenner = 1 + z * z / n
    mitte = (p + z * z / (2 * n)) / nenner
    breite = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / nenner
    return [round(max(0.0, mitte - breite), 3), round(min(1.0, mitte + breite), 3)]


def prozent(x: float, stellen: int = 0) -> str:
    return f"{x * 100:.{stellen}f}".replace(".", ",") + " %"


def rangliste() -> list[dict]:
    d = lies(ERG / "holdout" / "rangliste.json")
    vgl = d.get("vergleich", {}).get("modelle", {})
    zeilen = []
    for name, m in d["modelle"].items():
        g = m["bereiche"]["gesamt"]
        zeilen.append({"id": name, "name": NAMEN.get(name, name), "orakel": name.startswith("orakel"),
                       "bester": name == BESTES, "k": g["exakt_alle_laeufe"], "n": g["aufgaben"],
                       "wilson": vgl.get(name, {}).get("wilson95") or wilson(g["exakt_alle_laeufe"], g["aufgaben"]),
                       "p": vgl.get(name, {}).get("p"), "falsch": g["sicher_und_falsch"],
                       "erfunden": g["erfindungsquote"], "tokens": g.get("tokens_pro_s_median")})
    zeilen.sort(key=lambda z: (z["orakel"], -z["k"], z["falsch"]))
    return zeilen


def frisch() -> dict:
    seeds = []
    for ordner in FRISCH:
        g = lies(ERG / ordner / "rangliste.json")["modelle"][BESTES]["bereiche"]["gesamt"]
        seeds.append({"seed": ordner[-8:], "v2": "vorlagen2" in ordner, "k": g["exakt_alle_laeufe"],
                      "n": g["aufgaben"], "falsch": g["sicher_und_falsch"]})
    k, n = sum(s["k"] for s in seeds), sum(s["n"] for s in seeds)
    return {"seeds": seeds, "k": k, "n": n, "wilson": wilson(k, n), "falsch": sum(s["falsch"] for s in seeds)}


def beispiel() -> dict:
    """Beispielaufgabe aus dem Satz; ohne den Satz (öffentliche Kopie) aus seite/beispiel.json."""
    datei, kennung = BEISPIEL
    quelle, ablage = WURZEL / "benchmark" / "fristen" / datei, WURZEL / "seite" / "beispiel.json"
    if not quelle.exists():
        return json.loads(ablage.read_text(encoding="utf-8"))
    for zeile in quelle.read_text(encoding="utf-8").splitlines():
        d = json.loads(zeile)
        if d["id"] == kennung:
            ablage.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return d
    raise SystemExit(f"Beispiel {kennung} fehlt in {datei}")


def code_stand() -> str:
    try:
        return subprocess.run(["git", "-C", str(WURZEL), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unbekannt"


def datum_de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


# ----------------------------------------------------------------- Gestaltung

CSS = """
:root{--papier:#fbfaf6;--grund:#f2f1ec;--tinte:#16181a;--leise:#585e5a;--linie:#d6d3c9;--tanne:#1f4a3d;
--tanne-hell:#dfe9e3;--rot:#a2362c;--f-kopf:"Newsreader",Georgia,serif;--f-text:"Hanken Grotesk",system-ui,sans-serif;
--f-zahl:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--papier:#131514;--grund:#0e100f;--tinte:#e9e8e3;
--leise:#a3a8a4;--linie:#2c312e;--tanne:#8fc7ae;--tanne-hell:#1b2b24;--rot:#f08a7e;color-scheme:dark}}
:root[data-theme="dark"]{--papier:#131514;--grund:#0e100f;--tinte:#e9e8e3;--leise:#a3a8a4;--linie:#2c312e;--tanne:#8fc7ae;
--tanne-hell:#1b2b24;--rot:#f08a7e;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--papier);color:var(--tinte);font-family:var(--f-text);font-size:17px;line-height:1.6;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 56px}
.blatt{max-width:1120px;margin:0 auto}
h1,h2,h3{font-family:var(--f-kopf);font-weight:600;line-height:1.1;margin:0;text-wrap:balance}
p{margin:0}
a{color:var(--tanne)}
.zahl{font-family:var(--f-zahl);font-variant-numeric:tabular-nums}
.klein{font-size:.85rem;color:var(--leise)}
.kopf{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px 28px;padding-block:20px 12px;border-bottom:2px solid var(--tinte)}
.marke{font-family:var(--f-kopf);font-weight:700;font-size:2rem;letter-spacing:-.01em;text-decoration:none;color:var(--tinte);line-height:1.1}
.marke small{display:block;font-family:var(--f-text);font-weight:500;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--leise)}
.kopf nav{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:.95rem;align-items:baseline}
.kopf nav a{color:var(--tinte);text-decoration:none;border-bottom:1px solid transparent}
.kopf nav a:hover,.kopf nav a:focus-visible,.kopf nav a[aria-current]{border-bottom-color:var(--tinte);outline:none}
.kopf nav a.knopf{color:var(--papier);background:var(--tanne);padding:6px 14px;border:none}
.stempel{font-family:var(--f-zahl);font-size:.8rem;color:var(--tanne)}
.auftakt{padding-block:40px 28px;border-bottom:1px solid var(--linie);display:grid;gap:14px;max-width:820px}
.auftakt h1{font-size:clamp(2.2rem,5vw,3.6rem)}
.antwort{font-size:1.2rem;line-height:1.5}
.antwort b{font-weight:600}
section{padding-block:40px 6px;display:grid;gap:16px;scroll-margin-top:8px}
section>header{display:grid;gap:6px;max-width:74ch}
section h2{font-size:clamp(1.7rem,3.6vw,2.4rem)}
.etikett{font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:var(--leise);font-weight:500}
.tabelle{overflow-x:auto;border-top:2px solid var(--tinte);border-bottom:1px solid var(--tinte)}
table{width:100%;border-collapse:collapse;min-width:760px}
caption{text-align:left;padding:10px 0;color:var(--leise);font-size:.88rem;caption-side:bottom}
th{text-align:left;font-weight:500;font-size:.74rem;letter-spacing:.08em;text-transform:uppercase;color:var(--leise);padding:12px 10px;border-bottom:1px solid var(--linie);white-space:nowrap}
td{padding:12px 10px;border-bottom:1px solid var(--linie);vertical-align:middle}
tr:last-child td{border-bottom:none}
td.r,th.r{text-align:right}
td.modell{font-weight:500;white-space:nowrap}
tr.bester td.modell{color:var(--tanne);font-weight:700}
tr.orakel td{color:var(--leise);font-style:italic}
.balken{position:relative;height:18px;min-width:200px}
.balken .spur{position:absolute;left:0;right:0;top:8px;height:2px;background:var(--linie)}
.balken .ki{position:absolute;top:4px;height:10px;border:1px solid var(--leise);background:var(--grund)}
.balken .wert{position:absolute;top:1px;width:3px;height:16px;margin-left:-1px;background:var(--tinte)}
tr.bester .balken .ki{border-color:var(--tanne);background:var(--tanne-hell)}
tr.bester .balken .wert{background:var(--tanne)}
.achse{position:relative;height:14px;font-family:var(--f-zahl);font-size:.68rem;color:var(--leise)}
.achse span{position:absolute;transform:translateX(-50%)}
.falsch{color:var(--rot);font-weight:600}
.raster{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 28px}
.feld{border-top:2px solid var(--tinte);padding-block:12px 18px;display:grid;gap:8px;align-content:start}
.feld h3{font-size:1.3rem}
.feld.offen{border-top-style:dotted}
.schritte{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 28px;counter-reset:s}
.schritt{counter-increment:s;border-top:1px solid var(--linie);padding-top:12px;display:grid;gap:6px}
.schritt::before{content:counter(s);font-family:var(--f-kopf);font-weight:700;font-size:2rem;line-height:1;color:var(--tanne)}
.saetze{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px}
.satz{border:1px solid var(--linie);padding:10px 12px;display:grid;gap:2px}
.satz b{font-family:var(--f-zahl);font-size:1.2rem;font-weight:500}
.satz.fehlt b{color:var(--rot)}
.familien{display:flex;flex-wrap:wrap;gap:8px}
.familien span{border:1px solid var(--linie);padding:3px 12px;font-size:.9rem}
.beispiel{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px}
.akte{background:var(--grund);border:1px solid var(--linie);padding:18px 20px;font-family:var(--f-zahl);font-size:.78rem;line-height:1.55;white-space:pre-wrap;overflow:auto;max-height:34rem;margin:0}
.weg ol{margin:10px 0 0;padding-left:1.3em;display:grid;gap:8px;font-size:.95rem}
.loesung{margin-top:16px;border-top:2px solid var(--tinte);padding-top:10px;display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline}
.loesung b{font-family:var(--f-kopf);font-size:2rem}
.frage{border-top:1px solid var(--linie);padding-block:16px;display:grid;gap:6px;max-width:74ch}
.frage h2{font-size:1.35rem}
.kasten{border:2px solid var(--tanne);padding:22px 24px;display:grid;gap:10px}
.kasten ul,.liste{margin:0;padding-left:1.1em;display:grid;gap:6px}
pre.code{background:var(--grund);border:1px solid var(--linie);padding:14px 16px;font-family:var(--f-zahl);font-size:.8rem;overflow-x:auto;margin:0;white-space:pre-wrap}
.weiter{font-weight:600}
footer{margin-top:56px;border-top:2px solid var(--tinte);padding-top:14px;display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 24px;font-size:.86rem;color:var(--leise)}
footer nav{display:flex;flex-wrap:wrap;gap:4px 16px}
footer a{color:var(--leise)}
@media (max-width:780px){body{font-size:16px}.beispiel,.schritte{grid-template-columns:1fr}.schritt{padding-bottom:14px}}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" '
         'crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;'
         '6..72,600;6..72,700&amp;family=Hanken+Grotesk:wght@400;500;600;700&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap">')

LO, HI = 0.5, 1.0


def pos(x: float) -> float:
    return round((max(LO, min(HI, x)) - LO) / (HI - LO) * 100, 2)


def kopf(aktiv: str) -> str:
    links = "".join(f'<a href="{h}"{" aria-current=\"page\"" if h == aktiv else ""}>{t}</a>' for h, t in NAV)
    return (f'<header class="kopf"><a class="marke" href="./">{escape(DACH)}<small>Prüfreihe 1 · Fristprobe</small></a>'
            f'<nav aria-label="Hauptmenü">{links}<a class="knopf" href="pruefen-lassen.html">Prüfen lassen</a></nav></header>')


def fuss(stand: str, code: str) -> str:
    links = "".join(f'<a href="{h}">{t}</a>' for h, t in NAV + [("zitieren.html", "Zitieren"),
                                                               ("pruefen-lassen.html", "Prüfen lassen")])
    return (f'<footer><span>Fristprobe · Stand {stand} · Code {escape(code)} · alle Fälle erfunden · keine Rechtsberatung</span>'
            f'<nav aria-label="Fußmenü">{links}</nav></footer>')


def auftakt(etikett: str, h1: str, antwort: str, stand: str, code: str, n: int) -> str:
    return (f'<div class="auftakt"><span class="etikett">{escape(etikett)}</span><h1>{escape(h1)}</h1>'
            f'<p class="antwort">{antwort}</p><p class="stempel">Stand {stand} · Code {escape(code)} · {n} frische Fälle</p></div>')


def zeile_rang(i: int, z: dict) -> str:
    q = z["k"] / z["n"]
    lo, hi = z["wilson"]
    klasse = "bester" if z["bester"] else ("orakel" if z["orakel"] else "")
    tok = "–" if z["tokens"] is None else f"{z['tokens']:.1f}".replace(".", ",")
    falsch = f'<span class="falsch">{z["falsch"]}</span>' if z["falsch"] else "0"
    beschr = f"{prozent(q)} bestanden, 95-%-Intervall {prozent(lo, 1)} bis {prozent(hi, 1)}"
    return (f'<tr class="{klasse}"><td class="zahl">{"–" if z["orakel"] else i}</td><td class="modell">{escape(z["name"])}</td>'
            f'<td class="r zahl">{z["k"]}/{z["n"]}</td>'
            f'<td><div class="balken" role="img" aria-label="{beschr}" title="{beschr}"><span class="spur"></span>'
            f'<span class="ki" style="left:{pos(lo)}%;width:{round(pos(hi) - pos(lo), 2)}%"></span>'
            f'<span class="wert" style="left:{pos(q)}%"></span></div></td>'
            f'<td class="r zahl">{prozent(lo)}–{prozent(hi)}</td><td class="r zahl">{falsch}</td>'
            f'<td class="r zahl">{prozent(z["erfunden"])}</td><td class="r zahl">{tok}</td></tr>')


def tabelle(r: list[dict], nur: int | None = None) -> str:
    achse = "".join(f'<span style="left:{pos(v)}%">{int(v * 100)} %</span>' for v in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0))
    zeilen = [z for z in r if not (nur and z["orakel"])][:nur] if nur else r
    rang = "".join(zeile_rang(i, z) for i, z in enumerate(zeilen, 1))
    return (f'<div class="tabelle"><table><caption>Geheimer Testsatz: 50 Aufgaben, je dreimal gestellt. Bestanden heißt: alle drei '
            f'Antworten exakt. „Sicher falsch“: falsche Antwort mit hoher Sicherheit. Intervall: 95 % nach Wilson, Achse ab 50 %.</caption>'
            f'<thead><tr><th>#</th><th>Modell (lokal, mit Rechner)</th><th class="r">bestanden</th><th><div class="achse">{achse}</div></th>'
            f'<th class="r">95-%-Intervall</th><th class="r">sicher falsch</th><th class="r">erfundene Normen</th>'
            f'<th class="r">Token/s</th></tr></thead><tbody>{rang}</tbody></table></div>')


def seite(datei: str, titel: str, beschreibung: str, inhalt: str, stand: str, code: str, jsonld: str = "") -> str:
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    return (f'<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            f"<title>{escape(titel)}</title>\n<meta name=\"description\" content=\"{escape(beschreibung)}\">\n"
            f'<link rel="canonical" href="{URL}/{datei}">\n{FONTS}\n<style>{CSS}</style>\n{ld}\n</head>\n<body>\n'
            f'<div class="blatt">{kopf(datei)}<main>{inhalt}</main>{fuss(stand, code)}</div>\n</body>\n</html>\n')


# ----------------------------------------------------------------- Seiten

def seiten(r, f, b, stand, stand_iso, code) -> dict[str, tuple[str, str, str, str]]:
    best = next(z for z in r if z["bester"])
    lo, hi = prozent(f["wilson"][0], 1), prozent(f["wilson"][1], 1)
    kern = (f"<b>{best['name']} mit Rechner</b> löst <b>{f['k']} von {f['n']}</b> frischen deutschen Fristfällen richtig "
            f"(95-%-Intervall {lo} bis {hi}), ohne erfundene Norm. Kleinere Modelle geben bis zu "
            f"{max(z['falsch'] for z in r)} sicher klingende, aber falsche Antworten.")
    p = {}

    # Startseite
    kunden = [("KI-Firmen und Modellanbieter", "Wisst vor dem Release, ob euer Modell deutsche Fristen sicher rechnet. Prüflauf auf dem geheimen Testteil, mit Bericht und Intervallen.", "pruefen-lassen.html", "Prüflauf anfragen"),
              ("Legal-Tech und Kanzleisoftware", "Belegt die Qualität eures Produkts mit einer unabhängigen Messung statt mit Werbeversprechen.", "pruefen-lassen.html", "Produkt prüfen lassen"),
              ("Behörden und IT-Dienstleister", "Vergleicht Modelle vor der Beschaffung. Ab 02.12.2027 verlangt der AI Act für Hochrisiko-KI Nachweise zur Genauigkeit.", "pruefen-lassen.html", "Vergleich anfragen"),
              ("Forschung und Presse", "Offene Rangliste, Methode und Daten. Jede Zahl mit Datum, Version und Quelle zum Zitieren.", "daten.html", "Daten und Zitieren")]
    kunden_html = "".join(f'<div class="feld"><h3>{escape(t)}</h3><p>{escape(x)}</p><a class="weiter" href="{h}">{escape(c)} →</a></div>'
                          for t, x, h, c in kunden)
    p["index.html"] = ("Gesetzesfest · Welche KI rechnet deutsche Fristen richtig?",
                       f"Unabhängiger Benchmark für deutsche Rechts-KI: {f['k']} von {f['n']} frischen Fristfällen, Rangliste mit Intervallen, Methode, Daten, Prüfläufe.",
                       auftakt("Unabhängiger Prüfstand für deutsche Rechts-KI", "Welche KI rechnet deutsche Fristen richtig?", kern, stand, code, f["n"])
                       + f'<section aria-labelledby="t1"><header><h2 id="t1">Die Rangliste auf einen Blick</h2>'
                         f'<p class="klein">Die fünf besten lokalen Modelle auf dem geheimen Testsatz. Alle Zeilen, frische Sätze und Downloads auf der Ranglisten-Seite.</p></header>'
                       + tabelle(r, 5) + '<a class="weiter" href="rangliste.html">Ganze Rangliste →</a></section>'
                       + f'<section aria-labelledby="t2"><header><h2 id="t2">Für wen ist Fristprobe?</h2></header><div class="raster">{kunden_html}</div></section>'
                       + '<section aria-labelledby="t3"><header><h2 id="t3">Wie wird gemessen?</h2></header><div class="schritte">'
                         '<div class="schritt"><h3>Fall erzeugen</h3><p>Ein Generator schreibt erfundene Bescheide, Kündigungen und Klagen im Aufbau echter Schreiben.</p></div>'
                         '<div class="schritt"><h3>Modell antwortet</h3><p>Das Modell liest den Fall und nennt Fristende und Normen. Fehlt eine Angabe, darf es nachfragen.</p></div>'
                         '<div class="schritt"><h3>Programm prüft</h3><p>Ein Rechner nach §§ 187 bis 193 BGB bestimmt das richtige Datum. Keine KI entscheidet, was stimmt.</p></div>'
                         '</div><a class="weiter" href="methode.html">Zur Methode →</a></section>'
                       + '<section aria-labelledby="t4"><header><h2 id="t4">Ist Fristprobe unabhängig?</h2></header>'
                         '<p style="max-width:74ch">Ja. Niemand bezahlt uns für die öffentliche Rangliste, es gibt keine Werbung und keine gekauften Plätze. '
                         'Bezahlte Prüfläufe für Firmen ändern nie die öffentlichen Ergebnisse.</p><a class="weiter" href="ueber.html">Wer dahintersteht →</a></section>',
                       json.dumps({"@context": "https://schema.org", "@type": "Organization", "name": DACH,
                                   "description": "Unabhängiger deutscher Prüfstand für Rechts-KI", "url": URL},
                                  ensure_ascii=False))

    # Rangliste
    saetze = "".join(f'<div class="satz{" fehlt" if s["k"] < s["n"] else ""}"><b>{s["k"]}/{s["n"]}</b>'
                     f'<span class="klein">Satz {s["seed"][-4:]}{" · echte Layouts" if s["v2"] else ""}</span></div>'
                     for s in f["seeds"])
    ds = {"@context": "https://schema.org", "@type": "Dataset", "name": "Fristprobe · Rangliste Prüfreihe 1: Fristen berechnen",
          "description": f"Ergebnisse lokaler KI-Modelle bei deutschen Fristberechnungen. {best['name']} mit Rechner: {f['k']}/{f['n']} frische Fälle richtig.",
          "inLanguage": "de", "dateModified": stand_iso, "isAccessibleForFree": True, "url": f"{URL}/rangliste.html",
          "creator": {"@type": "Organization", "name": "Fristprobe"},
          "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{URL}/rangliste.csv"},
                           {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{URL}/rangliste.json"}],
          "variableMeasured": ["bestanden (alle drei Läufe exakt)", "95-%-Wilson-Intervall", "sicher und falsch", "erfundene Normen"]}
    p["rangliste.html"] = ("Rangliste · Welche KI rechnet deutsche Fristen am zuverlässigsten? · Gesetzesfest",
                           f"{best['name']} mit Rechner führt: {best['k']}/{best['n']} auf dem geheimen Testsatz, {f['k']}/{f['n']} auf frischen Fällen. Alle Modelle mit Intervallen.",
                           auftakt("Rangliste", "Welche KI rechnet deutsche Fristen am zuverlässigsten?",
                                   f"<b>{best['name']} mit Rechner</b> besteht <b>{best['k']} von {best['n']}</b> Aufgaben des geheimen Testsatzes und gibt keine sicher-falsche Antwort. Am schwächsten ist Gemma 4 E4B mit 37 von 50.",
                                   stand, code, f["n"])
                           + '<section aria-labelledby="t1"><header><h2 id="t1">Alle Modelle im Vergleich</h2></header>' + tabelle(r)
                           + '<p class="klein">Unterschiede gelten erst bei p &lt; 0,05 (McNemar-Test, gepaart je Aufgabe) als belegt. Daten: <a href="rangliste.csv">CSV</a> · <a href="rangliste.json">JSON</a>.</p></section>'
                           + f'<section aria-labelledby="t2"><header><h2 id="t2">Wie stabil ist das beste Modell auf neuen Fällen?</h2>'
                             f'<p>Sehr stabil: {f["k"]} von {f["n"]} frischen Fällen richtig, in {sum(1 for s in f["seeds"] if s["k"] == s["n"])} von {len(f["seeds"])} Sätzen fehlerfrei. Jeder Satz wurde neu erzeugt und genau einmal gemessen.</p></header>'
                             f'<div class="saetze">{saetze}</div></section>',
                           json.dumps(ds, ensure_ascii=False))

    # Prüfreihe Fristen
    familien = "".join(f"<span>{escape(x)}</span>" for x in FAMILIEN)
    rechenweg = "".join(f"<li>{escape(s.split('] ', 1)[-1])}</li>" for s in b["rechenweg"])
    normen = " · ".join(escape(n) for n in b["sollwert"]["normen_pflicht"])
    p["pruefreihe-fristen.html"] = ("Prüfreihe 1: Fristen berechnen · Gesetzesfest",
                                    "Was Prüfreihe 1 testet: neun Aufgabenarten von Widerspruch bis Kündigung, mit Beispielaufgabe und Rechenweg.",
                                    auftakt("Prüfreihen", "Was testet Prüfreihe 1 „Fristen berechnen“?",
                                            "Sie testet, ob ein Modell aus einem Schreiben das richtige Fristende bestimmt oder ein genanntes Datum richtig prüft. Dazu muss es Zugang, Bekanntgabe, Wochenenden und Feiertage je Bundesland richtig behandeln.",
                                            stand, code, f["n"])
                                    + f'<section aria-labelledby="t1"><header><h2 id="t1">Welche Aufgabenarten gibt es?</h2></header><div class="familien">{familien}</div></section>'
                                    + f'<section aria-labelledby="t2"><header><h2 id="t2">Wie sieht eine Aufgabe aus?</h2><p class="klein">Beispiel aus einem öffentlichen Übungssatz.</p></header>'
                                      f'<div class="beispiel"><pre class="akte">{escape(b["dokument"])}</pre><div class="weg"><p><b>{escape(b["frage"])}</b></p><ol>{rechenweg}</ol>'
                                      f'<div class="loesung"><span class="etikett">Fristende</span><b>{datum_de(b["sollwert"]["fristende"])}</b><span class="zahl klein">{normen}</span></div></div></div></section>'
                                    + '<section aria-labelledby="t3"><header><h2 id="t3">Welche Prüfreihen kommen?</h2></header><div class="raster">'
                                      '<div class="feld"><span class="etikett">läuft</span><h3>1 · Fristen berechnen</h3><p>Wann endet die Frist, und stimmt das genannte Datum?</p></div>'
                                      '<div class="feld"><span class="etikett">in Arbeit</span><h3>2 · Belehrung prüfen</h3><p>Ist die Rechtsbehelfsbelehrung vollständig und richtig? Fehlt sie, gilt oft ein Jahr statt eines Monats.</p></div>'
                                      '<div class="feld offen"><span class="etikett">geplant</span><h3>3 · Form prüfen</h3><p>Reicht eine E-Mail, oder braucht es die Unterschrift auf Papier?</p></div></div></section>')

    # Methode
    regeln = [("Wer bestimmt die richtige Antwort?", "Ein Programm, keine KI. Der Rechner setzt §§ 187 bis 193 BGB, § 222 ZPO, die Bekanntgabefiktion (z. B. § 41 Abs. 2 VwVfG) und die Feiertage je Bundesland um. Jede Rechenregel verweist auf eine Norm."),
              ("Woher kommen die Fälle?", "Ein Generator erzeugt erfundene Schreiben im Aufbau echter Bescheide, Kündigungen und Vermerke. Namen, Anschriften und Aktenzeichen sind ausgedacht."),
              ("Wie wird bewertet?", "Jede Aufgabe wird dreimal gestellt. Bestanden ist sie nur, wenn alle drei Antworten exakt stimmen. Zusätzlich zählen erfundene Normen und sicher-falsche Antworten."),
              ("Wie wird verhindert, dass Modelle auswendig lernen?", "Ein Testsatz bleibt geheim. Frische Sätze werden mit neuem Zufallswert erzeugt und genau einmal gemessen. Nachgeschärft wird nur an Übungssätzen."),
              ("Welche Statistik wird verwendet?", "Das 95-%-Wilson-Intervall an jeder Quote und der gepaarte McNemar-Test für jeden Vergleich. „Besser“ heißt: belegt besser bei p < 0,05."),
              ("Was kann Fristprobe nicht?", "Die Fälle decken nur die genannten Aufgabenarten ab. Ein gutes Ergebnis heißt nicht, dass ein Modell Rechtsberatung leisten darf. Fristprobe misst Modelle und berät keine Einzelfälle.")]
    p["methode.html"] = ("Methode · Wie misst Fristprobe? · Gesetzesfest",
                         "Musterlösung aus einem Programm nach §§ 187–193 BGB, erfundene Fälle, geheimer Testteil, Wilson-Intervalle und McNemar-Test.",
                         auftakt("Methode", "Wie misst Fristprobe?",
                                 "Ein Programm rechnet für jeden erfundenen Fall das richtige Fristende nach deutschem Recht. Das Modell muss dasselbe Datum finden und die passenden Normen nennen. Raten wird nicht belohnt: Fehlt eine Angabe, ist eine Rückfrage richtig.",
                                 stand, code, f["n"])
                         + "".join(f'<div class="frage"><h2>{escape(t)}</h2><p>{escape(x)}</p></div>' for t, x in regeln))

    # Daten
    p["daten.html"] = ("Daten · Rangliste als CSV und JSON · Gesetzesfest",
                       "Rangliste von Fristprobe zum Herunterladen als CSV und JSON, mit Feldbeschreibung und Version.",
                       auftakt("Daten", "Welche Daten kann ich herunterladen?",
                               "Die öffentliche Rangliste gibt es als CSV und JSON mit festen Dateinamen. Der Übungssatz folgt als offener Datensatz. Der geheime Testteil bleibt geschützt.",
                               stand, code, f["n"])
                       + '<section aria-labelledby="t1"><header><h2 id="t1">Downloads</h2></header><ul class="liste">'
                         '<li><a href="rangliste.csv">rangliste.csv</a>: eine Zeile je Modell</li><li><a href="rangliste.json">rangliste.json</a>: dieselben Daten mit frischen Sätzen</li>'
                         '<li>Übungssatz mit Rechenweg: folgt (Lizenz wird noch festgelegt)</li></ul></section>'
                       + '<section aria-labelledby="t2"><header><h2 id="t2">Was bedeuten die Felder?</h2></header><ul class="liste">'
                         '<li><b>bestanden</b>: Aufgaben, bei denen alle drei Antworten exakt stimmen</li><li><b>wilson_unten, wilson_oben</b>: 95-%-Intervall des Anteils</li>'
                         '<li><b>sicher_falsch</b>: falsche Antworten mit hoher angegebener Sicherheit</li><li><b>erfundene_normen</b>: Anteil genannter Normen, die es nicht gibt</li>'
                         '<li><b>token_pro_s</b>: Tempo auf der Messhardware (Median)</li></ul></section>')

    # FAQ
    faq = [("Was ist Fristprobe?", "Fristprobe ist ein unabhängiger Benchmark, der misst, ob KI-Modelle deutsche Fristen richtig berechnen und mit Normen belegen."),
           ("Welches Modell rechnet deutsche Fristen am besten?", f"Unter den lokal gemessenen Modellen {best['name']} mit Rechner: {best['k']} von {best['n']} auf dem geheimen Testsatz und {f['k']} von {f['n']} auf frischen Fällen (Stand {stand})."),
           ("Darf ich eine KI meine Frist berechnen lassen?", "Fristprobe misst Modelle, nicht Einzelfälle. Für eine konkrete Frist zählt der Rat einer Anwältin, eines Anwalts oder der Behörde. Ein Tag zu spät kann das Recht kosten."),
           ("Wer bestimmt, was richtig ist?", "Ein Programm nach §§ 187 bis 193 BGB und den Bekanntgaberegeln, keine KI."),
           ("Sind echte Personendaten im Spiel?", "Nein. Alle Fälle sind erfunden."),
           ("Wie oft wird gemessen?", "Bei jedem neuen Modell und jeder Code-Änderung. Datum und Code-Version stehen an jeder Zahl."),
           ("Kann man einen Platz in der Rangliste kaufen?", "Nein. Bezahlte Prüfläufe für Firmen ändern nie die öffentlichen Ergebnisse."),
           ("Werden auch große Cloud-Modelle getestet?", "Geplant. Bisher stehen lokal laufende Modelle in der Rangliste."),
           ("Wie kann ich mein Modell oder Produkt prüfen lassen?", "Über die Seite „Prüfen lassen“. Wir testen auf dem geheimen Teil und schicken einen Bericht mit Intervallen."),
           ("Wie zitiere ich Fristprobe?", "Mit Name, Prüfreihe, Stand und Code-Version. Ein fertiger Vorschlag steht auf der Seite „Zitieren“.")]
    p["faq.html"] = ("FAQ · Häufige Fragen zu Gesetzesfest",
                     "Antworten zu Fristprobe: was gemessen wird, welches Modell vorne liegt, wer die Lösung bestimmt, Unabhängigkeit und Prüfläufe.",
                     auftakt("FAQ", "Häufige Fragen zu Fristprobe", "Kurze Antworten auf die Fragen, die uns am häufigsten gestellt werden.", stand, code, f["n"])
                     + "".join(f'<div class="frage"><h2>{escape(q)}</h2><p>{escape(a)}</p></div>' for q, a in faq),
                     json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                         {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
                         ensure_ascii=False))

    # Zitieren
    bib = (f"@misc{{fristprobe{stand_iso[:4]},\n  title  = {{Fristprobe: Prüfreihe 1 „Fristen berechnen“}},\n"
           f"  author = {{{{{DACH}}}}},\n  year   = {{{stand_iso[:4]}}},\n  note   = {{Stand {stand}, Code {code}}},\n  url    = {{{URL}}}\n}}")
    p["zitieren.html"] = ("Zitieren · Gesetzesfest",
                          "Zitiervorschlag und BibTeX für Fristprobe, mit Stand und Code-Version.",
                          auftakt("Zitieren", "Wie zitiere ich Fristprobe?",
                                  f"Nenne Name, Prüfreihe, Stand und Code-Version: „Fristprobe, Prüfreihe 1 ‚Fristen berechnen‘, Stand {stand}, Code {escape(code)}.“",
                                  stand, code, f["n"])
                          + f'<section aria-labelledby="t1"><header><h2 id="t1">BibTeX</h2></header><pre class="code">{escape(bib)}</pre></section>')

    # Prüfen lassen
    p["pruefen-lassen.html"] = ("Prüfen lassen · Prüflauf für Ihr Modell oder Produkt · Gesetzesfest",
                                "Unabhängiger Prüflauf für KI-Modelle und Legal-Tech-Produkte: geheimer Testteil, Bericht mit Intervallen, Datensätze mit Rechenweg.",
                                auftakt("Für Firmen und Behörden", "Wie lasse ich mein Modell oder Produkt prüfen?",
                                        "Sie schicken uns Zugang zu Ihrem Modell oder Produkt. Wir lassen es den geheimen Testteil rechnen und liefern einen Bericht mit Trefferquote, Intervallen, Fehlerarten und Beispielen. Die öffentliche Rangliste bleibt davon unberührt.",
                                        stand, code, f["n"])
                                + '<section aria-labelledby="t1"><header><h2 id="t1">Was können Sie bei uns beauftragen?</h2></header><div class="raster">'
                                  '<div class="feld"><h3>Prüflauf</h3><p>Ihr Modell auf dem geheimen Testteil, je Aufgabe dreimal. Bericht mit Wilson-Intervallen und Vergleich zur Rangliste.</p></div>'
                                  '<div class="feld"><h3>Datensatz</h3><p>Geprüfte Aufgaben mit Musterlösung aus Code, Rechenweg und Normen, für Training-Evaluation oder Qualitätssicherung.</p></div>'
                                  '<div class="feld"><h3>Eigene Prüfreihe</h3><p>Wir bauen eine Prüfreihe für Ihren Fachbereich, zum Beispiel Ihre Bescheidarten oder Fristen.</p></div></div></section>'
                                + '<section aria-labelledby="t2"><header><h2 id="t2">Wie läuft ein Auftrag ab?</h2></header><div class="schritte">'
                                  '<div class="schritt"><h3>Anfrage</h3><p>Sie beschreiben Modell oder Produkt und Ziel.</p></div>'
                                  '<div class="schritt"><h3>Messung</h3><p>Wir messen auf eigener Hardware oder über Ihren Zugang, mit festem Code-Stand.</p></div>'
                                  '<div class="schritt"><h3>Bericht</h3><p>Sie erhalten Ergebnisse, Fehlerbeispiele und die Statistik. Veröffentlicht wird nur mit Ihrer Zustimmung.</p></div></div></section>'
                                + f'<section aria-labelledby="t3"><div class="kasten"><h2 id="t3">Kontakt</h2><p>{escape(KONTAKT)}</p>'
                                  '<p class="klein">Unsere Regel: Wer zahlt, bekommt einen Bericht, aber keinen Einfluss auf die öffentliche Rangliste und keine Aufgaben gestrichen.</p></div></section>')

    # Über uns
    p["ueber.html"] = ("Über uns · Wer steht hinter Gesetzesfest?",
                       f"Fristprobe ist ein unabhängiges Projekt von {DACH}. Wer zahlt, was wir nicht können, Versionen.",
                       auftakt("Über uns", "Wer steht hinter Fristprobe?",
                               f"Fristprobe ist Prüfreihe 1 von {escape(DACH)}, einem kleinen unabhängigen Prüflabor. Wir messen auf eigener Hardware, ohne Werbung und ohne Geldgeber, die Ergebnisse beeinflussen könnten.",
                               stand, code, f["n"])
                       + '<div class="frage"><h2>Wer bezahlt Fristprobe?</h2><p>Bisher niemand. Die Messungen laufen auf eigener Hardware für 0 € Cloud-Kosten. Sollte sich das ändern, steht hier, wer zahlt.</p></div>'
                       + '<div class="frage"><h2>Wie bleibt die Rangliste unabhängig?</h2><p>Kein Platz ist käuflich. Bezahlte Prüfläufe ändern nie die öffentlichen Ergebnisse, und niemand kann Aufgaben streichen lassen.</p></div>'
                       + '<div class="frage"><h2>Was hat sich zuletzt geändert?</h2><p>18.10.2026: Neue Regel gegen Daten aus Notizen Dritter, zwei frische Sätze mit 100 von 100, Seite neu aufgebaut.</p></div>'
                       + f'<div class="frage"><h2>Impressum und Kontakt</h2><p>{escape(KONTAKT)}</p></div>')
    return p


# ----------------------------------------------------------------- Dateien

def csv_text(r: list[dict]) -> str:
    puffer = io.StringIO()
    w = csv.writer(puffer)
    w.writerow(["modell", "kennung", "bestanden", "aufgaben", "wilson_unten", "wilson_oben", "sicher_falsch",
                "erfundene_normen", "token_pro_s"])
    for z in r:
        w.writerow([z["name"], z["id"], z["k"], z["n"], z["wilson"][0], z["wilson"][1], z["falsch"], z["erfunden"],
                    "" if z["tokens"] is None else z["tokens"]])
    return puffer.getvalue()


def llms(r: list[dict], f: dict, stand: str, voll: bool, texte: dict) -> str:
    best = next(z for z in r if z["bester"])
    zeilen = "\n".join(f"- {z['name']}: {z['k']}/{z['n']} bestanden, sicher falsch {z['falsch']}" for z in r if not z["orakel"])
    kopf_text = (f"# {DACH}: Fristprobe\n\n> Unabhängiger deutscher Benchmark: Rechnen KI-Modelle deutsche Fristen richtig und belegen sie "
                 f"jede Antwort mit einer Norm? Prüfreihe 1 von {DACH}. Stand {stand}.\n\nKernergebnis: {best['name']} mit Rechner löst "
                 f"{f['k']} von {f['n']} frischen Fristfällen (95-%-Intervall {prozent(f['wilson'][0], 1)} bis "
                 f"{prozent(f['wilson'][1], 1)}), 0 erfundene Normen.\n\n## Rangliste (geheimer Testsatz, 50 Aufgaben, je drei Läufe)\n{zeilen}\n\n"
                 "## Seiten\n" + "\n".join(f"- [{t}]({URL}/{d}): {texte[d][1]}" for d, t in
                                             [("rangliste.html", "Rangliste"), ("pruefreihe-fristen.html", "Prüfreihe Fristen"),
                                              ("methode.html", "Methode"), ("daten.html", "Daten"), ("faq.html", "FAQ"),
                                              ("pruefen-lassen.html", "Prüfen lassen"), ("ueber.html", "Über uns")]) + "\n")
    return kopf_text if not voll else kopf_text + "\n## Methode\n- Musterlösung aus einem Programm (§§ 187–193 BGB, Feiertage je Bundesland, Bekanntgabefiktion), nicht von einer KI.\n- Nur erfundene Fälle; geheimer Testteil; frische Sätze je einmal gemessen.\n- Wilson-Intervall an jeder Quote, McNemar-Test für Vergleiche.\n- Unabhängig: keine Werbung, keine bezahlten Platzierungen.\n"


ROBOTS = """# Fristprobe: Such-Crawler ausdrücklich erlaubt
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: Claude-SearchBot
Allow: /
User-agent: Claude-User
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Perplexity-User
Allow: /
User-agent: Bingbot
Allow: /
User-agent: Googlebot
Allow: /
User-agent: *
Allow: /
Sitemap: {url}/sitemap.xml
"""


def main() -> int:
    r, f, b = rangliste(), frisch(), beispiel()
    heute = date.today()
    stand, stand_iso, code = heute.strftime("%d.%m.%Y"), heute.isoformat(), code_stand()
    texte = seiten(r, f, b, stand, stand_iso, code)
    DIST.mkdir(parents=True, exist_ok=True)
    for datei, (titel, beschr, inhalt, *ld) in texte.items():
        (DIST / datei).write_text(seite(datei, titel, beschr, inhalt, stand, code, ld[0] if ld else ""), encoding="utf-8")
    (DIST / "rangliste.csv").write_text(csv_text(r), encoding="utf-8")
    (DIST / "rangliste.json").write_text(json.dumps({"stand": stand_iso, "code": code, "rangliste": r, "frisch": f},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (DIST / "llms.txt").write_text(llms(r, f, stand, False, texte), encoding="utf-8")
    (DIST / "llms-full.txt").write_text(llms(r, f, stand, True, texte), encoding="utf-8")
    (DIST / "robots.txt").write_text(ROBOTS.format(url=URL), encoding="utf-8")
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{URL}/{d}</loc><lastmod>{stand_iso}</lastmod></url>\n" for d in texte) + "</urlset>\n",
        encoding="utf-8")
    titel, beschr, inhalt, *_ = texte["index.html"]
    (WURZEL / "seite" / "vorschau.html").write_text(
        f'<title>Fristprobe</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{FONTS}\n<style>{CSS}</style>\n'
        f'<div class="blatt">{kopf("index.html")}<main>{inhalt}</main>{fuss(stand, code)}</div>\n', encoding="utf-8")
    print(f"seite/dist gebaut: {len(texte)} Seiten, {len(r)} Modelle, frisch {f['k']}/{f['n']}, Code {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
