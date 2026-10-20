"""Normen erkennen und vergleichen.

``schluessel("§ 84 Abs. 1 SGG")`` == ``schluessel("§84 SGG")`` == {("84", "SGG")}.
Absatz, Satz und Nummer fallen weg; verglichen werden Paragraph und Gesetz.

Die Positivliste (gegen erfundene Normen) besteht aus allen Normen in
recht/belege.json plus einer Liste gängiger Fristnormen (GAENGIGE_NORMEN).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
BELEGE = WURZEL / "recht" / "belege.json"

_ROEMISCH = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI", "7": "VII", "8": "VIII",
             "9": "IX", "10": "X", "11": "XI", "12": "XII", "14": "XIV"}

_GESETZE = (r"SGB\s*(?:XIV|XII|XI|IX|X|VIII|VII|VI|V|IV|III|II|I|\d{1,2})(?![A-Za-z])", "BayVwVfG", "VwVfG",
            "VwGO", "VwZG", "KSchG", "ArbGG", "BUrlG", "EGAO", "EGBGB", "TzBfG", "MuSchG", "BetrVG", "BGB",
            "ZPO", "SGG", "FGO", "AO", "HGB", "GG", "EStG", "BEEG", "WoGG", "BAföG", "BAfoeG", "StPO", "StGB",
            "PostModG", "GVG", "RVG", "GKG")
_GESETZ_RE = "(?:" + "|".join(_GESETZE) + ")"
_TOKEN = re.compile(
    r"(?P<pp>§§)|(?P<p>§)|(?P<art>\bArt(?:ikel|\.)?)\s*|(?P<sub>\bAbs(?:atz|\.)?|\bSatz\b|\bS\.|\bNr\.|\bNummer\b"
    r"|\bBuchst(?:abe|\.)?|\blit\.|\bHs\.|\bHalbsatz\b)|(?P<gesetz>\b" + _GESETZ_RE + r"\b)"
    r"|(?P<num>\d+[a-z]?)(?![\d])|(?P<bis>\bbis\b|[-–])|(?P<sep>,|\bund\b|\boder\b|;|\bi\.\s*V\.\s*m\.)"
    r"|(?P<kuerzel>\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]{1,14}\b)",
    re.IGNORECASE,
)
# Unbekannte Kürzel (nicht in _GESETZE) zählen, damit erfundene Gesetze wie „§ 241 ZGB“ nicht durchrutschen.
# Ausgenommen, weil echt, aber nicht im Bundesrecht prüfbar: EU-Recht und Landesverfahrensgesetze. Bloßes „SGB“
# ohne Buch bleibt unerkannt (unvollständig, nicht erfunden).
_NICHT_PRUEFBAR = re.compile(r"(?:DSGVO|AEUV|EUV|EMRK|GRCH|SGB|.*VWVFG|.*VWZG|.*VWVG)")


def _ist_kuerzel(v: str) -> bool:
    """Abkürzungsform mit mindestens zwei Großbuchstaben (BDSG, StVG, EntgFG), kein Wort wie „des“ oder „Satz“."""
    return sum(c.isupper() for c in v) >= 2 and not _NICHT_PRUEFBAR.fullmatch(gesetz_normal(v))


def gesetz_normal(g: str) -> str:
    g = re.sub(r"[\s.]", "", g).upper()
    m = re.fullmatch(r"SGB(\d{1,2})", g)
    if m:
        g = "SGB" + _ROEMISCH.get(m.group(1), m.group(1))
    return {"BAFÖG": "BAFOEG"}.get(g, g)


def schluessel(text: str) -> set[tuple[str, str]]:
    """Alle (Paragraph, Gesetz)-Paare in einem Normtext."""
    out: set[tuple[str, str]] = set()
    if not text:
        return out
    pending: list[str] = []
    modus = None          # 'p', 'pp', 'art', 'sub'
    mehrfach = False      # nach '§§'
    bis = False
    art_nr = None
    for m in _TOKEN.finditer(text):
        k = m.lastgroup
        v = m.group(k)
        if k == "pp":
            modus, mehrfach, bis = "p", True, False
        elif k == "p":
            modus, mehrfach, bis = "p", False, False
            art_nr = None
        elif k == "art":
            modus, bis = "art", False
        elif k == "sub":
            modus = "sub"
        elif k == "sep":
            if mehrfach and modus == "sub":
                modus = "p"
        elif k == "bis":
            bis = modus == "p"
        elif k == "num":
            if modus == "p":
                if bis and pending and pending[-1].isdigit() and v.isdigit():
                    pending += [str(i) for i in range(int(pending[-1]) + 1, int(v) + 1)]
                else:
                    pending.append(v.lower())
                bis = False
                if not mehrfach:
                    modus = "sub"
            elif modus == "art":
                art_nr = "art" + v.lower()
                modus = None
            # Zahlen nach Abs./Satz/Nr. werden übersprungen
        elif k == "kuerzel":
            if (pending or art_nr) and _ist_kuerzel(v):
                g = gesetz_normal(v)
                if pending:
                    out.update((p, g) for p in pending)
                else:
                    out.add((art_nr, g))
                pending, modus, mehrfach, bis, art_nr = [], None, False, False, None
        elif k == "gesetz":
            g = gesetz_normal(v)
            if pending:
                out.update((p, g) for p in pending)
            elif art_nr:
                out.add((art_nr, g))
            pending, modus, mehrfach, bis, art_nr = [], None, False, False, None
    return out


def _bereich(spec: str) -> set[str]:
    out = set()
    for teil in spec.split():
        if "-" in teil:
            a, b = teil.split("-")
            out.update(str(i) for i in range(int(a), int(b) + 1))
        else:
            out.add(teil)
    return out


# Gängige Normen rund um Fristen, Bescheide und Kündigungen (Paragraphen je Gesetz)
GAENGIGE_NORMEN = {
    "BGB": "1 2 126 126a 126b 130 132 133 157 186-193 194 195 199 242 286 314 355 356 543 549 556b 568 569 "
           "573 573a 573b 573c 573d 574 574a 575 576 577a 580a 612a 613a 620 621 622 623 624 625 626 627",
    "ZPO": "166-195 214 216 217 221-227 233-236 253 270 357 418",
    "VWGO": "40 42 55a 56 57 58 60 67 68 69 70 72 73 74 75 80 81 82 113 152a",
    "VWVFG": "9 15 28 31 32 35 37 41 43 44 45 48 49 79 80",
    "SGBX": "14 24 26 27 31 33 35 36 37 39 40 41 44 45 48 50 62 63 65",
    "SGBI": "16 36 37",
    "SGBII": "7 9 11 19 20 22 31 32 33 37 39 40 41 44 60",
    "SGBXII": "18 19 27",
    "SGG": "51 54 57 62 63 64 65 65a 65d 66 67 77 78 83 84 85 86 86a 86b 87 90 91 92 178a",
    "AO": "87a 108 109 110 118 119 121 122 122a 123 124 155 172 173 347 348 350 351 352 353 354 355 356 357 "
          "358 361 365 366 367",
    "FGO": "40 44 45 47 52a 54 55 56 64 65 133a",
    "KSCHG": "1-26",
    "ARBGG": "9 46 46c 61a",
    "VWZG": "1-10 5a",
    "EGAO": "1 art97",
    "BURLG": "3",
    "GG": "19 20 103",
    "MUSCHG": "17",
    "TZBFG": "14 15",
    "BAYVWVFG": "art31 art41",
    "BETRVG": "102",
}


@lru_cache(maxsize=1)
def positivliste() -> frozenset[tuple[str, str]]:
    pos: set[tuple[str, str]] = set()
    for gesetz, spec in GAENGIGE_NORMEN.items():
        pos.update((p, gesetz) for p in _bereich(spec))
    try:
        daten = json.loads(BELEGE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        daten = []
    for gruppe in daten:
        for regel in gruppe.get("regeln", []):
            for n in regel.get("normen", []):
                pos.update(schluessel(n))
    return frozenset(pos)


def ist_belegt(text: str) -> bool:
    """True, wenn alle in ``text`` erkannten Normen auf der Positivliste stehen (und mindestens eine erkannt wurde)."""
    k = schluessel(text)
    return bool(k) and k <= positivliste()


def treffer(pflicht, genannt: set[tuple[str, str]]) -> bool:
    """pflicht: Normtext oder Liste von Alternativen; genannt: Menge von Schlüsseln."""
    if isinstance(pflicht, (list, tuple)):
        return any(treffer(p, genannt) for p in pflicht)
    k = schluessel(pflicht)
    return bool(k) and k <= genannt
