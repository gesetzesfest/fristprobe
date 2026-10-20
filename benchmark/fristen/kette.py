#!/usr/bin/env python3
"""Kette „Modell liest, Code rechnet“ für den Fristen-Benchmark (nur Standardbibliothek).

Schritt 1, Auslesen: Ein lokales Ollama-Modell bekommt NUR Dokument und Frage (nie Parameter oder
Sollwert) und gibt ein festes JSON mit Tatsachen aus dem Dokument zurück. Das Schema steht in
prompt_kette.py und wird über Ollamas ``format`` erzwungen (structured outputs). Lehnt der Server das
Schema ab, läuft die Kette mit ``format: "json"`` weiter (Spalte ``format`` in der Ergebniszeile).
``--format json`` erzwingt das von Anfang an (Kontrolllauf wie bei den Einzelmodellen, die nur
``format: "json"`` bekommen; Name ``<modell>+rechner-json``).

Schritt 2, Rechnen: Reiner Code bildet die Felder auf pruefki.fristen.rechner ab und berechnet Fristende
und Normen. Bei Typ „pruefen“ vergleicht der Code das genannte mit dem berechneten Fristende (befund oder
kein_befund). Fehlt ein nötiges Feld, lautet die Antwort „rueckfrage“. Eine leere Auslese (kein Feld
lesbar) oder eine, aus der sich die Art nicht bestimmen lässt, ergibt KEINE Antwort (zählt wie unlesbar):
Sonst bekäme ein Modell, das nichts liest, die Rückfrage-Aufgaben geschenkt. Sicherheit 0,9, wenn alle
nötigen Felder da und lesbar sind, nichts angenommen werden musste und der Rechner weder „unsicher“ noch
„strittig“ meldet; sonst niedriger.

Vergleichbar mit den Einzelmodellen ist nur „exakt“: Normen und Sicherheit der Kette kommen aus dem Code,
Belegquote, Erfindungsquote, Brier und „sicher und falsch“ messen hier also den Rechner, nicht das Modell.

Ausgabe im Format von run_ollama.py, eine Zeile je Antwort unter
benchmark/fristen/ergebnisse/<datum>-<modell>+rechner.jsonl, so wertet bewerten.py die Kette wie ein
eigenes Modell. Zusätzlich je Zeile: felder_roh (Modellausgabe), felder (geprüft), rechnung (Abbildung,
fehlende Felder, Annahmen) für fehleranalyse.py.

--orakel nimmt statt des Modells die wahren Felder aus aufgaben.jsonl/parameter. Das ist die
Obergrenze der Kette und muss 50/50 ergeben, sonst ist die Abbildung falsch. Bei v3 gilt das einschließlich
der Gegenproben (keine Regel darf den wahren Feldern widersprechen) und der Nachfrage: Das Orakel beantwortet
sie mit dem wahren Wert und der Zeile, in der er steht (ohne Modellaufruf, ``aufrufe`` 0). Gefragt wird nur
bei den Rückfrage-Aufgaben, die Antwort ist dort null, und die Antwortart bleibt „rueckfrage“. Das prüft die
Abbildung, nicht die Wirkung: Wie oft ein Modell auf Nachfrage richtig antwortet, zeigt erst ein echter Lauf.
Ebenso ist der Stub-Lauf in den Tests (StubModellV3) ein Regressionstest für die Regeln, kein Wirkungsnachweis.

Fassungen (--prompt-version, Standard v3; Name in der Rangliste <modell>+rechner bzw. <modell>+rechner-v3):

- v2: eine Auslese, dann Rechner. Unverändert reproduzierbar (Prompt-Hash a9f5f6a18651).
- v3: geschärfter Prompt (prompt_kette.py), danach Gegenproben im Code (``gegenpruefe``: Daten müssen im
  Dokument stehen, Verfahrensordnung aus Gericht, Rechtsbehelf und Gesetz, Art des Bescheids aus dem
  Rechtsbehelf, Rechtsbehelfsbelehrung nur mit Frist, Zeitfolge; jede Regel mit Norm in ``REGELN``). Fehlt
  danach ein Feld, das der Rechner für die erkannte Art braucht, stellt die Kette dem Modell genau eine zweite,
  kurze Frage nur zu diesem Feld (``nachfrage_feld``; eigenes kleines Schema, kein Lösungshinweis). Höchstens
  ein Nachfrage-Aufruf je Aufgabe; Spalten ``aufrufe`` und ``nachfrage`` (Feld, Antwort, Dauer) in der
  Ergebniszeile. Was erst auf Nachfrage oder per Gegenprobe gegen die Auslese gesetzt wurde, rechnet mit
  Sicherheit 0,6. ``--ohne-nachfrage`` / ``--ohne-gegenprobe`` schalten die Teile einzeln ab (Name
  ``…-v3-ohne-nachfrage`` usw.), damit sich ihr Beitrag messen lässt.

Aufgabensätze: Standard ist aufgaben.jsonl (Seed v1, Ausgabe ergebnisse/). ``--holdout`` nimmt die eine
.jsonl-Datei in holdout/ (Ausgabe ergebnisse/holdout/, dort eigene rangliste.md/json). Jede andere Datei über
``--aufgaben`` schreibt nach ergebnisse/<Dateiname>/ mit eigener Rangliste, nie in die Hauptrangliste.
Grenze des Holdouts: Er stammt aus generator.py mit anderem Seed. Vorlagen, Namenslisten, Vermerke, Fragen und
die 50 Fallen-Plätze (PLAN) sind dieselben wie in Seed v1; er misst also die Verallgemeinerung auf neue Daten,
Länder und Personen, nicht auf neue Vorlagen, und er lässt sich aus Generator und Seed jederzeit neu erzeugen
(„ungeöffnet“ ist eine Zusage, keine prüfbare Eigenschaft). Weil alle Sätze dieselben IDs (F001 …) nutzen, trägt
jede Ergebniszeile die Kennung ihrer Aufgabe (``aufgabe_kennung``): Fortsetzen, bewerten.py und fehleranalyse.py
brechen ab, wenn Zeilen zu einem anderen Satz gehören.

  python3 benchmark/fristen/kette.py --modelle qwen3:8b llama3.2:3b
  python3 benchmark/fristen/kette.py --modelle qwen3:8b --think --ids F001 F002 --laeufe 1
  python3 benchmark/fristen/kette.py --orakel --ausgabe-dir /tmp/kette
  python3 benchmark/fristen/kette.py --modelle qwen3:8b --prompt-version v2     # alte Kette
  python3 benchmark/fristen/kette.py --modelle qwen3:8b --format json          # Kontrolllauf ohne Schema
  python3 benchmark/fristen/kette.py --modelle qwen3:8b gemma3:4b --holdout    # Endmessung (neue Daten)
  # Gegenprobe auf frischen Aufgaben (gleiche Vorlagen, andere Daten und Namen):
  python3 benchmark/fristen/generator.py --seed 7 --ausgabe /tmp/seed7.jsonl
  python3 benchmark/fristen/kette.py --aufgaben /tmp/seed7.jsonl --ausgabe-dir /tmp/seed7 --modelle qwen3:8b

Ein abgebrochener Lauf setzt wie bei run_ollama.py wieder auf (gleiches Modell, Aufgabe, Lauf).
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import statistics
import sys
import time
import urllib.error
from collections import Counter
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
for _p in (str(HIER), str(WURZEL)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bewerten as B  # noqa: E402
import prompt as P  # noqa: E402
import prompt_kette as PK  # noqa: E402
import run_ollama as RO  # noqa: E402
from pruefki.fristen import rechner as R  # noqa: E402
from pruefki.fristen.feiertage import LAENDER  # noqa: E402

SUFFIX = "+rechner"
ORAKEL = "orakel"
STANDARD_AUFGABEN = HIER / "aufgaben.jsonl"
ERGEBNISSE = HIER / "ergebnisse"
HOLDOUT_DIR = HIER / "holdout"     # frischer Satz für die Endmessung; Inhalt nur beim Lauf gelesen

RB_ARTEN = ("widerspruch_sgb2", "widerspruch_vwvfg", "einspruch_ao", "klage_sgg", "klage_vwgo")
ART_AUS_VERFAHREN = {
    ("SGB X", "bescheid"): "widerspruch_sgb2", ("SGB X", "widerspruchsbescheid"): "klage_sgg",
    ("VwVfG", "bescheid"): "widerspruch_vwvfg", ("VwVfG", "widerspruchsbescheid"): "klage_vwgo",
    ("AO", "bescheid"): "einspruch_ao",
}
ART_TEXT = {"widerspruch_sgb2": "Widerspruch (SGB X)", "widerspruch_vwvfg": "Widerspruch (VwVfG)",
            "einspruch_ao": "Einspruch (AO)", "klage_sgg": "Klage zum Sozialgericht",
            "klage_vwgo": "Klage zum Verwaltungsgericht", "kschg_klage": "Kündigungsschutzklage",
            "kuendigung_arbeit": "Kündigung Arbeitsverhältnis", "kuendigung_miete": "Kündigung Mietverhältnis"}
FELD_TEXT = {"art": "Art des Rechtsbehelfs bzw. der Kündigung", "bundesland": "Bundesland",
             "datum_aufgabe_post": "Tag der Aufgabe zur Post", "datum_zustellung": "Tag der Zustellung",
             "zustellart": "Zustellart mit Datum", "datum_zugang": "Tag des Zugangs der Kündigung",
             "ueberlassung": "Tag der Überlassung der Wohnung",
             "beschaeftigungsbeginn": "Beginn des Arbeitsverhältnisses",
             "genanntes_fristende": "im Dokument genanntes Fristende"}

SICHER = 0.9            # alle nötigen Felder da, nichts angenommen, Rechner ohne Vorbehalt
MIT_ANNAHME = 0.6       # Vorgabe eingesetzt, Widerspruch zwischen Feldern oder unplausible Reihenfolge
RECHNER_VORBEHALT = 0.5  # Rechner meldet unsicher oder strittig
RUECKFRAGE_FELD = 0.6   # nötiges Feld fehlt (kann auch ein Lesefehler sein)
UNBESTIMMT = 0.3        # Rechner lehnt die Angaben ab
JAHRE = (1900, 2099)    # plausible Jahre; alles andere gilt als unlesbar (auch Schutz vor OverflowError)


def ds(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else "—"


# ----------------------------------------------------------------- Felder prüfen und vereinheitlichen

def _ohne_umlaute(s: str) -> str:
    return s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


_LAND = {}
for _code, _name in LAENDER.items():
    for _k in (_code, _name, _ohne_umlaute(_name), _name.replace("-", " ")):
        _LAND[_ohne_umlaute(_k.lower())] = _code
_LAND.update({"nrw": "NW", "rlp": "RP"})
# Amtliche Vorsätze vor dem Ländernamen („Freistaat Bayern“, „Freie und Hansestadt Hamburg“)
_LAND_VORSATZ = re.compile(r"^(?:bundesland|land|freistaat|freie und hansestadt|freie hansestadt|hansestadt)\s+")


def _land_code(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip(" ,.;:")
    return _LAND.get(s) or _LAND.get(_LAND_VORSATZ.sub("", s))


def lies_datum(v) -> tuple[str | None, bool]:
    """'02.02.2027', '2.2.2027', '2027-02-02' oder '2. Februar 2027' -> ('2027-02-02', False); unlesbar -> (None, True)."""
    if v is None:
        return None, False
    s = str(v).strip()
    if s.lower() in ("", "null", "none", "-", "—", "unbekannt"):
        return None, False
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    try:
        if m:
            d = date(int(m[1]), int(m[2]), int(m[3]))
        else:
            m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s)
            if m:
                d = date(int(m[3]), int(m[2]), int(m[1]))
            else:  # „3. März 2026“, „02. APR. 2026“ (Modell schreibt das Datum wie im Brief ab)
                m = _D_WORT.search(s)
                d = date(int(m[3]), _MONATE[m[2].lower()], int(m[1])) if m else None
    except ValueError:
        d = None
    if d is None or not JAHRE[0] <= d.year <= JAHRE[1]:
        return None, True
    return d.isoformat(), False


def _wahl(v, erlaubt) -> tuple[str | None, bool]:
    if v is None:
        return None, False
    s = _ohne_umlaute(str(v).strip().lower()).replace(" ", "_").replace("-", "_")
    if s in ("", "null", "none", "unbekannt"):
        return None, False
    for w in erlaubt:
        if s == _ohne_umlaute(w.lower()).replace(" ", "_").replace("-", "_"):
            return w, False
    return None, True


def _verfahren(v) -> tuple[str | None, bool]:
    if v is None:
        return None, False
    s = re.sub(r"[\s_.\-]", "", str(v)).upper()
    if s in ("", "NULL", "NONE"):
        return None, False
    w = {"SGBX": "SGB X", "SGB10": "SGB X", "VWVFG": "VwVfG", "AO": "AO"}.get(s)
    return w, w is None


def _land(v) -> tuple[str | None, bool]:
    """Ländername oder -kürzel -> Kürzel. Klammerzusätze („Niedersachsen (NI)“) zählen nur, wenn innen und
    außen nicht zwei verschiedene Länder stehen; ein Ort oder ein unbekannter Name bleibt unlesbar (None)."""
    if v is None:
        return None, False
    s = _ohne_umlaute(str(v).strip().lower())
    if s in ("", "null", "none"):
        return None, False
    w = _land_code(s)
    if w is None and "(" in s:
        innen = re.findall(r"\(([^()]*)\)", s)
        aussen = re.sub(r"\([^()]*\)", " ", s)
        codes = {c for c in (_land_code(t) for t in [aussen, *innen]) if c}
        w = codes.pop() if len(codes) == 1 else None
    return w, w is None


def _ja_nein(v) -> tuple[bool | None, bool]:
    if v is None or isinstance(v, bool):
        return v, False
    s = str(v).strip().lower()
    if s in ("true", "ja", "yes", "1"):
        return True, False
    if s in ("false", "nein", "no", "0"):
        return False, False
    if s in ("", "null", "none"):
        return None, False
    return None, True


_ZAHLWORT = {"ein": 1, "einen": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
             "sechs": 6}


def _zahl(v) -> tuple[int | None, bool]:
    if v is None:
        return None, False
    if isinstance(v, bool):
        return None, True
    if isinstance(v, (int, float)):
        return (int(v), False) if float(v).is_integer() and v > 0 else (None, True)
    s = str(v).strip().lower()
    if s in ("", "null", "none"):
        return None, False
    m = re.search(r"\d+", s)
    if m and int(m[0]) > 0:
        return int(m[0]), False
    w = _ZAHLWORT.get(s.split()[0]) if s.split() else None
    return w, w is None


def _rbb(v) -> tuple[str | None, bool]:
    if v is True:
        return "vorhanden", False
    if v is False:
        return "fehlt", False
    s = str(v).strip().lower() if v is not None else None
    if s in ("ja", "true"):
        return "vorhanden", False
    if s in ("nein", "false"):
        return "fehlt", False
    return _wahl(v, PK.RBB)


def lies_feld(name: str, v) -> tuple:
    """Ein Rohwert des Modells -> (geprüfter Wert oder None, unlesbar?)."""
    if name in PK.DATUMSFELDER:
        return lies_datum(v)
    if name == "verfahren":
        return _verfahren(v)
    if name == "bundesland":
        return _land(v)
    if name == "schreiben":
        return _wahl(v, PK.SCHREIBEN)
    if name == "art":
        return _wahl(v, PK.ARTEN)
    if name == "zustellart":
        return _wahl(v, PK.ZUSTELLARTEN)
    if name == "rechtsbehelfsbelehrung":
        return _rbb(v)
    if name == "kuendigende_partei":
        return _wahl(v, PK.PARTEIEN)
    if name == "probezeit":
        return _ja_nein(v)
    if name == "probezeit_monate":
        return _zahl(v)
    raise KeyError(name)  # pragma: no cover - neue Felder müssen hier eingetragen werden


def normalisiere(roh) -> tuple[dict | None, list[str]]:
    """Rohfelder des Modells -> geprüfte Felder (Daten ISO, Land als Kürzel); Unlesbares wird None.

    Ist danach kein einziges Feld gefüllt (leeres Objekt, alles null, nur fremde Schlüssel wie
    antwortart/fristende), gilt die ganze Auslese als unlesbar: (None, hinweise)."""
    felder, hinweise, _ = _normalisiere(roh)
    return felder, hinweise


def _normalisiere(roh) -> tuple[dict | None, list[str], list[str]]:
    """Wie normalisiere, zusätzlich die Namen der unlesbaren Felder (für die Sicherheit in rechne)."""
    if not isinstance(roh, dict):
        return None, ["Auslese ist kein JSON-Objekt"], []
    felder: dict = {}
    hinweise: list[str] = []
    unlesbar: list[str] = []
    for name in PK.FELDNAMEN:
        v = roh.get(name)
        w, kaputt = lies_feld(name, v)
        felder[name] = w
        if kaputt:
            unlesbar.append(name)
            hinweise.append(f"{name} unlesbar: {str(v)[:40]!r}")
    fremd = sorted(set(roh) - set(PK.FELDNAMEN))
    if fremd:
        hinweise.append("unbekannte Felder ignoriert: " + ", ".join(fremd))
    if all(w is None for w in felder.values()):
        return None, hinweise + ["Auslese leer: kein Feld lesbar"], unlesbar
    return felder, hinweise, unlesbar


def als_modellausgabe(felder: dict) -> dict:
    """Geprüfte Felder zurück in die Schreibweise des Modells (TT.MM.JJJJ, Ländername)."""
    out = {}
    for name in PK.FELDNAMEN:
        v = felder.get(name)
        if v is not None and name in PK.DATUMSFELDER:
            v = ds(v)
        elif v is not None and name == "bundesland":
            v = LAENDER[v]
        out[name] = v
    return out


# ----------------------------------------------------------------- Rechnen (nur Code)

def bestimme_art(f: dict, frage: str = "") -> tuple[str | None, list[str]]:
    """Art aus schreiben und verfahren (Behördenschreiben) bzw. aus art (Kündigungen); Rückgabe (art, Annahmen).

    Bei Bescheiden entscheidet der Code aus zwei einfachen Tatsachen (wer schreibt, Ausgangs- oder
    Widerspruchsbescheid); das Feld art des Modells dient dann nur als Ersatz und zur Gegenprobe. Ein
    Widerspruch zwischen beiden ist eine Annahme (Sicherheit sinkt), eine fehlende Gegenprobe nicht.
    Bei Arbeitskündigungen ist der Wortlaut der Frage die Gegenprobe (Klagefrist oder Beendigungstermin):
    Widerspricht er dem Feld art, gilt die Frage, mit Annahme.
    """
    modell_art = f.get("art")
    schreiben = f.get("schreiben")
    annahmen: list[str] = []
    if schreiben in ("bescheid", "widerspruchsbescheid"):
        art = ART_AUS_VERFAHREN.get((f.get("verfahren"), schreiben))
        if art is None and modell_art in RB_ARTEN:
            art = modell_art
    elif schreiben == "kuendigung_mietverhaeltnis":
        art = "kuendigung_miete"
    elif schreiben == "kuendigung_arbeitsverhaeltnis":
        aus_frage = art_aus_frage(frage)
        if modell_art in ("kschg_klage", "kuendigung_arbeit") and aus_frage in (None, modell_art):
            art = modell_art
        else:
            art = aus_frage or "kuendigung_arbeit"
            if modell_art not in ("kschg_klage", "kuendigung_arbeit"):
                annahmen.append(f"art aus der Frage geschlossen: {art}")
    else:
        art = modell_art
    if modell_art and art and modell_art != art:
        annahmen.append(f"art {modell_art} passt nicht zu Schreiben, Verfahren oder Frage; gerechnet als {art}")
    return art, annahmen


def art_aus_frage(frage: str) -> str | None:
    """Arbeitskündigung: fragt die Frage nach der Klagefrist oder nach dem Beendigungstermin? None: unklar."""
    f = (frage or "").lower()
    if "klage" in f:
        return "kschg_klage"
    if any(w in f for w in ("endet", "beendigung", "kündigungsfrist", "kuendigungsfrist", "termin")):
        return "kuendigung_arbeit"
    return None


def _zustellung(f: dict, annahmen: list[str]) -> tuple[str | None, str | None, str | None, list[str]]:
    """Zustellart und Ereignistag eines Bescheids: (zustellart, aufgabe_post, zustellung, fehlend)."""
    za = f.get("zustellart")
    post, zust, zug = f.get("datum_aufgabe_post"), f.get("datum_zustellung"), f.get("datum_zugang")
    if za == "zustellungsurkunde":
        if zust is None and zug is not None:
            annahmen.append("Zustelldatum aus datum_zugang übernommen")
            zust = zug
        return "pzu", None, zust, ([] if zust else ["datum_zustellung"])
    if za == "einfacher_brief":
        return "brief", post, None, ([] if post else ["datum_aufgabe_post"])
    if za == "persoenliche_uebergabe":
        tag = zust or zug
        if tag:
            annahmen.append("persönliche Übergabe wie Zustellung gerechnet (Tag der Übergabe)")
            return "pzu", None, tag, []
        return "pzu", None, None, ["datum_zustellung"]
    # Zustellart nicht ausgelesen: aus den Daten schließen
    if zust and not post:
        annahmen.append("Zustellart aus datum_zustellung geschlossen: Zustellungsurkunde")
        return "pzu", None, zust, []
    if post and not zust:
        annahmen.append("Zustellart aus datum_aufgabe_post geschlossen: einfacher Brief")
        return "brief", post, None, []
    if post and zust:
        annahmen.append("Aufgabe zur Post und Zustellung ausgelesen, Zustellart fehlt: Zustellung genommen")
        return "pzu", None, zust, []
    return None, None, None, ["zustellart"]


def _zugang(f: dict, annahmen: list[str]) -> str | None:
    zugang = f.get("datum_zugang")
    if zugang is None and f.get("datum_zustellung"):
        annahmen.append("Zugang aus datum_zustellung übernommen")
        zugang = f["datum_zustellung"]
    return zugang


def _rueckfrage_normen(art: str | None, fehlend: list[str], f: dict) -> list[str]:
    normen: list[str] = []
    if art in RB_ARTEN:
        cfg = R.RECHTSBEHELFE[art]
        if "datum_aufgabe_post" in fehlend or "zustellart" in fehlend:
            normen.append(R.VERFAHREN[cfg["verfahren"]]["norm"])
        if "datum_zustellung" in fehlend:
            normen.append("§ 3 VwZG")
        normen.append(cfg["norm"] if f.get("rechtsbehelfsbelehrung") != "fehlt" else cfg["rbb_norm"])
    elif art == "kschg_klage":
        normen.append("§ 4 Satz 1 KSchG")
    elif art == "kuendigung_miete":
        normen += ["§ 573c Abs. 1 Satz 1 BGB", "§ 130 Abs. 1 Satz 1 BGB"]
        if "ueberlassung" in fehlend:
            normen.append("§ 573c Abs. 1 Satz 2 BGB")
    elif art == "kuendigung_arbeit":
        normen += ["§ 622 Abs. 2 BGB" if "beschaeftigungsbeginn" in fehlend else "§ 622 Abs. 1 BGB",
                   "§ 130 Abs. 1 Satz 1 BGB"]
    return normen


def _vor(a: str | None, b: str | None) -> bool:
    return bool(a and b and a < b)


def _begruendung(art: str, args: dict, e: R.Ergebnis, typ: str, genannt: str | None, antwortart: str) -> str:
    if art in RB_ARTEN:
        ereignis = (f"zur Post gegeben am {ds(args['aufgabe_post'])}" if args["zustellart"] == "brief"
                    else f"zugestellt am {ds(args['zustellung'])}")
        ohne = "" if args["rbb"] else ", ohne Rechtsbehelfsbelehrung"
    else:
        ereignis, ohne = f"Zugang am {ds(args['zugang'])}", ""
    land = f", {LAENDER[args['land']]}" if args.get("land") else ""
    was = {"kuendigung_miete": "Mietende", "kuendigung_arbeit": "Beendigungstermin"}.get(art, "Fristende")
    satz2 = f"Rechner: {was} {ds(e.datum.isoformat())}"
    if typ == "pruefen":
        satz2 += f"; genannt {ds(genannt)}, also {antwortart}"
    return f"Gelesen: {ART_TEXT[art]}{land}, {ereignis}{ohne}. {satz2}."


def rechne(felder: dict, typ: str, frage: str = "", unlesbar: list[str] | tuple = (),
           vorab: dict | None = None) -> dict:
    """Geprüfte Felder -> {'antwort': {...} oder None, 'rechnung': {...}}; nur Code, kein Modell.

    ``unlesbar``: Felder, die das Modell gefüllt hat, die sich aber nicht lesen ließen (aus _normalisiere,
    bei v3 auch Daten, die die Gegenprobe verworfen hat). Geht ein solches Feld in die Rechnung ein, ist das
    eine Annahme (Sicherheit höchstens 0,6). ``vorab``: Annahmen und Zweifel aus Gegenprobe und Nachfrage
    (v3); sie senken die Sicherheit wie eigene. Lässt sich die Art nicht bestimmen, gibt es keine Antwort
    (antwort None), keine Rückfrage.
    """
    f = {n: felder.get(n) for n in PK.FELDNAMEN}
    annahmen: list[str] = list((vorab or {}).get("annahmen", []))
    zweifel: list[str] = list((vorab or {}).get("zweifel", []))
    fehlend: list[str] = []
    benutzt = ["schreiben", "verfahren", "art"]
    art, a = bestimme_art(f, frage)
    annahmen += a
    land = f["bundesland"]
    funktion, args = None, {}

    if art is None:
        fehlend.append("art")
    elif art in RB_ARTEN:
        funktion = "rechtsbehelf"
        if land is None:
            fehlend.append("bundesland")
        zustellart, post, zust, fe = _zustellung(f, annahmen)
        fehlend += fe
        benutzt += ["bundesland", "zustellart"] + {"brief": ["datum_aufgabe_post"], "pzu": ["datum_zustellung"]}.get(
            zustellart, ["datum_aufgabe_post", "datum_zustellung"]) + ["rechtsbehelfsbelehrung"]
        rbb = f["rechtsbehelfsbelehrung"]
        if rbb is None:
            annahmen.append("Rechtsbehelfsbelehrung nicht ausgelesen: als vorhanden angenommen")
        args = {"art": art, "land": land, "zustellart": zustellart, "aufgabe_post": post, "zustellung": zust,
                "rbb": rbb != "fehlt"}
        if _vor(post or zust, f["datum_schreiben"]):
            zweifel.append("Aufgabe zur Post bzw. Zustellung liegt vor dem Datum des Bescheids")
    elif art == "kschg_klage":
        funktion = "kschg_klage"
        benutzt += ["bundesland", "datum_zugang"]
        zugang = _zugang(f, annahmen)
        fehlend += [n for n, v in (("bundesland", land), ("datum_zugang", zugang)) if v is None]
        args = {"zugang": zugang, "land": land}
    elif art == "kuendigung_miete":
        funktion = "kuendigung_miete"
        benutzt += ["bundesland", "datum_zugang", "kuendigende_partei"]
        zugang = _zugang(f, annahmen)
        partei = f["kuendigende_partei"]
        if partei not in ("mieter", "vermieter"):
            annahmen.append("kündigende Partei nicht ausgelesen: Mieterkündigung angenommen")
            partei = "mieter"
        fehlend += [n for n, v in (("bundesland", land), ("datum_zugang", zugang)) if v is None]
        args = {"zugang": zugang, "land": land, "partei": partei}
        if partei == "vermieter":
            benutzt.append("ueberlassung")
            args["ueberlassung"] = f["ueberlassung"]
            if f["ueberlassung"] is None:
                fehlend.append("ueberlassung")
            if _vor(zugang, f["ueberlassung"]):
                zweifel.append("Zugang liegt vor der Überlassung der Wohnung")
    elif art == "kuendigung_arbeit":
        funktion = "kuendigung_arbeit"
        benutzt += ["datum_zugang", "kuendigende_partei", "beschaeftigungsbeginn", "probezeit"]
        zugang = _zugang(f, annahmen)
        partei = f["kuendigende_partei"]
        if partei not in ("arbeitgeber", "arbeitnehmer"):
            annahmen.append("kündigende Partei nicht ausgelesen: Arbeitgeberkündigung angenommen")
            partei = "arbeitgeber"
        beginn = f["beschaeftigungsbeginn"]
        probezeit = bool(f["probezeit"])
        if f["probezeit"] is None and f["probezeit_monate"]:
            annahmen.append("Probezeit aus probezeit_monate geschlossen")
            probezeit = True
        if zugang is None:
            fehlend.append("datum_zugang")
        if not probezeit and beginn is None and partei == "arbeitgeber":
            fehlend.append("beschaeftigungsbeginn")
        args = {"zugang": zugang, "betriebszugehoerigkeit_jahre": None, "probezeit": probezeit, "partei": partei,
                "beginn": beginn, "land": land}
        if partei == "arbeitnehmer" and beginn is None and not probezeit:
            args["betriebszugehoerigkeit_jahre"] = 0   # bei Arbeitnehmerkündigung ohne Belang (§ 622 Abs. 1 BGB)
        if probezeit:
            benutzt.append("probezeit_monate")
            monate = f["probezeit_monate"]
            if monate is None:
                annahmen.append("Länge der Probezeit nicht ausgelesen: sechs Monate angenommen")
                monate = 6
            args["probezeit_monate"] = monate
            if beginn is None:
                annahmen.append("Probezeit ohne Beschäftigungsbeginn: Zugang in der Probezeit angenommen")
        if _vor(zugang, beginn):
            zweifel.append("Zugang liegt vor dem Beschäftigungsbeginn")
    if art in ("kschg_klage", "kuendigung_miete", "kuendigung_arbeit") and _vor(args.get("zugang"),
                                                                                 f["datum_schreiben"]):
        zweifel.append("Zugang liegt vor dem Datum des Schreibens")

    genannt = f["genanntes_fristende"]
    if typ == "pruefen":
        benutzt.append("genanntes_fristende")
        if genannt is None and art is not None:
            fehlend.append("genanntes_fristende")
    annahmen += [f"{n} unlesbar, als nicht angegeben behandelt" for n in unlesbar if n in benutzt]

    rechnung = {"art": art, "funktion": funktion, "argumente": args, "fehlend": fehlend, "annahmen": annahmen,
                "zweifel": zweifel, "benutzt": benutzt, "unlesbar": list(unlesbar), "ergebnis": None,
                "fehler": None}

    def rueckfrage(sicherheit: float, grund: str) -> dict:
        return {"antwort": {"antwortart": "rueckfrage", "fristende": None,
                            "normen": _rueckfrage_normen(art, fehlend, f), "sicherheit": sicherheit,
                            "begruendung": grund[:500]},
                "rechnung": rechnung}

    if art is None:
        # Ohne Art weiß die Kette nicht, welche Angabe fehlen könnte: keine Antwort statt einer Rückfrage,
        # die bei den Rückfrage-Aufgaben zufällig stimmen würde.
        rechnung["fehler"] = "Art nicht bestimmbar (schreiben, verfahren und art nicht gelesen oder unpassend)"
        return {"antwort": None, "rechnung": rechnung}
    if fehlend:
        return rueckfrage(RUECKFRAGE_FELD, "Es fehlt: " + ", ".join(FELD_TEXT.get(n, n) for n in fehlend) + ".")
    try:
        e = R.berechne(funktion, args)
    except (ValueError, TypeError, KeyError, OverflowError) as ex:
        rechnung["fehler"] = f"{type(ex).__name__}: {ex}"[:300]
        return rueckfrage(UNBESTIMMT, f"Der Rechner kann mit den gelesenen Angaben nicht rechnen: {ex}")
    datum = e.datum.isoformat()
    rechnung["ergebnis"] = {"datum": datum, "roh_datum": e.roh_datum.isoformat() if e.roh_datum else None,
                            "unsicher": e.unsicher, "strittig": e.strittig}
    if typ == "pruefen":
        antwortart = "kein_befund" if genannt == datum else "befund"
    else:
        antwortart = "berechnet"
    sicherheit = SICHER
    if annahmen or zweifel:
        sicherheit = MIT_ANNAHME
    if e.unsicher or e.strittig:
        sicherheit = min(sicherheit, RECHNER_VORBEHALT)
    return {"antwort": {"antwortart": antwortart, "fristende": datum, "normen": list(e.normen),
                        "sicherheit": sicherheit,
                        "begruendung": _begruendung(art, args, e, typ, genannt, antwortart)[:500]},
            "rechnung": rechnung}


def ist_exakt(aufgabe: dict, antwort_json: dict | None) -> bool:
    """Wie bewerten.py: Antwortart und (außer bei rueckfrage) Fristende stimmen."""
    if not antwort_json:
        return False
    s = aufgabe["sollwert"]
    if antwort_json.get("antwortart") != s["antwortart"]:
        return False
    return s["antwortart"] == "rueckfrage" or antwort_json.get("fristende") == s["fristende"]


# ----------------------------------------------------------------- Orakel: wahre Felder aus den Parametern

def orakel_felder(aufgabe: dict) -> tuple[dict, list[str]]:
    """Wahre Felder aus aufgaben.jsonl/parameter und die Liste der daraus prüfbaren Felder.

    Prüfbar sind Felder, deren richtiger Wert aus den Parametern folgt (auch null, wenn das Dokument die
    Angabe nicht enthält, etwa bei Rückfrage-Aufgaben).
    """
    p = aufgabe["parameter"]
    args = p["argumente"]
    zusatz = p.get("zusatz") or {}
    f: dict = {n: None for n in PK.FELDNAMEN}
    pruefbar: list[str] = []
    fn = p["funktion"]
    if fn == "rechtsbehelf":
        art = args["art"]
        cfg = R.RECHTSBEHELFE[art]
        f.update(schreiben="widerspruchsbescheid" if art.startswith("klage") else "bescheid",
                 verfahren=cfg["verfahren"], art=art, bundesland=args["land"],
                 rechtsbehelfsbelehrung="vorhanden" if args.get("rbb", True) else "fehlt",
                 datum_schreiben=zusatz.get("bescheid_datum"))
        pruefbar += ["schreiben", "verfahren", "art", "bundesland", "rechtsbehelfsbelehrung"]
        if args.get("zustellart", "brief") == "brief":
            f.update(zustellart="einfacher_brief", datum_aufgabe_post=args.get("aufgabe_post"))
            pruefbar += ["datum_aufgabe_post"] + (["zustellart"] if args.get("aufgabe_post") else [])
        else:
            f.update(zustellart="zustellungsurkunde", datum_zustellung=args.get("zustellung"))
            pruefbar += ["zustellart", "datum_zustellung"]
    elif fn == "kschg_klage":
        f.update(schreiben="kuendigung_arbeitsverhaeltnis", art="kschg_klage", bundesland=args["land"],
                 datum_zugang=args.get("zugang"), kuendigende_partei="arbeitgeber")
        pruefbar += ["schreiben", "art", "bundesland", "datum_zugang", "kuendigende_partei"]
    elif fn == "kuendigung_miete":
        partei = args.get("partei", "mieter")
        f.update(schreiben="kuendigung_mietverhaeltnis", art="kuendigung_miete", bundesland=args["land"],
                 datum_zugang=args.get("zugang"), kuendigende_partei=partei, ueberlassung=args.get("ueberlassung"),
                 datum_schreiben=zusatz.get("schreiben_vom"))
        pruefbar += ["schreiben", "art", "bundesland", "datum_zugang", "kuendigende_partei"]
        if partei == "vermieter":
            pruefbar.append("ueberlassung")
    elif fn == "kuendigung_arbeit":
        probezeit = bool(args.get("probezeit"))
        f.update(schreiben="kuendigung_arbeitsverhaeltnis", art="kuendigung_arbeit", bundesland=args.get("land"),
                 datum_zugang=args.get("zugang"), kuendigende_partei=args.get("partei", "arbeitgeber"),
                 beschaeftigungsbeginn=args.get("beginn"), probezeit=True if probezeit else None,
                 probezeit_monate=args.get("probezeit_monate", 6) if probezeit else None)
        pruefbar += ["schreiben", "art", "bundesland", "datum_zugang", "kuendigende_partei",
                     "beschaeftigungsbeginn", "probezeit"] + (["probezeit_monate"] if probezeit else [])
    else:
        raise ValueError(f"Unbekannte Funktion {fn!r}")
    if f["datum_schreiben"]:
        pruefbar.append("datum_schreiben")
    if aufgabe["typ"] == "pruefen":
        f["genanntes_fristende"] = p.get("genannt")
        pruefbar.append("genanntes_fristende")
    return f, pruefbar


def gleich(feld: str, soll, ist) -> bool:
    """Feldvergleich für die Fehleranalyse; bei probezeit gilt null wie false (Dokument schweigt)."""
    if feld == "probezeit":
        return bool(soll) == bool(ist)
    return soll == ist


# ----------------------------------------------------------------- Gegenproben (v3, nur Code)
#
# Allgemeine Lese- und Rechtsregeln, keine Namen, Wendungen oder Fallen aus generator.py. Die Quelle im Dokument
# gilt als stärker als die Auslese des Modells; setzt eine Regel einen Wert gegen die Auslese, rechnet die Kette
# mit Sicherheit 0,6 (MIT_ANNAHME). Reine Zweifel ändern keinen Wert, senken nur die Sicherheit.
REGELN = {
    "P": {"text": "Wer kündigt das Mietverhältnis? Schreibt die kündigende Person in der Ich-Form über ihre eigene "
                  "Wohnung („meine Wohnung“, „mein Mietverhältnis“, „ich bin Mieterin“) und spricht nichts für den "
                  "Vermieter („Ihre Wohnung“, „Eigenbedarf“, „Sie als Mieter“, „kündigen wir“), kündigt der Mieter; "
                  "umgekehrt der Vermieter. Sprechen beide Seiten dafür, bleibt die Auslese und es gibt einen Zweifel. "
                  "Gefunden 16.10.: Mieterin als Vermieterin gelesen (Seed 20261016 F049, fremd_probe D).",
          "norm": "§ 573c Abs. 1 BGB (Frist hängt davon ab, wer kündigt)"},
    "D1": {"text": "Ein ausgelesenes Datum muss im Dokument stehen; sonst gilt das Feld als unlesbar "
                   "(das Modell schreibt ab, es rechnet nicht). Das Datum der Aufgabe zur Post muss zudem in einer "
                   "Zeile mit einem Post-Wort stehen (Post, Versand, abgesandt, aufgegeben, Brief).",
           "norm": "keine Rechtsnorm (Leseregel)"},
    "D2": {"text": "Ein Datum, das im Dokument nur einmal steht, belegt nur ein Ereignis. Steht es zugleich als "
                   "Datum des Schreibens und als Ereignistag (Aufgabe zur Post, Zustellung, Zugang, Überlassung, "
                   "Beschäftigungsbeginn, genanntes Fristende) in der Auslese, gilt es als Datum des Schreibens. "
                   "Teilen sich zwei Ereignisse, die beide in die Rechnung eingehen, ein einmal genanntes Datum, "
                   "gilt der Tag der Bekanntgabe (Aufgabe zur Post, Zustellung, Zugang) als nicht belegt und wird "
                   "nachgefragt; sind beide keine Bekanntgabe, ist keines belegt. Ein Wert aus der Nachfrage geht "
                   "einer Kopie in einem anderen Feld vor, nie dem Datum des Schreibens. Felder, die für die "
                   "erkannte Art nicht zählen, bleiben außer Betracht. Das Datum des Schreibens beweist weder "
                   "Absendung noch Zugang. Grenze (an echten Dokumenten ungeprüft): Ein Ereignis am Tag des "
                   "Schreibens, dessen Datum der Text nicht wiederholt („am heutigen Tag erhalten“), gilt so als "
                   "nicht belegt; dann folgt eine Rückfrage mit Sicherheit 0,6, nie ein sicheres Ergebnis.",
           "norm": "§ 41 Abs. 2 VwVfG, § 37 Abs. 2 SGB X, § 122 Abs. 2 AO (Fiktion ab Aufgabe zur Post); "
                   "§ 130 Abs. 1 Satz 1 BGB (Zugang, nicht Abgabe); § 573c Abs. 1 Satz 2 BGB, § 622 Abs. 2 BGB"},
    "V": {"text": "Rechtsweg aus dem Gericht in der Rechtsbehelfsbelehrung oder Frage (stärkste Quelle), dann der "
                  "Rechtsbehelf (Einspruch: AO; Widerspruch: nicht AO), dann ein im Dokument genanntes Gesetz. "
                  "Das Gericht bestimmt den Rechtsweg, nicht das Verfahrensgesetz: Der Rechner verbindet beide nur "
                  "nach dem Regelfall (Sozialgericht und SGB X, Verwaltungsgericht und VwVfG, Finanzgericht und "
                  "AO). Ausnahmen kennt er nicht, etwa SGB X mit Rechtsweg zum Verwaltungsgericht (§ 68 SGB I: "
                  "Ausbildungsförderung, Wohngeld, Kinder- und Jugendhilfe) oder Teile der AO bei Realsteuern der "
                  "Gemeinden (§ 1 Abs. 2 AO). Widerspricht die Auslese dem Dokument, gilt das Dokument. "
                  "Widersprechen sich die Quellen im Dokument (etwa Verwaltungsgericht und ein Buch des SGB), gilt "
                  "die stärkere, und die Sicherheit sinkt, weil ein solcher Sonderfall vorliegen kann.",
          "norm": "§ 51 Abs. 1 SGG, § 40 Abs. 1 VwGO, § 33 Abs. 1 FGO (Rechtsweg); § 347 Abs. 1 AO, § 68 Abs. 1 VwGO, "
                  "§ 78 Abs. 1 SGG (Rechtsbehelf); § 1 Abs. 1 SGB X, § 1 Abs. 1 AO, § 1 Abs. 1 VwVfG "
                  "(Anwendungsbereich); § 68 SGB I, § 1 Abs. 2 AO (Ausnahmen)"},
    "S": {"text": "Bescheid oder Widerspruchsbescheid aus dem Rechtsbehelf in Belehrung oder Frage: nur Klage "
                  "-> Klagefrist (Widerspruchsbescheid); nur Widerspruch oder Einspruch -> Bescheid.",
          "norm": "§ 68 Abs. 1 VwGO, § 78 Abs. 1 SGG, § 347 Abs. 1 AO (Vorverfahren); § 74 Abs. 1 VwGO, "
                  "§ 87 Abs. 2 SGG (Klage nach dem Widerspruchsbescheid)"},
    "B": {"text": "Eine Rechtsbehelfsbelehrung nennt Rechtsbehelf und Frist. Steht im Dokument weder eine "
                  "Belehrung noch eine Stelle mit Rechtsbehelf und Frist, fehlt sie (dann gilt die Jahresfrist). "
                  "Belehrt der Bescheid unter einer eigenen Überschrift „Rechtsbehelfsbelehrung“ (vor jedem Vermerk, "
                  "nicht verneint) über Widerspruch, Einspruch oder Klage, die Stelle und eine Frist von einem Monat, "
                  "ist sie vorhanden, auch wenn die Auslese „fehlt“ sagt (Sicherheit 0,6). Sonst bleibt „fehlt“ nur "
                  "mit Zweifel, wenn das Dokument Rechtsbehelf und Frist oder eine Belehrung nennt (die Stelle kann "
                  "eine Anmerkung Dritter sein). Ob die Belehrung richtig und vollständig ist (etwa der Sitz, § 58 "
                  "Abs. 2 VwGO), prüft die Regel nicht.",
          "norm": "§ 58 Abs. 1 und 2 VwGO, § 66 Abs. 1 und 2 SGG, § 356 Abs. 1 und 2 AO, § 37 Abs. 6 VwVfG, "
                  "§ 36 SGB X"},
    "Z": {"text": "Bei Prüfaufgaben liegt ein genanntes Fristende nach dem Ereignistag (die Frist beginnt erst am "
                  "Folgetag); sonst Zweifel.",
          "norm": "§ 187 Abs. 1 BGB, § 31 Abs. 1 VwVfG, § 26 Abs. 1 SGB X, § 108 Abs. 1 AO, § 222 Abs. 1 ZPO"},
    "N": {"text": "Ein Wert aus der Nachfrage zählt nur mit Beleg: Die Fundstelle ist angegeben, steht wörtlich im "
                  "Dokument (Leerraum, Groß- und Kleinschreibung, Anführungszeichen und Striche zählen nicht) und "
                  "enthält mehr als ein Datum; ein Datum muss in der Fundstelle selbst stehen. Sonst wird der Wert "
                  "verworfen (dann Rückfrage).",
          "norm": "keine Rechtsnorm (Leseregel)"},
}

_MONATE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
           "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
           # Abkürzungen wie auf Eingangsstempeln („02. APR. 2026“, „3. Mrz. 2026“)
           "jan": 1, "feb": 2, "mär": 3, "mrz": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sept": 9, "sep": 9,
           "okt": 10, "nov": 11, "dez": 12}
_D_ZAHL = re.compile(r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)")
_D_WORT = re.compile(r"(?<!\d)(\d{1,2})\.\s?(" + "|".join(sorted(_MONATE, key=len, reverse=True))
                     + r")(?![a-zäöü])\.?\s+(\d{4})(?!\d)", re.I)
_D_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


@lru_cache(maxsize=512)
def datumsangaben(dokument: str) -> Counter:
    """Alle Kalenderdaten im Text (TT.MM.JJJJ, T.M.JJ, „1. Juli 2026“, ISO) -> Anzahl je ISO-Datum.
    Rückgabe nicht verändern (zwischengespeichert)."""
    zaehler: Counter = Counter()

    def dazu(j, m, t):
        j = int(j)
        j = 2000 + j if j < 100 else j
        try:
            zaehler[date(j, int(m), int(t)).isoformat()] += 1
        except ValueError:
            pass
    for m in _D_ZAHL.finditer(dokument):
        dazu(m[3], m[2], m[1])
    for m in _D_WORT.finditer(dokument):
        dazu(m[3], _MONATE[m[2].lower()], m[1])
    for m in _D_ISO.finditer(dokument):
        dazu(m[1], m[2], m[3])
    return zaehler


_RBB_KOPF = re.compile(r"rechts(?:behelfs|mittel)belehrung", re.I)
_RB_WORT = re.compile(r"widerspruch|einspruch|klage|rechtsbehelf", re.I)
_DAUER = re.compile(r"\b(?:monat(?:s|es|e|en)?|wochen?|jahr(?:es|en|e)?|(?:monats|wochen|jahres)frist)\b", re.I)
# Für Regel B (Überschrift): eine eigene Zeile „Rechtsbehelfsbelehrung“ oder „Rechtsmittelbelehrung“, auch
# nummeriert, fett oder mit Klammerzusatz, mit oder ohne Text nach dem Doppelpunkt; kein Satz über eine Belehrung
# („Die Rechtsbehelfsbelehrung fehlt“)
_RBB_UEBERSCHRIFT = re.compile(r"^\s*(?:[0-9IVX]+[.)]\s*|[#*_]+\s*)?rechts(?:behelfs|mittel)belehrung[*_]*\s*"
                               r"(?:\([^)]*\))?\s*(?::(?P<rest>.*))?$", re.I)
# Kopf einer Anmerkung Dritter („— Vermerk: …“, „Notiz der Beratung“) oder der Behörde (Postausgang, Zustellung):
# Dort endet die Belehrung; eine Überschrift erst danach gehört nicht zum Bescheid
_ANMERKUNG = re.compile(r"^\s*(?:[—–-]+\s|notiz|anmerkung|hinweis (?:der|des|von)\b|im auftrag\b)|vermerk|"
                        r"zustellungsurkunde", re.I)
_BELEHRUNG_WORT = re.compile(r"rechts(?:behelfs|mittel)belehrung\w*", re.I)
_RB_KLAR = re.compile(r"widerspruch(?!sbescheid)|einspruch|klage", re.I)
_MONAT = re.compile(r"\bmonat(?:s|es|e|en)?\b|\bmonatsfrist\b", re.I)
# Stelle: „beim …“, „bei der/dem …“ oder ein Gericht des Rechtswegs (nicht „Bei Fragen …“)
_STELLE = re.compile(r"\bbeim\s+\w|\bbei\s+(?:der|dem)\s+\w|(?:sozial|verwaltungs|finanz)gericht", re.I)
_VERNEINT = re.compile(r"\b(?:nicht|keine?[nrs]?|fehlt|fehlen|entfällt|entfallen|unterblieben|ohne)\b", re.I)
_EINSPRUCH = re.compile(r"einspruch", re.I)
_WIDERSPRUCH = re.compile(r"widerspruch(?!sbescheid)", re.I)
_KLAGE = re.compile(r"klage", re.I)
# Gericht -> Rechtsweg; das Verfahrensgesetz folgt daraus nur im Regelfall (REGELN["V"])
_GERICHTE = (("SGB X", re.compile(r"sozialgericht", re.I), "§ 51 Abs. 1 SGG", "Sozialgericht"),
             ("VwVfG", re.compile(r"verwaltungsgericht", re.I), "§ 40 Abs. 1 VwGO", "Verwaltungsgericht"),
             ("AO", re.compile(r"finanzgericht", re.I), "§ 33 Abs. 1 FGO", "Finanzgericht"))
# Genannte Gesetze; zum SGB zählen auch die Gesetze, die nach § 68 SGB I als seine besonderen Teile gelten
# (Auswahl: Ausbildungsförderung, Wohngeld, Unterhaltsvorschuss, Elterngeld; Kinder- und Jugendhilfe ist SGB VIII).
_GESETZE = (("SGB X", re.compile(r"\bSGB\b|\bSGG\b|\bBAföG\b|\bWoGG\b|\bUVG\b|\bBEEG\b|(?i:sozialgesetzbuch|"
                                 r"ausbildungsförderung|wohngeld|unterhaltsvorschuss|elterngeld|"
                                 r"kinder- und jugendhilfe)"), "§ 1 Abs. 1 SGB X, § 68 SGB I"),
            ("AO", re.compile(r"\bAO\b|\bFGO\b|(?i:abgabenordnung)"), "§ 1 Abs. 1 AO"),
            ("VwVfG", re.compile(r"\bVwVfG\b|\bVwGO\b|(?i:verwaltungsverfahrensgesetz)"), "§ 1 Abs. 1 VwVfG"))
VERFAHREN_AUS_ART = {"widerspruch_sgb2": "SGB X", "klage_sgg": "SGB X", "widerspruch_vwvfg": "VwVfG",
                     "klage_vwgo": "VwVfG", "einspruch_ao": "AO"}
BEHOERDE = ("bescheid", "widerspruchsbescheid")
# Ereignisse für D2 (Zustellung und Zugang sind dasselbe Ereignis: Bekanntgabe an den Empfänger)
_EREIGNISSE = (("datum_schreiben",), ("datum_aufgabe_post",), ("datum_zustellung", "datum_zugang"), ("ueberlassung",),
               ("beschaeftigungsbeginn",), ("genanntes_fristende",))
_BEKANNTGABE = (("datum_aufgabe_post",), ("datum_zustellung", "datum_zugang"))


@lru_cache(maxsize=512)
def belehrung(dokument: str) -> tuple[tuple[str, ...], bool]:
    """Belehrungsstellen des Dokuments: Absatz unter einer Überschrift „Rechtsbehelfsbelehrung“ (bis zur
    Leerzeile) und jede Zeile, die einen Rechtsbehelf zusammen mit einer Frist nennt. Zweiter Wert: ob eine
    solche Überschrift vorkommt."""
    zeilen = dokument.splitlines()
    stellen: list[str] = []
    kopf = False
    i = 0
    while i < len(zeilen):
        if _RBB_KOPF.search(zeilen[i]):
            kopf = True
            j = i
            while j < len(zeilen) and zeilen[j].strip():
                j += 1
            stellen.append(" ".join(zeilen[i:j]))
            i = max(j, i + 1)
            continue
        if _RB_WORT.search(zeilen[i]) and _DAUER.search(zeilen[i]):
            stellen.append(zeilen[i])
        i += 1
    return tuple(stellen), kopf


def _mit_frist(stellen) -> bool:
    return any(_RB_WORT.search(s) and _DAUER.search(s) for s in stellen)


@lru_cache(maxsize=512)
def belehrung_unter_ueberschrift(dokument: str) -> bool:
    """Regel B: Ob der Bescheid unter einer eigenen Überschrift „Rechtsbehelfsbelehrung“ über Rechtsbehelf
    (Widerspruch, Einspruch, Klage), Stelle und Monatsfrist belehrt. Der Abschnitt reicht über höchstens vier
    Absätze bis zum Kopf einer Anmerkung (Vermerk, Postausgang, Zustellung, „Im Auftrag“). Nicht gezählt: eine
    Überschrift nach einer Anmerkung (Text Dritter), ein verneinter Text („Rechtsbehelfsbelehrung: nicht erteilt“,
    „Eine Rechtsbehelfsbelehrung liegt nicht bei“) und jede andere Frist als ein Monat (alle fünf Rechtsbehelfe der
    Kette haben eine Monatsfrist; eine falsche Frist macht die Belehrung unrichtig, § 58 Abs. 2 VwGO)."""
    zeilen = dokument.splitlines()
    for i, zeile in enumerate(zeilen):
        m = _RBB_UEBERSCHRIFT.match(zeile)
        if not m:
            continue
        if any(_ANMERKUNG.search(z) for z in zeilen[:i]):
            return False
        rest = (m.group("rest") or "").strip()
        if rest and _VERNEINT.search(rest):
            return False
        teile, absaetze, k = [rest], 0, i + 1
        while k < len(zeilen) and absaetze < 4:
            z = zeilen[k]
            if not z.strip():
                absaetze += 1
                k += 1
                continue
            if _ANMERKUNG.search(z) or _RBB_UEBERSCHRIFT.match(z):
                break
            teile.append(z)
            k += 1
        text = " ".join(teile)
        saetze = re.split(r"(?<=[.!?])\s+", text)
        if any(_BELEHRUNG_WORT.search(st) and _VERNEINT.search(st) for st in saetze):
            return False
        text = _BELEHRUNG_WORT.sub(" ", text)
        return bool(_RB_KLAR.search(text) and _MONAT.search(text) and _STELLE.search(text))
    return False


def _verfahren_quellen(dokument: str, frage: str = "") -> tuple[set | None, list[str], list[str], list[str]]:
    """Wie verfahren_aus_dokument, zusätzlich die Quellen, die der stärkeren widersprechen (verworfen)."""
    stellen, _ = belehrung(dokument)
    text = "\n".join([*stellen, frage or ""])
    quellen: list[tuple[str, set, str]] = []
    gerichte = [(v, n, g) for v, rx, n, g in _GERICHTE if rx.search(text)]
    if len({v for v, _, _ in gerichte}) == 1:
        v, n, g = gerichte[0]
        quellen.append((f"Gericht: {g} (Regelfall {v})", {v}, n))
    ein, wider = bool(_EINSPRUCH.search(text)), bool(_WIDERSPRUCH.search(text))
    if ein and not wider:
        quellen.append(("Rechtsbehelf Einspruch", {"AO"}, "§ 347 Abs. 1 AO"))
    elif wider and not ein:
        quellen.append(("Rechtsbehelf Widerspruch", {"SGB X", "VwVfG"}, "§ 68 Abs. 1 VwGO, § 78 Abs. 1 SGG"))
    gesetze = [(v, n) for v, rx, n in _GESETZE if rx.search(dokument)]
    if len({v for v, _ in gesetze}) == 1:
        quellen.append((f"Gesetz im Dokument ({gesetze[0][0]})", {gesetze[0][0]}, gesetze[0][1]))
    menge: set | None = None
    benutzt: list[str] = []
    normen: list[str] = []
    verworfen: list[str] = []
    for name, m, norm in quellen:
        if menge is None or menge & m:
            menge = set(m) if menge is None else menge & m
            benutzt.append(name)
            normen.append(norm)
        else:
            verworfen.append(name)
    return menge, benutzt, normen, verworfen


def verfahren_aus_dokument(dokument: str, frage: str = "") -> tuple[set | None, list[str], list[str]]:
    """Mögliche Verfahrensordnungen nach dem Dokument: (Menge oder None, benutzte Quellen, Normen).

    Quellen von stark nach schwach: Gericht (Belehrung oder Frage; bestimmt den Rechtsweg, das Verfahrensgesetz
    nur im Regelfall), Rechtsbehelf (Belehrung oder Frage), Gesetz (ganzes Dokument). Eine schwächere Quelle grenzt
    nur ein; widerspricht sie der stärkeren, zählt sie nicht (pruefe_recht meldet das als Zweifel)."""
    return _verfahren_quellen(dokument, frage)[:3]


def schreiben_aus_dokument(dokument: str, frage: str = "") -> str | None:
    """Bescheid (Widerspruch/Einspruch gegeben) oder Widerspruchsbescheid (nur Klage gegeben); None: unklar."""
    stellen, _ = belehrung(dokument)
    text = "\n".join([*stellen, frage or ""])
    klage = bool(_KLAGE.search(text))
    vor = bool(_EINSPRUCH.search(text) or _WIDERSPRUCH.search(text))
    if klage and not vor:
        return "widerspruchsbescheid"
    if vor and not klage:
        return "bescheid"
    return None


def _eintrag(regel, feld, gelesen, gesetzt, grund) -> dict:
    return {"regel": regel, "feld": feld, "gelesen": gelesen, "gesetzt": gesetzt, "grund": grund,
            "norm": REGELN[regel]["norm"]}


def relevante_felder(f: dict, typ: str, frage: str = "") -> set[str]:
    """Felder, die für die aus ``f`` erkannte Art in die Rechnung eingehen (wie rechne sie benutzt)."""
    return set(rechne(f, typ, frage)["rechnung"]["benutzt"]) | {"datum_schreiben"}


def pruefe_daten(f: dict, dokument: str, relevant: set[str] | None = None,
                 vorrang: set[str] | frozenset = frozenset()) -> tuple[list[dict], list[str]]:
    """D1 und D2 auf den Feldern ``f`` (wird verändert): (Einträge, verworfene Felder).

    ``relevant``: Felder, die in die Rechnung eingehen (relevante_felder); D2 vergleicht zwei Ereignisse nur,
    wenn beide zählen; kleine Modelle füllen unbenutzte Felder oft mit einer Kopie des richtigen Datums. None:
    alle Felder zählen. ``vorrang``: Felder aus der Nachfrage; sie gehen bei D2 einer Kopie in einem anderen
    Feld vor, nur nicht dem Datum des Schreibens."""
    vorkommen = datumsangaben(dokument)

    def zaehlt(g) -> bool:
        return relevant is None or any(n in relevant for n in g)
    eintraege: list[dict] = []
    weg: list[str] = []
    for n in PK.FELDNAMEN:
        v = f.get(n)
        if n in PK.DATUMSFELDER and v and not vorkommen.get(v):
            eintraege.append(_eintrag("D1", n, v, None, "Datum steht nicht im Dokument"))
            f[n] = None
            weg.append(n)
        elif n in _FUND_PASST and v and n not in vorrang and not any(
                _FUND_PASST[n].search(z) for z in dokument.splitlines() if datumsangaben(z).get(v)):
            # Seed v1 F043: Datum eines Beratungsvermerks als Aufgabe zur Post (84/84 echte Postdaten stehen neben
            # einem Post-Wort). Antworten der Nachfrage prüft Regel N mit derselben Wortliste.
            eintraege.append(_eintrag("D1", n, v, None, "Datum steht in keiner Zeile, die zu diesem Feld passt"))
            f[n] = None
            weg.append(n)
        elif n in _BEKANNTGABE_FELDER and v and nur_in_anmerkung_dritter(dokument, v):
            eintraege.append(_eintrag("D1", n, v, None, "Datum steht nur im Kopf einer Anmerkung Dritter"))
            f[n] = None
            weg.append(n)
    verwerfen: dict[str, str] = {}
    for i, gi in enumerate(_EREIGNISSE):
        for gj in _EREIGNISSE[i + 1:]:
            if gi != ("datum_schreiben",) and not (zaehlt(gi) and zaehlt(gj)):
                continue
            gemeinsam = {f[n] for n in gi if f.get(n)} & {f[n] for n in gj if f.get(n)}
            for v in gemeinsam:
                if vorkommen.get(v, 0) >= 2:
                    continue
                if gi == ("datum_schreiben",):
                    gruppen = (gj,)                                   # Anker: das Datum des Schreibens
                elif vorrang & {*gi, *gj}:
                    gruppen = tuple(g for g in (gi, gj) if not vorrang & set(g))
                elif (gi in _BEKANNTGABE) != (gj in _BEKANNTGABE):
                    gruppen = tuple(g for g in (gi, gj) if g in _BEKANNTGABE)   # wird nachgefragt
                else:
                    gruppen = (gi, gj)
                for g in gruppen:
                    for n in g:
                        if f.get(n) == v:
                            verwerfen[n] = f"{ds(v)} steht nur einmal im Dokument und belegt nur ein Ereignis"
    for n, grund in verwerfen.items():
        eintraege.append(_eintrag("D2", n, f[n], None, grund))
        f[n] = None
        weg.append(n)
    return eintraege, weg


_MIETER_ICH = re.compile(r"\b(?:meine[rm]?\s+(?:miet)?wohnung|mein(?:em)?\s+mietverhältnis|mein(?:es|en)?\s+mietvertrag"
                        r"(?:s|es)?\b|ich\s+bin\b[^.\n]{0,40}\bmieter(?:in)?\b)", re.I)
_VERMIETER = re.compile(r"\b(?:ihre[rm]?\s+(?:miet)?wohnung|ihr(?:em)?\s+mietverhältnis|die\s+von\s+ihnen\s+"
                        r"(?:gemietete|bewohnte)|eigenbedarfs?|sie\s+als\s+mieter(?:in)?|kündigen\s+wir)\b", re.I)


def partei_aus_dokument(dokument: str) -> str | None:
    """Regel P: 'mieter' oder 'vermieter', wenn nur eine Seite im Text Spuren hinterlässt; sonst None."""
    m, v = bool(_MIETER_ICH.search(dokument)), bool(_VERMIETER.search(dokument))
    return "mieter" if m and not v else "vermieter" if v and not m else None


def pruefe_recht(f: dict, dokument: str, frage: str, typ: str) -> tuple[list[dict], list[str], list[str]]:
    """P, V, S, B auf den Feldern ``f`` (wird verändert): (Einträge, Annahmen, Zweifel)."""
    eintraege: list[dict] = []
    annahmen: list[str] = []
    zweifel: list[str] = []
    if f.get("schreiben") == "kuendigung_mietverhaeltnis" or f.get("art") == "kuendigung_miete":   # P
        p_dok, p = partei_aus_dokument(dokument), f.get("kuendigende_partei")
        if p_dok and p != p_dok:
            eintraege.append(_eintrag("P", "kuendigende_partei", p, p_dok, "Ich-Form bzw. Anrede im Dokument"))
            if p is not None:
                annahmen.append(f"Gegenprobe P: kündigende Partei {p} passt nicht zum Text; gerechnet als {p_dok}")
            f["kuendigende_partei"] = p_dok
    behoerde = f.get("schreiben") in BEHOERDE or (f.get("schreiben") is None and f.get("art") in RB_ARTEN)
    if f.get("schreiben") in BEHOERDE:                                     # S
        s = schreiben_aus_dokument(dokument, frage)
        if s and s != f["schreiben"]:
            eintraege.append(_eintrag("S", "schreiben", f["schreiben"], s, "Rechtsbehelf in Belehrung oder Frage"))
            annahmen.append(f"Gegenprobe S: schreiben {f['schreiben']} passt nicht zum Rechtsbehelf; gerechnet als {s}")
            f["schreiben"] = s
    if behoerde:                                                           # V
        menge, quellen, _, gegen = _verfahren_quellen(dokument, frage)
        if gegen:
            zweifel.append(f"Gegenprobe V: Quellen im Dokument widersprechen sich ({', '.join(quellen)} gegen "
                           f"{', '.join(gegen)}); Sonderfall möglich, gerechnet nach der stärkeren")
        v = f.get("verfahren")
        if menge and v not in menge:
            if len(menge) == 1:
                neu = next(iter(menge))
            else:
                neu = VERFAHREN_AUS_ART.get(f.get("art"))
                neu = neu if neu in menge else None
        if menge and v not in menge and neu != v:
            grund = ", ".join(quellen)
            eintraege.append(_eintrag("V", "verfahren", v, neu, grund))
            if v is not None:
                annahmen.append(f"Gegenprobe V: verfahren {v} widerspricht dem Dokument ({grund}); "
                                f"gerechnet mit {neu or 'Art der Auslese'}")
            f["verfahren"] = neu
        stellen, kopf = belehrung(dokument)                                # B
        mit_frist = _mit_frist(stellen)
        r = f.get("rechtsbehelfsbelehrung")
        if r == "vorhanden" and not mit_frist and not kopf:
            eintraege.append(_eintrag("B", "rechtsbehelfsbelehrung", r, "fehlt",
                                      "keine Belehrung und keine Stelle mit Rechtsbehelf und Frist im Dokument"))
            annahmen.append("Gegenprobe B: keine Rechtsbehelfsbelehrung im Dokument; gerechnet ohne (Jahresfrist)")
            f["rechtsbehelfsbelehrung"] = "fehlt"
        elif r == "fehlt" and belehrung_unter_ueberschrift(dokument):
            eintraege.append(_eintrag("B", "rechtsbehelfsbelehrung", r, "vorhanden",
                                      "Belehrung unter eigener Überschrift nennt Rechtsbehelf, Stelle und Frist"))
            annahmen.append("Gegenprobe B: Rechtsbehelfsbelehrung unter eigener Überschrift im Dokument; "
                            "gerechnet mit Belehrung")
            f["rechtsbehelfsbelehrung"] = "vorhanden"
        elif r == "fehlt" and (mit_frist or kopf):
            grund = "Dokument nennt Rechtsbehelf und Frist" if mit_frist else "Dokument nennt eine Rechtsbehelfsbelehrung"
            eintraege.append(_eintrag("B", "rechtsbehelfsbelehrung", r, r, grund))
            zweifel.append(f"Gegenprobe B: {grund}, Auslese sagt „fehlt“")
        elif r is None and (mit_frist or not kopf):
            neu = "vorhanden" if mit_frist else "fehlt"
            eintraege.append(_eintrag("B", "rechtsbehelfsbelehrung", None, neu,
                                      "Rechtsbehelf und Frist im Dokument" if mit_frist else "keine Belehrung im Dokument"))
            if neu == "fehlt":
                annahmen.append("Gegenprobe B: Belehrung nicht ausgelesen und nicht im Dokument; gerechnet ohne")
            f["rechtsbehelfsbelehrung"] = neu
    return eintraege, annahmen, zweifel


def pruefe_zeitfolge(f: dict, typ: str) -> tuple[list[dict], list[str]]:
    """Z: bei Prüfaufgaben liegt das genannte Fristende nach dem Ereignistag; sonst Zweifel."""
    eintraege: list[dict] = []
    zweifel: list[str] = []
    genannt = f.get("genanntes_fristende")
    if typ == "pruefen" and genannt:
        for n in ("datum_aufgabe_post", "datum_zustellung", "datum_zugang"):
            if f.get(n) and f[n] >= genannt:
                eintraege.append(_eintrag("Z", n, f[n], f[n], f"genanntes Fristende {ds(genannt)} liegt nicht danach"))
                zweifel.append(f"Gegenprobe Z: {n} {ds(f[n])} liegt nicht vor dem genannten Fristende")
    return eintraege, zweifel


def gegenpruefe(felder: dict, dokument: str, frage: str = "", typ: str = "berechnen") -> dict:
    """Alle Gegenproben auf einer Kopie von ``felder``, in der Reihenfolge der Kette: V, S, B (Recht), dann
    D1, D2 (Daten, D2 nur für die Felder der erkannten Art), dann Z.

    Rückgabe {'felder', 'gegenproben' (Einträge mit Regel und Norm), 'unlesbar' (verworfene Daten),
    'annahmen', 'zweifel'}."""
    f = dict(felder)
    e1, annahmen, zweifel = pruefe_recht(f, dokument, frage, typ)
    e2, weg = pruefe_daten(f, dokument, relevante_felder(f, typ, frage))
    e3, z = pruefe_zeitfolge(f, typ)
    return {"felder": f, "gegenproben": e1 + e2 + e3, "unlesbar": weg, "annahmen": annahmen,
            "zweifel": zweifel + z}


# ----------------------------------------------------------------- Nachfrage (v3)

def nachfrage_feld(rechnung: dict | None) -> str | None:
    """Das eine Feld für die Nachfrage: nötig für die erkannte Art und nach der Auslese leer; sonst None."""
    if not rechnung or rechnung.get("art") is None or rechnung.get("fehler"):
        return None
    fehlend = rechnung.get("fehlend") or []
    return next((n for n in PK.NACHFRAGE_REIHENFOLGE if n in fehlend), None)


_ZIEL_DATUM = {"einfacher_brief": "datum_aufgabe_post", "zustellungsurkunde": "datum_zustellung",
               "persoenliche_uebergabe": "datum_zugang"}


_ZEICHEN = str.maketrans({"„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'", "’": "'", "–": "-", "—": "-",
                          " ": " "})


def _vereinheitlicht(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).translate(_ZEICHEN)).strip().lower()


# Wörter, ohne die eine Fundstelle das Feld nicht trägt (gefunden 16.10.: Datum eines Beratungsvermerks als
# „Aufgabe zur Post“ übernommen, obwohl der Brief sagt, dass kein Postvermerk vorliegt)
_FUND_PASST = {"datum_aufgabe_post": re.compile(r"post|versand|abgesandt|abgesendet|aufgegeben|brief", re.I)}
# Kopfzeile einer Anmerkung Dritter („— Vermerk: Sozialberatung …, 10.04.2025 —“, mit Strich davor): Ihr
# Datum ist der Tag der Notiz, kein Tag der Bekanntgabe (Seed 20261024 F012: Zustelldatum aus dem Beratungsvermerk).
# Vermerke der Behörde („Ab-Vermerk: …“) und Sätze wie „Hinweis der Beratungsstelle: … erhalten am …“ haben
# keinen Strich davor und bleiben Fundstellen.
_DRITTE_KOPF = re.compile(r"^\s*[—–-]+\s*(?:vermerk|notiz|anmerkung)\b", re.I)
_BEKANNTGABE_FELDER = frozenset({"datum_aufgabe_post", "datum_zustellung", "datum_zugang"})


def nur_in_anmerkung_dritter(dokument: str, wert: str) -> bool:
    """Ob das Datum ``wert`` nur in Kopfzeilen von Anmerkungen Dritter steht (und mindestens einmal dort)."""
    zeilen = [z for z in dokument.splitlines() if datumsangaben(z).get(wert)]
    return bool(zeilen) and all(_DRITTE_KOPF.search(z) for z in zeilen)


def fundstelle_mangel(fund, dokument: str, feld: str | None = None) -> str | None:
    """Regel N, erster Teil: None, wenn die Fundstelle trägt; sonst der Grund. Sie muss angegeben sein, wörtlich im
    Dokument stehen (Leerraum, Groß/Klein, Anführungszeichen, Striche egal; „…“ oder „...“ trennt Teile, die je für
    sich im Dokument stehen müssen), außer Daten mindestens ein Wort enthalten und für ``feld`` (falls in
    _FUND_PASST) ein passendes Wort, z. B. „Post“ für das Datum der Aufgabe zur Post."""
    if not isinstance(fund, str) or not fund.strip():
        return "keine Fundstelle angegeben"
    doc = _vereinheitlicht(dokument)
    teile = [t.strip(" \"'.,;:-") for t in re.split(r"…|\.\.\.", _vereinheitlicht(fund))]
    teile = [t for t in teile if t]
    if not teile or not all(t in doc for t in teile):
        return "Fundstelle steht nicht wörtlich im Dokument"
    ohne_daten = _D_ISO.sub(" ", _D_WORT.sub(" ", _D_ZAHL.sub(" ", " ".join(teile))))
    if not re.search(r"[a-zäöüß]{2,}", ohne_daten):
        return "Fundstelle enthält nur ein Datum"
    if feld in _FUND_PASST and not _FUND_PASST[feld].search(ohne_daten):
        return f"Fundstelle passt nicht zu {feld}"
    if feld in _BEKANNTGABE_FELDER and any(
            _DRITTE_KOPF.search(z) and any(t in _vereinheitlicht(z) for t in teile) for z in dokument.splitlines()):
        return "Fundstelle ist der Kopf einer Anmerkung Dritter (Datum der Notiz, nicht der Bekanntgabe)"
    return None


def ersatz_fundstelle(dokument: str, feld: str, wert: str) -> str | None:
    """Regel N, Ersatz (17.10., Vorlagen v2): Trägt die genannte Fundstelle ein Datum nicht, sucht der Code selbst die
    Zeile. Übernommen wird es nur, wenn genau eine Zeile des Dokuments dieses Datum enthält und für ``feld`` trägt
    (fundstelle_mangel mit passendem Wort). Nur für Felder in _FUND_PASST, sonst None."""
    if feld not in _FUND_PASST:
        return None
    passend = [z.strip() for z in dokument.splitlines()
               if datumsangaben(z).get(wert) and fundstelle_mangel(z, dokument, feld) is None]
    return passend[0] if len(passend) == 1 else None


def lies_nachfrage(feld: str, roh_text: str | None, dokument: str | None = None) -> tuple[dict, dict]:
    """Antwort auf die Nachfrage -> (Werte für die Felder, Info für die Ergebniszeile).

    Mit ``dokument`` gilt Regel N: ohne tragende Fundstelle (fundstelle_mangel) wird jeder Wert verworfen, ein Datum
    außerdem, wenn es nicht in der Fundstelle steht. Verworfenes steht in info["verworfen"] (Feld, Wert, Grund).
    Ausnahme ersatz_fundstelle: genau eine passende Zeile mit dem Datum trägt es (info["fundstelle_ersetzt"])."""
    obj = P._json_objekt(roh_text) if roh_text else None
    info: dict = {"feld": feld, "fundstelle": None, "werte": {}, "hinweis": None, "verworfen": []}
    if not isinstance(obj, dict):
        info["hinweis"] = "Antwort ist kein JSON-Objekt"
        return {}, info
    fund = obj.get("fundstelle")
    info["fundstelle"] = str(fund)[:300] if fund not in (None, "") else None
    werte: dict = {}
    if feld == "zustellart":
        za, _ = lies_feld("zustellart", obj.get("zustellart"))
        tag, _ = lies_datum(obj.get("datum"))
        if za:
            werte["zustellart"] = za
            if tag:
                werte[_ZIEL_DATUM[za]] = tag
    else:
        w, kaputt = lies_feld(feld, obj.get(feld))
        if w is not None:
            werte[feld] = w
        elif kaputt:
            info["hinweis"] = f"{feld} unlesbar: {str(obj.get(feld))[:40]!r}"
    if dokument is not None and werte:
        mangel = fundstelle_mangel(fund, dokument, feld)
        daten_der_stelle = datumsangaben(str(fund)) if mangel is None else Counter()
        for n, w in list(werte.items()):
            grund = mangel or (None if n not in PK.DATUMSFELDER or daten_der_stelle.get(w)
                               else "Datum steht nicht in der Fundstelle")
            zeile = ersatz_fundstelle(dokument, n, w) if grund and n in PK.DATUMSFELDER else None
            if zeile:
                info.setdefault("fundstelle_ersetzt", []).append({"feld": n, "wert": w, "zeile": zeile[:300],
                                                                  "grund": grund})
            elif grund:
                info["verworfen"].append({"feld": n, "wert": w, "grund": grund})
                del werte[n]
    info["werte"] = werte
    return werte, info


def orakel_nachfrage(aufgabe: dict, feld: str) -> dict:
    """Antwort des Orakels auf eine Nachfrage: der wahre Wert, als Fundstelle die erste Zeile des Dokuments, in der
    er steht (null, wenn die Angabe im Dokument fehlt, wie bei den Rückfrage-Aufgaben)."""
    wahr = als_modellausgabe(orakel_felder(aufgabe)[0])
    if feld == "zustellart":
        za = wahr["zustellart"]
        antwort = {"zustellart": za, "datum": wahr.get(_ZIEL_DATUM[za]) if za else None}
        beleg = antwort["datum"] or za
    else:
        antwort = {feld: wahr[feld]}
        beleg = wahr[feld]
    zeile = next((z.strip() for z in aufgabe["dokument"].splitlines() if beleg and str(beleg) in z), None)
    return {"fundstelle": zeile, **antwort}


# ----------------------------------------------------------------- Läufe

def _auslese_chat(chat_fn, host, modell, nachrichten, args, optionen, zustand, schema=None) -> tuple[dict, str]:
    """Ruft das Modell mit dem Schema auf; lehnt der Server das Schema ab, ab dann mit format 'json'."""
    if zustand["format"] == "schema":
        try:
            return chat_fn(host, modell, nachrichten, think=args.think, timeout=args.timeout, optionen=optionen,
                           format_=schema or PK.SCHEMA, keep_alive=args.keep_alive), "schema"
        except RuntimeError as e:
            text = str(e).lower()
            if not any(w in text for w in ("format", "schema", "grammar")):
                raise
            zustand["format"] = "json"
            print(f"  {modell}: Server lehnt das JSON-Schema ab ({str(e)[:120]}); weiter mit format 'json'.",
                  flush=True)
    return chat_fn(host, modell, nachrichten, think=args.think, timeout=args.timeout, optionen=optionen,
                   format_="json", keep_alive=args.keep_alive), "json"


def verarbeite(aufgabe: dict, roh_text: str | None, fassung: str | None = None,
               nachfrage: tuple[str, str | None] | None = None, gegenprobe: bool = True) -> dict:
    """Rohtext der Auslese -> Teil einer Ergebniszeile (antwort, antwort_json, felder, rechnung).

    v2: normalisieren und rechnen. v3 zusätzlich: Rechtsproben (V, S, B), Datumsprüfung (D1, D2), dann die
    Antwort der Nachfrage (``nachfrage`` = (Feld, Rohtext), nur in leere Felder; vorher Regel N: Fundstelle) mit
    erneuter Datumsprüfung, dann die Zeitfolge (Z) und erst danach der Rechner. ``felder`` ist, womit gerechnet
    wurde; ``felder_auslese`` die erste Auslese.

    ``aufgabe["typ"]`` ist die Auftragsart (berechnen oder prüfen). Sie steht offen in der Frage, im Echtbetrieb gibt
    sie der Aufrufer mit; sie verrät keinen Sollwert, und das Modell bekommt sie nicht (nur Dokument und Frage)."""
    fassung = fassung or PK.STANDARD
    felder_roh = P._json_objekt(roh_text) if roh_text else None
    felder, hinweise, unlesbar = _normalisiere(felder_roh)
    frage, typ = aufgabe.get("frage", ""), aufgabe["typ"]
    if felder is None:
        leer = {"antwort": None, "antwort_json": None, "felder_roh": felder_roh, "felder": None,
                "rechnung": None, "hinweise": hinweise}
        if fassung != "v2":
            leer.update(felder_auslese=None, gegenproben=[], nachfrage_info=None)
        return leer
    if fassung == "v2":
        erg = rechne(felder, typ, frage, unlesbar)
        antwort = erg["antwort"]
        return {"antwort": json.dumps(antwort, ensure_ascii=False) if antwort else None,
                "antwort_json": P.lies_antwort(antwort) if antwort else None,
                "felder_roh": felder_roh, "felder": felder, "rechnung": erg["rechnung"], "hinweise": hinweise}

    dokument = aufgabe["dokument"]
    felder_auslese = dict(felder)
    unlesbar = list(unlesbar)
    eintraege: list[dict] = []
    annahmen: list[str] = []
    zweifel: list[str] = []
    if gegenprobe:
        e, annahmen, zweifel = pruefe_recht(felder, dokument, frage, typ)
        eintraege += e
        e, weg = pruefe_daten(felder, dokument, relevante_felder(felder, typ, frage))
        eintraege += e
        unlesbar += [n for n in weg if n not in unlesbar]
    info = None
    if nachfrage is not None:
        feld, text = nachfrage
        werte, info = lies_nachfrage(feld, text, dokument if gegenprobe else None)
        eintraege += [_eintrag("N", v["feld"], v["wert"], None, v["grund"]) for v in info["verworfen"]]
        gesetzt = [n for n, w in werte.items() if felder.get(n) is None]
        for n in gesetzt:
            felder[n] = werte[n]
        if gegenprobe and gesetzt:
            e, weg = pruefe_daten(felder, dokument, relevante_felder(felder, typ, frage), vorrang=set(gesetzt))
            eintraege += e
            unlesbar += [n for n in weg if n not in unlesbar]
        info["uebernommen"] = [n for n in gesetzt if felder.get(n) is not None]
        if info["uebernommen"]:
            annahmen.append(f"{', '.join(info['uebernommen'])} erst auf Nachfrage gelesen")
            # erst auf Nachfrage gelesen: ein vorher verworfener Wert ist jetzt ersetzt, nicht mehr „unlesbar“
            unlesbar = [n for n in unlesbar if n not in info["uebernommen"]]
    if gegenprobe:
        e, z = pruefe_zeitfolge(felder, typ)
        eintraege += e
        zweifel += z
    erg = rechne(felder, typ, frage, unlesbar, vorab={"annahmen": annahmen, "zweifel": zweifel})
    erg["rechnung"]["gegenproben"] = eintraege
    antwort = erg["antwort"]
    return {"antwort": json.dumps(antwort, ensure_ascii=False) if antwort else None,
            "antwort_json": P.lies_antwort(antwort) if antwort else None,
            "felder_roh": felder_roh, "felder_auslese": felder_auslese, "felder": felder,
            "rechnung": erg["rechnung"], "hinweise": hinweise, "gegenproben": eintraege, "nachfrage_info": info}


def kettenname(modell: str | None, fassung: str = "v2", nur_json: bool = False, nachfrage: bool = True,
               gegenprobe: bool = True) -> str:
    """Name in Ergebnisdatei und Rangliste: <modell>+rechner (v2), <modell>+rechner-v3 (v3), Zusätze für
    abgeschaltete Teile und den Kontrolllauf ohne Schema."""
    name = (modell or ORAKEL) + SUFFIX
    if fassung != "v2":
        name += f"-{fassung}"
        if not nachfrage:
            name += "-ohne-nachfrage"
        if not gegenprobe:
            name += "-ohne-gegenprobe"
    return name + ("-json" if nur_json else "")


def _dauer_ns(*antworten, schluessel: str) -> int | None:
    werte = [r.get(schluessel) for r in antworten if r and r.get(schluessel)]
    return sum(werte) if werte else None


def schon_da(pfad: Path, aufgaben: list[dict], standard: bool = True) -> set[tuple[str, int]]:
    """Fertige (id, lauf) einer Ergebnisdatei zum Fortsetzen, nur wenn die Datei zu diesem Aufgabensatz gehört.

    Seed v1 und Holdout nutzen dieselben IDs (F001 …). Jede Zeile trägt deshalb die Kennung ihrer Aufgabe
    (bewerten.aufgabe_kennung). Trägt eine Zeile zu einer ID dieses Laufs eine andere Kennung, oder hat sie keine
    (ältere Läufe, nur Seed v1) und der Satz ist nicht aufgaben.jsonl, bricht der Lauf ab, statt fremde Zeilen als
    erledigt zu zählen."""
    kennung = {a["id"]: B.aufgabe_kennung(a) for a in aufgaben}
    fertig: set[tuple[str, int]] = set()
    if not pfad.exists():
        return fertig
    with open(pfad, encoding="utf-8") as fh:
        for z in fh:
            try:
                d = json.loads(z)
            except json.JSONDecodeError:
                continue
            k = d.get("aufgabe_kennung")
            if d.get("id") in kennung and (k != kennung[d["id"]] if k else not standard):
                raise SystemExit(f"{pfad} enthält Zeilen eines anderen Aufgabensatzes ({d['id']}, Lauf {d.get('lauf')}, "
                                 f"Kennung {k or 'fehlt'}). Anderes --ausgabe-dir oder --datum wählen.")
            if not d.get("fehler"):
                fertig.add((d["id"], d["lauf"]))
    return fertig


def laufe_kette(modell: str | None, aufgaben: list[dict], args, ausgabe_dir: Path, datum: str,
                chat_fn=None) -> dict:
    orakel = modell is None
    chat_fn = chat_fn or RO.chat
    fassung = PK.fassung(getattr(args, "prompt_version", None))
    v3 = fassung.name != "v2"
    nur_json = not orakel and getattr(args, "format", "schema") == "json"
    mit_gegenprobe = v3 and not getattr(args, "ohne_gegenprobe", False)
    # Auch das Orakel bekommt die Nachfrage (es antwortet mit dem wahren Wert, ohne Modellaufruf): so prüft der
    # Orakel-Lauf, dass Nachfrage und Regel N richtige Werte nicht verwerfen und fehlende nicht erfinden.
    mit_nachfrage = v3 and not getattr(args, "ohne_nachfrage", False)
    kname = kettenname(modell, fassung.name, nur_json, nachfrage=not getattr(args, "ohne_nachfrage", False),
                       gegenprobe=not getattr(args, "ohne_gegenprobe", False))
    pfad = ausgabe_dir / f"{datum}-{RO.dateiname(kname)}.jsonl"
    fertig = schon_da(pfad, aufgaben, getattr(args, "standard_satz", True))
    optionen = {"num_ctx": args.num_ctx}
    if args.temperatur is not None:
        optionen["temperature"] = args.temperatur
    if args.seed is not None:
        optionen["seed"] = args.seed
    if getattr(args, "num_predict", None):
        optionen["num_predict"] = args.num_predict  # Schutz gegen endlose Leerzeichen (Ollama-MLX, Issue #18567)
    if getattr(args, "num_gpu", None) is not None:
        optionen["num_gpu"] = args.num_gpu  # Schichten auf der Grafikkarte (Windows-Rechner: qwen3:8b am schnellsten mit 36)
    zaehler = {"ok": 0, "fehler": 0, "uebersprungen": 0, "unlesbar": 0, "ohne_antwort": 0, "nachfragen": 0}
    exakt: dict[str, list[bool]] = {}
    tps: list[float] = []
    zustand = {"format": "json" if nur_json else "schema"}
    verbindungsfehler_folge = 0
    pause = max(0.0, getattr(args, "pause", 0.0) or 0.0)
    with open(pfad, "a", encoding="utf-8") as out:
        for lauf in range(1, args.laeufe + 1):
            for a in aufgaben:
                if (a["id"], lauf) in fertig:
                    zaehler["uebersprungen"] += 1
                    continue
                zeile = {"modell": kname, "id": a["id"], "lauf": lauf, "split": a["split"], "typ": a["typ"],
                         "aufgabe_kennung": B.aufgabe_kennung(a), "zeit": datetime.now().isoformat(timespec="seconds"),
                         "quelle": "orakel" if orakel else "kette", "auslese_modell": None if orakel else modell,
                         "prompt_version": fassung.version, "prompt_hash": fassung.prompt_hash(),
                         "think": bool(args.think) and not orakel, "optionen": None if orakel else optionen}
                t0 = time.monotonic()
                try:
                    if orakel:
                        roh_text = json.dumps(als_modellausgabe(orakel_felder(a)[0]), ensure_ascii=False)
                        r, fmt = {}, None
                    else:
                        r, fmt = _auslese_chat(chat_fn, args.host, modell, fassung.nachrichten(a), args, optionen,
                                               zustand, schema=fassung.schema)
                        roh_text = (r.get("message") or {}).get("content", "")
                    msg = r.get("message") or {}
                    zeile.update(format=fmt, auslese=roh_text, denken=(msg.get("thinking") or "")[:4000] or None,
                                 aufrufe=0 if orakel else 1)
                    teil = verarbeite(a, roh_text, fassung.name, gegenprobe=mit_gegenprobe)
                    nachfrage = None
                    feld = nachfrage_feld(teil.get("rechnung")) if mit_nachfrage else None
                    if feld:
                        t1 = time.monotonic()
                        if orakel:
                            r2, fmt2 = {}, None
                            text2 = json.dumps(orakel_nachfrage(a, feld), ensure_ascii=False)
                        else:
                            r2, fmt2 = _auslese_chat(chat_fn, args.host, modell, PK.nachfrage_nachrichten(a, feld),
                                                     args, optionen, zustand, schema=PK.nachfrage_schema(feld))
                            text2 = (r2.get("message") or {}).get("content", "")
                        msg2 = r2.get("message") or {}
                        teil = verarbeite(a, roh_text, fassung.name, nachfrage=(feld, text2), gegenprobe=mit_gegenprobe)
                        nachfrage = {**teil["nachfrage_info"], "format": fmt2, "auslese": text2,
                                     "denken": (msg2.get("thinking") or "")[:2000] or None,
                                     "dauer_s": round(time.monotonic() - t1, 2), "eval_count": r2.get("eval_count"),
                                     "eval_duration": r2.get("eval_duration"),
                                     "total_duration": r2.get("total_duration")}
                        zeile["aufrufe"] = 0 if orakel else 2
                        zaehler["nachfragen"] += 1
                    teil.pop("nachfrage_info", None)
                    zeile.update(teil)
                    if v3:
                        zeile["nachfrage"] = nachfrage
                    zeile.update(eval_count=r.get("eval_count"), eval_duration=r.get("eval_duration"),
                                 load_duration=r.get("load_duration"), prompt_eval_count=r.get("prompt_eval_count"),
                                 prompt_eval_duration=r.get("prompt_eval_duration"),
                                 total_duration=r.get("total_duration"), tokens_pro_s=RO.token_pro_s(r), fehler=None)
                    if nachfrage:   # Summen über beide Aufrufe; tokens_pro_s bleibt die der ersten Auslese
                        zeile["total_duration_alle"] = _dauer_ns(r, r2, schluessel="total_duration")
                        zeile["eval_count_alle"] = _dauer_ns(r, r2, schluessel="eval_count")
                    verbindungsfehler_folge = 0
                    zaehler["ok"] += 1
                    if zeile["felder"] is None:
                        zaehler["unlesbar"] += 1
                    elif zeile["antwort_json"] is None:
                        zaehler["ohne_antwort"] += 1
                    if zeile["tokens_pro_s"]:
                        tps.append(zeile["tokens_pro_s"])
                except (socket.timeout, TimeoutError):
                    zeile.update(antwort=None, antwort_json=None, fehler=f"Zeitüberschreitung nach {args.timeout} s")
                    zaehler["fehler"] += 1
                except urllib.error.URLError as e:
                    zeile.update(antwort=None, antwort_json=None, fehler=f"Verbindung: {e.reason}")
                    zaehler["fehler"] += 1
                    verbindungsfehler_folge += 1
                except Exception as e:  # noqa: BLE001 - robust weiterlaufen
                    zeile.update(antwort=None, antwort_json=None, fehler=f"{type(e).__name__}: {e}"[:400])
                    zaehler["fehler"] += 1
                zeile["dauer_s"] = round(time.monotonic() - t0, 2)
                out.write(json.dumps(zeile, ensure_ascii=False) + "\n")
                out.flush()
                ok = ist_exakt(a, zeile.get("antwort_json"))
                exakt.setdefault(a["id"], []).append(ok)
                status = (zeile["fehler"] or (zeile.get("antwort_json") or {}).get("antwortart")
                          or ("unlesbar" if zeile.get("felder") is None else "keine Antwort"))
                extra = f", Nachfrage {zeile['nachfrage']['feld']}" if zeile.get("nachfrage") else ""
                print(f"  {kname} Lauf {lauf} {a['id']}: {status}{' exakt' if ok else ''} ({zeile['dauer_s']} s"
                      f"{extra})", flush=True)
                if verbindungsfehler_folge >= 5:
                    print("  Fünf Verbindungsfehler hintereinander: Abbruch dieses Modells.", flush=True)
                    return {"datei": str(pfad), **zaehler, "abbruch": True}
                if pause and not orakel:
                    time.sleep(pause)  # Schonmodus: Grafikkarte kühlt zwischen den Aufgaben nach
    bericht = {"datei": str(pfad), **zaehler, "format": None if orakel else zustand["format"],
               "tokens_pro_s_median": statistics.median(tps) if tps else None}
    if exakt and not zaehler["uebersprungen"] and args.laeufe:
        voll = sum(1 for v in exakt.values() if len(v) == args.laeufe and all(v))
        bericht["exakt_alle_laeufe_dieser_lauf"] = f"{voll}/{len(exakt)}"
    return bericht


def holdout_datei() -> Path:
    """Die eine Aufgabendatei in holdout/ (nur der Name wird hier angesehen, nicht der Inhalt)."""
    dateien = sorted(HOLDOUT_DIR.glob("*.jsonl"))
    if len(dateien) != 1:
        raise SystemExit(f"In {HOLDOUT_DIR} muss genau eine .jsonl-Datei liegen (gefunden: {len(dateien)}); "
                         "sonst --aufgaben PFAD angeben.")
    return dateien[0]


def standard_ausgabe(aufgaben_pfad: Path) -> Path:
    """ergebnisse/ für aufgaben.jsonl, ergebnisse/holdout/ für den Holdout-Satz, sonst ergebnisse/<Dateiname>/."""
    p = Path(aufgaben_pfad).resolve()
    if p == STANDARD_AUFGABEN.resolve():
        return ERGEBNISSE
    if HOLDOUT_DIR.resolve() in p.parents:
        return ERGEBNISSE / "holdout"
    return ERGEBNISSE / p.stem


def schreibe_rangliste(aufgaben_pfad: Path, ausgabe_dir: Path, laeufe: int) -> int:
    """Eigene Rangliste (rangliste.md/json) im Ausgabeverzeichnis, bewertet gegen diesen Aufgabensatz."""
    return B.main(["--aufgaben", str(aufgaben_pfad), "--ergebnisse", str(ausgabe_dir),
                          "--laeufe", str(laeufe), "--ausgabe-dir", str(ausgabe_dir)])


def main(argv=None, chat_fn=None) -> int:
    ap = argparse.ArgumentParser(description="Fristen-Benchmark: Kette „Modell liest, Code rechnet“")
    ap.add_argument("--modelle", nargs="+", default=RO.STANDARD_MODELLE)
    ap.add_argument("--orakel", action="store_true",
                    help="wahre Felder aus aufgaben.jsonl/parameter statt Modell (Obergrenze, muss 50/50 ergeben)")
    ap.add_argument("--prompt-version", choices=sorted(PK.FASSUNGEN), default=PK.STANDARD,
                    help="v3 (Standard): geschärfter Prompt, Gegenproben, Nachfrage; v2: alte Kette")
    ap.add_argument("--ohne-nachfrage", action="store_true", help="v3 ohne Nachfrage (Name …-v3-ohne-nachfrage)")
    ap.add_argument("--ohne-gegenprobe", action="store_true",
                    help="v3 ohne Gegenproben im Code (Name …-v3-ohne-gegenprobe)")
    ap.add_argument("--laeufe", type=int, default=3)
    ap.add_argument("--think", action="store_true", help="Denkmodus einschalten (z. B. qwen3)")
    ap.add_argument("--format", choices=["schema", "json"], default="schema",
                    help="schema: Auslese-Schema als Grammatik (Standard); json: nur format 'json' wie bei den "
                         "Einzelmodellen (Kontrolllauf, Name <modell>+rechner…-json)")
    ap.add_argument("--host", default=RO.HOST)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--temperatur", type=float, default=None, help="Standard: Voreinstellung des Modells")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-gpu", type=int, default=None,
                    help="Schichten auf der Grafikkarte erzwingen (Ollama num_gpu); Standard: Ollama entscheidet")
    ap.add_argument("--num-predict", type=int, default=None,
                    help="Höchstzahl Ausgabe-Token je Aufruf (z. B. 1024 für MLX-Modelle); Standard: ohne Grenze")
    ap.add_argument("--pause", type=float, default=0.0,
                    help="Schonmodus: Sekunden Pause nach jeder Aufgabe, damit ein heißer Rechner nachkühlt "
                         "(z. B. 3); Standard 0")
    ap.add_argument("--keep-alive", default="10m")
    ap.add_argument("--split", choices=["alle", "oeffentlich", "privat"], default="alle")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--aufgaben", type=Path, default=None,
                    help="Aufgabendatei (Standard aufgaben.jsonl, Seed v1). Andere Dateien schreiben nach "
                         "ergebnisse/<Dateiname>/ mit eigener Rangliste.")
    ap.add_argument("--holdout", action="store_true",
                    help="Holdout-Satz (die eine .jsonl in holdout/; gleiche Vorlagen wie Seed v1, neue Daten); "
                         "Ausgabe ergebnisse/holdout/ mit eigener Rangliste")
    ap.add_argument("--ausgabe-dir", type=Path, default=None,
                    help="Standard: ergebnisse/, ergebnisse/holdout/ bzw. ergebnisse/<Dateiname>/")
    ap.add_argument("--rangliste", action=argparse.BooleanOptionalAction, default=None,
                    help="danach rangliste.md/json ins Ausgabeverzeichnis schreiben (Standard: ja, außer bei "
                         "aufgaben.jsonl; dort wie bisher bewerten.py)")
    ap.add_argument("--datum", default=date.today().isoformat())
    args = ap.parse_args(argv)

    if args.holdout:
        if args.aufgaben:
            ap.error("--holdout und --aufgaben schließen sich aus")
        args.aufgaben = holdout_datei()
    aufgaben_pfad = args.aufgaben or STANDARD_AUFGABEN
    args.standard_satz = Path(aufgaben_pfad).resolve() == STANDARD_AUFGABEN.resolve()
    args.ausgabe_dir = args.ausgabe_dir or standard_ausgabe(aufgaben_pfad)
    rangliste = args.rangliste if args.rangliste is not None else (
        Path(aufgaben_pfad).resolve() != STANDARD_AUFGABEN.resolve())
    aufgaben = RO.lade_aufgaben(aufgaben_pfad, args.split, args.ids, args.limit)
    args.ausgabe_dir.mkdir(parents=True, exist_ok=True)
    fassung = PK.fassung(args.prompt_version)
    teile = "" if fassung.name == "v2" else (
        (", ohne Nachfrage" if args.ohne_nachfrage else ", mit Nachfrage")
        + (", ohne Gegenproben" if args.ohne_gegenprobe else ", mit Gegenproben"))
    if args.orakel:
        print(f"{len(aufgaben)} Aufgaben, {args.laeufe} Läufe, Orakel (wahre Felder) + Rechner "
              f"({fassung.name}{teile})")
        name = kettenname(None, fassung.name, nachfrage=not args.ohne_nachfrage, gegenprobe=not args.ohne_gegenprobe)
        bericht = {name: laufe_kette(None, aufgaben, args, args.ausgabe_dir, args.datum)}
        print(json.dumps(bericht, ensure_ascii=False, indent=1))
        if rangliste:
            schreibe_rangliste(aufgaben_pfad, args.ausgabe_dir, args.laeufe)
        return 0
    vorhanden = None
    if chat_fn is None:
        vorhanden = RO.verfuegbare_modelle(args.host)
        if vorhanden is None:
            print(f"Ollama unter {args.host} nicht erreichbar. Läuft 'ollama serve'?", file=sys.stderr)
            return 2
    print(f"{len(aufgaben)} Aufgaben aus {aufgaben_pfad.name}, {args.laeufe} Läufe, Kette mit: "
          f"{', '.join(args.modelle)} (Prompt {fassung.version}, {fassung.prompt_hash()}{teile}); "
          f"Ausgabe {args.ausgabe_dir}")
    bericht = {}
    for m in args.modelle:
        name = kettenname(m, fassung.name, args.format == "json", nachfrage=not args.ohne_nachfrage,
                          gegenprobe=not args.ohne_gegenprobe)
        if vorhanden is not None and m not in vorhanden:
            print(f"- {m}: nicht installiert (ollama pull {m}), übersprungen", file=sys.stderr)
            bericht[name] = {"fehlt": True}
            continue
        print(f"- {name}")
        bericht[name] = laufe_kette(m, aufgaben, args, args.ausgabe_dir, args.datum, chat_fn=chat_fn)
    print(json.dumps(bericht, ensure_ascii=False, indent=1))
    if rangliste:
        schreibe_rangliste(aufgaben_pfad, args.ausgabe_dir, args.laeufe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
