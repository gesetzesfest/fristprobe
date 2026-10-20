"""Abruf aus der Wissensbasis: exakter Normtext, Volltextsuche, Prüfung auf erfundene Normen.

  from pruefki.wissen.abruf import norm, suche, existiert
  norm("§ 41 Abs. 2 VwVfG")          # Treffer mit Text, Absatz 2, Quelle und Stand
  norm("BGB", "§ 187")               # dasselbe mit getrenntem Gesetz
  suche("Bekanntgabe vierter Tag")   # BM25-Treffer mit Ausschnitt
  existiert("§ 999 BGB-erfunden")    # False

  python3.12 -m pruefki.wissen.abruf "§ 41 VwVfG"
  python3.12 -m pruefki.wissen.abruf --suche "Bekanntgabe vierter Tag" [--limit 5] [--gesetz AO]
  python3.12 -m pruefki.wissen.abruf --existiert "§ 999 SGG"

Die Datenbank wird nur lesend geöffnet; eine leere, beschädigte oder veraltete Datei meldet WissensbasisFehler.
Gesetzesnamen werden über die Alias-Tabelle aufgelöst ('SGB X' = 'SGB 10', 'AO' = 'AO 1977', 'EGBGB' = 'BGBEG'),
auch gebeugt ('des Bürgerlichen Gesetzbuchs', 'Zehnten Buches Sozialgesetzbuch') und mit Bindestrich ('SGB-II').
Ein unbekannter Gesetzesname gilt als nicht vorhanden; ein Name wird nie auf einen ähnlichen Namen umgebogen
('BGB-erfunden' ist nicht 'BGB'). Folgt einem Bundesgesetz ein Land ('VwVfG NRW'), gilt es als Landesrecht und damit
als unbekannt. Nach dem Gesetzesnamen folgender Fließtext ('§ 41 VwVfG beträgt ...') wird übergangen.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pruefki.wissen.index import DB_STANDARD, SCHEMA_VERSION, alias_schluessel, kompakt, nur_lesen_uri

# ---------------------------------------------------------------------------------------------------------------
# Zitate zerlegen (ohne Datenbank)
# ---------------------------------------------------------------------------------------------------------------


@dataclass
class Verweis:
    typ: str                       # '§', 'art', 'anlage', 'anhang', 'muster', 'regel', 'formblatt'
    nummer: str                    # '187', '41a', '1.01', 'iv'; leer bei 'Anlage BKatV'
    schluessel: str                # Suchschlüssel wie normen.enbez_norm: '§187', 'art1', 'art97§1'
    gesetz: list[str] = field(default_factory=list)   # Namenskandidaten, längster zuerst
    absatz: str | None = None
    satz: str | None = None
    nr: str | None = None
    hinweis: str = ""
    vorlaeufig: bool = False       # Zahl nach einem schon genannten Gesetz ('§§ 41 VwVfG, 37 SGB X')

    @property
    def text(self) -> str:
        teile = []
        m = re.match(r"^art([0-9a-z]+)§", self.schluessel)
        if m:
            teile.append(f"Art. {m.group(1)}")
        teile.append({"§": "§", "art": "Art."}.get(self.typ, self.typ.capitalize())
                     + (f" {self.nummer}" if self.nummer else ""))
        if self.absatz:
            teile.append(f"Abs. {self.absatz}")
        if self.satz:
            teile.append(f"Satz {self.satz}")
        if self.nr:
            teile.append(f"Nr. {self.nr}")
        if self.gesetz:
            teile.append(self.gesetz[0])
        return " ".join(teile)


# Strukturwörter auch klein oder ganz groß ('abs.', 'ART.'); 'S.' nur groß ('s.' heißt 'siehe').
_TOKEN = re.compile(r"""
    (?P<pp>§§|(?i:\bParagra(?:ph|f)en\b))
  | (?P<p>§|(?i:\bParagra(?:ph|f)\b))
  | (?P<art>(?i:\b(?:Artikel|Art)\b)\.?)
  | (?P<anl>(?i:\b(?:Anlagen?|Anhang)\b)|\b(?:Muster|Formblatt|Regel)\b)
  | (?P<abs>(?i:\b(?:Absatz\b|Abs\.|Abs\b)))
  | (?P<satz>(?i:\bSatz\b)|\bS\.)
  | (?P<nr>(?i:\b(?:Nummer\b|Nr\.|Nr\b|Ziffer\b|Ziff\.)))
  | (?P<sub>(?i:\b(?:Unterabsatz\b|UAbs\.|Buchstabe\b|Buchst\.|lit\.|Halbsatz\b|Hs\.|Alternative\b|Alt\.
             |Variante\b|Var\.)))
  | (?P<wortzahl>\d+-(?=[^\W\d_])[^\s,;()\[\]§]+)
  | (?P<ord>\d+\.(?=\s*[A-ZÄÖÜ][a-zäöüß]*[A-ZÄÖÜ]))
  | (?P<num>\d+(?:\.\d+)*[a-z]?(?![a-zäöüß\d_]))
  | (?P<bis>\bbis\b|–|-(?=\s*\d))
  | (?P<ff>\bff?\.)
  | (?P<sep>[,;]|\bund\b|\boder\b|\bsowie\b|\bu\.(?=\s)|\bi\.\s?V\.\s?m\.|\biVm\b|\bvgl\.|\bzu\b|\bnach\b
            |\bgemäß\b|\bgem\.)
  | (?P<wort>[^\s,;()\[\]§]+)
""", re.VERBOSE)
_FUELL = {"des", "der", "dem", "die", "das", "den", "im", "in", "zum", "zur", "vom", "von", "a.", "f.", "ff."}
_ROEMISCH = re.compile(r"[IVXLC]+")
_ROEMISCH_ABSATZ = re.compile(r"X{0,2}(?:IX|IV|V?I{0,3})")      # I bis XXIX, Klausurschreibweise '§ 41 II VwVfG'
_ROEMISCH_WERT = {"I": 1, "V": 5, "X": 10}
_PUBLIKATION = re.compile(r"(?:BGBl|ABl|BAnz|GVBl|RGBl)\.?", re.IGNORECASE)
_MAX_BEREICH = 200


def _roemisch(s: str) -> int:
    werte = [_ROEMISCH_WERT[c] for c in s]
    return sum(-w if i + 1 < len(werte) and w < werte[i + 1] else w for i, w in enumerate(werte))


def _gesetzartig(worte: list[str]) -> bool:
    """Sieht der Anfang wie ein Gesetzesname aus? Abkürzung mit zwei Großbuchstaben ('BGB', 'SGB X', 'VwVfG',
    'erfundenG') oder ein Wort wie '-gesetz', '-buch', '-ordnung'. 'Wochen', 'Tage' oder 'BGBl.' sind es nicht."""
    for w in worte[:4]:
        if _PUBLIKATION.fullmatch(w):
            return False
        if (sum(c.isupper() for c in w) >= 2 or w[-1:].isupper()
                or re.search(r"gesetz|buch|ordnung|vertrag|abkommen|kodex", w, re.IGNORECASE)):
            return True
    return False


def zerlege(zitat: str) -> list[Verweis]:
    """'§ 37 Abs. 2 SGB X' -> [Verweis('§', '37', '§37', ['SGB X', 'SGB'], absatz='2')].
    Versteht §, §§ (Listen, 'bis'), Art./Artikel, Art. 97 § 1, Anlage, Abs./Satz/Nr./Buchst., i. V. m., römische
    Absätze ('§ 41 II 1 VwVfG' = Abs. 2 Satz 1), Parallelzitate ('§§ 41 VwVfG, 37 SGB X') und Kleinschreibung."""
    fertig: list[Verweis] = []
    offen: list[Verweis] = []          # Bezeichnungen, deren Gesetz noch fehlt
    gesetz: list[str] = []
    modus: str | None = None           # nummer, mehrfach, nach_nummer, nach_roemisch, sub, nach_sub, gesetz
    typ = "§"
    mehrfach = bis = False
    fortsetzung = False                # nach 'VwVfG,': eine nackte Zahl gehört zu einem weiteren Gesetz
    rahmen = ""                        # 'art97' bei 'Art. 97 § 1'
    sub_art = ""
    vorher = ""                        # Art des vorigen Tokens

    def schliesse() -> None:
        nonlocal offen, gesetz
        if offen:
            kandidaten = [" ".join(gesetz[:n]) for n in range(len(gesetz), 0, -1)] if gesetz else []
            for v in offen:
                v.gesetz = kandidaten
            # Fortsetzungen zählen nur, wenn ein Gesetzesname folgt ('§ 41 VwVfG, 3 Wochen' ist kein § 3)
            fertig.extend(v for v in offen if not v.vorlaeufig or _gesetzartig(gesetz))
            offen = []
        gesetz = []

    def neu(nummer: str) -> Verweis:
        v = Verweis(typ, nummer, f"{rahmen}{typ}{nummer}", vorlaeufig=fortsetzung)
        offen.append(v)
        return v

    for m in _TOKEN.finditer(zitat or ""):
        k = m.lastgroup
        v = m.group(k)
        if k == "wortzahl":                # '1-DM-GoldmünzG'
            k = "wort"
        elif k == "ord":                   # '5. VermBG', '20. BImSchV' (Ordnungszahl vor dem Gesetzesnamen)
            if modus in ("sub", "nummer", "mehrfach"):
                k, v = "num", v.rstrip(".")
            elif offen and modus != "gesetz":
                gesetz, modus, vorher = [v], "gesetz", k
                continue
        if k in ("p", "pp", "art", "anl"):
            if modus == "gesetz":
                schliesse()
            offen = [x for x in offen if not x.vorlaeufig]
            fortsetzung = False
            rahmen = ""
            if k in ("p", "pp") and vorher == "artnum" and offen and offen[-1].typ == "art":
                rahmen = offen.pop().schluessel
            typ = {"p": "§", "pp": "§", "art": "art"}.get(k) or re.sub(r"n$", "", v.lower())
            mehrfach, bis, modus = k == "pp", False, "nummer"
        elif k == "num" and modus is None and fortsetzung and vorher == "sep":
            neu(v.lower())                 # '§§ 41 VwVfG, 37 SGB X': 37 ist ein § des nächsten Gesetzes
            modus, vorher = "nach_nummer", "num"
            continue
        elif k == "num" and modus == "nach_roemisch" and offen and offen[-1].satz is None:
            offen[-1].satz = v.lower()     # '§ 41 II 1 VwVfG': Abs. 2 Satz 1
            modus = "nach_sub"
        elif k == "num" or (k == "wort" and modus == "nummer"
                            and (_ROEMISCH.fullmatch(v) or (typ != "§" and re.fullmatch(r"[A-Z]\d*[a-z]?", v)))):
            if modus in ("nummer", "mehrfach"):
                nummer = v.lower()
                if bis and offen and offen[-1].typ == typ and offen[-1].nummer.isdigit() and nummer.isdigit():
                    von, zu = int(offen[-1].nummer) + 1, int(nummer)
                    ende = min(zu, von + _MAX_BEREICH - 1)
                    for i in range(von, ende + 1):
                        neu(str(i))
                    if ende < zu:              # sehr lange Bereiche: Anfang und Ende prüfen, mit Hinweis
                        neu(nummer).hinweis = (f"Bereich bis {zu} gekürzt: geprüft {von - 1} bis {ende} und {zu}")
                else:
                    neu(nummer)
                bis = False
                modus = "mehrfach" if mehrfach else "nach_nummer"
                vorher = "artnum" if typ == "art" else "num"
                continue
            if modus == "sub" and offen:
                ziel = offen[-1]
                if sub_art == "abs" and ziel.absatz is None:
                    ziel.absatz = v.lower()
                elif sub_art == "satz" and ziel.satz is None:
                    ziel.satz = v.lower()
                elif sub_art == "nr" and ziel.nr is None:
                    ziel.nr = v.lower()
                modus = "nach_sub"
            elif modus == "gesetz":
                gesetz.append(v)
        elif k in ("abs", "satz", "nr", "sub"):
            if modus == "gesetz":
                schliesse()
            if offen:
                modus, sub_art = "sub", k
        elif k == "bis":
            if modus in ("nach_nummer", "mehrfach"):
                bis, modus = True, "nummer"
        elif k == "ff":
            pass
        elif k == "sep":
            if modus == "gesetz":
                schliesse()
                modus, fortsetzung = None, True
            elif modus == "nach_nummer" and v == ",":
                modus = "mehrfach"
            elif modus == "nach_sub":
                modus = "mehrfach" if mehrfach else "sub"
            elif modus not in ("mehrfach", "sub"):
                modus = None
        elif k == "wort":
            w = v.strip(".:!?\"'„“”")
            if not w:
                pass
            elif (modus == "nach_nummer" and vorher in ("num", "artnum") and offen and _ROEMISCH_ABSATZ.fullmatch(v)
                  and offen[-1].absatz is None):
                offen[-1].absatz = str(_roemisch(v))       # '§ 41 II VwVfG', 'Art. 19 IV GG' ('II.' ist ein Name)
                modus = "nach_roemisch"
            elif (modus in ("nach_nummer", "mehrfach") and vorher == "num" and offen and re.fullmatch(r"[a-z]", v)
                  and offen[-1].nummer.isdigit()):
                offen[-1].nummer += v                       # '§ 41 a VwVfG' = § 41a
                offen[-1].schluessel += v
            elif modus == "sub" and re.fullmatch(r"[a-z]{1,2}\)?|[ivx]+", w):
                modus = "nach_sub"
            elif modus != "gesetz" and w.lower() in _FUELL:
                pass
            elif modus == "nummer" and typ in ("anlage", "anhang") and _gesetzartig([w]):
                neu("")                                     # 'Anlage BKatV' (Anlage ohne Nummer)
                gesetz, modus = [w], "gesetz"
            elif offen:
                if modus != "gesetz":
                    gesetz, modus = [], "gesetz"
                if len(gesetz) < 8:
                    gesetz.append(w)
        vorher = k
    schliesse()
    return fertig


# ---------------------------------------------------------------------------------------------------------------
# Treffer
# ---------------------------------------------------------------------------------------------------------------


@dataclass
class Treffer:
    zitat: str
    gesetz: str                    # Kürzel des Gesetzes (Ordner auf gesetze-im-internet.de)
    abk: str
    gesetz_titel: str
    enbez: str
    enbez_norm: str
    titel: str
    text: str
    gliederung: str
    fussnoten: str
    art: str
    status: str
    quelle_url: str
    stand: str
    builddate: str
    absatz: str | None = None
    absatz_text: str | None = None
    hinweis: str = ""
    score: float | None = None
    ausschnitt: str = ""
    unter_artikel: bool = False    # '§ 30 EGAO' nur als 'Art 97 § 30 EGAO' gefunden
    alle_worte: bool | None = None  # Suche: Norm enthält alle Suchwörter (oder ihre Synonyme)

    @property
    def ansicht_url(self) -> str:
        """Lesefassung auf gesetze-im-internet.de (für § N und Art N), sonst die Übersicht des Gesetzes."""
        m = re.fullmatch(r"(§|art)(\d+[a-z]?)", self.enbez_norm)
        basis = f"https://www.gesetze-im-internet.de/{self.gesetz}/"
        if m:
            return basis + (f"__{m.group(2)}.html" if m.group(1) == "§" else f"art_{m.group(2)}.html")
        return basis + "index.html"

    def als_text(self, voll: bool = True) -> str:
        kopf = f"{self.zitat}" + (f" – {self.titel}" if self.titel else "")
        zeilen = [kopf, f"{self.gesetz_titel}" + (f" | {self.gliederung}" if self.gliederung else "")]
        if self.status != "geltend":
            zeilen.append(f"Status: {self.status}")
        if self.hinweis:
            zeilen.append(f"Hinweis: {self.hinweis}")
        zeilen.append("")
        if self.absatz and self.absatz_text and not voll:
            zeilen.append(self.absatz_text)
        else:
            zeilen.append(self.text or "(ohne Text)")
        if self.fussnoten and voll:
            zeilen += ["", "Fußnoten:", self.fussnoten]
        zeilen += ["", f"Quelle: {self.quelle_url} | Stand: {self.stand}", f"Ansicht: {self.ansicht_url}"]
        return "\n".join(zeilen)


def absaetze(text: str) -> list[str]:
    """Nummern der Absätze, z. B. ['1', '2', '2a', '3']."""
    return re.findall(r"^\((\d+[a-z]?)\)(?=\s|$)", text or "", re.MULTILINE)


def absatz_text(text: str, absatz: str) -> str | None:
    out: list[str] = []
    drin = False
    for z in (text or "").split("\n"):
        m = re.match(r"^\((\d+[a-z]?)\)(?:\s|$)", z)
        if m:
            drin = m.group(1) == absatz
        if drin:
            out.append(z)
    return "\n".join(out) or None


def _nr(s: str) -> tuple[int, str] | None:
    m = re.fullmatch(r"(\d+)([a-z]*)", s)
    return (int(m.group(1)), m.group(2)) if m else None


_TEILE = re.compile(r"(art[0-9a-z]+(?=§))?(§|art|anlage|anhang|muster|regel|nr|formblatt|tabelle)(.*)")


def im_bereich(schluessel: str, bereich: str) -> bool:
    """Liegt '§4' im Platzhalter '§3-6' (bzw. '§26,27', 'artviii§1-8')?"""
    a, b = _TEILE.fullmatch(schluessel), _TEILE.fullmatch(bereich)
    if not a or not b or a.group(1) != b.group(1) or a.group(2) != b.group(2):
        return False
    x = _nr(a.group(3))
    for teil in b.group(3).split(","):
        if "-" in teil:
            von, bis = (_nr(t) for t in teil.split("-", 1))
            if x and von and bis and von <= x <= bis and (not x[1] or von[1] or bis[1]):
                return True
        elif teil == a.group(3):
            return True
    return False


# ---------------------------------------------------------------------------------------------------------------
# Satz und Nummer prüfen
# ---------------------------------------------------------------------------------------------------------------


def saetze_hoechstens(text: str) -> int:
    """Obergrenze für die Zahl der Sätze: Jeder Punkt vor Leerraum oder Textende kann einen Satz beenden.
    Abkürzungen ('Abs.', 'z. B.') und Listenmarken ('1.') zählen mit; die Grenze ist also großzügig."""
    t = re.sub(r"^\(\d+[a-z]?\)\s*", "", (text or "").strip())
    if not t:
        return 0
    n = len(re.findall(r"[.!?](?=\s|$)", t))
    return n + (0 if re.search(r"[.!?]\s*$", t) else 1)


def nummern(text: str) -> list[str]:
    """Listenmarken '1.', '2a.' am Zeilenanfang (auch eingerückt)."""
    return re.findall(r"^\s*(\d+[a-z]?)\.(?=\s)", text or "", re.MULTILINE)


def _unklar_gegliedert(text: str) -> bool:
    """Tabellen oder Bilder: Nummern lassen sich dort nicht sicher erkennen."""
    return " | " in text or "[Bild" in text


# ---------------------------------------------------------------------------------------------------------------
# Wissensbasis
# ---------------------------------------------------------------------------------------------------------------

_STOPP = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen", "und", "oder",
          "im", "in", "am", "an", "auf", "aus", "bei", "mit", "nach", "von", "vom", "zu", "zum", "zur", "für", "ist",
          "sind", "wird", "werden", "nicht", "als", "auch", "es", "sich", "wie", "wenn", "dass", "daß",
          # Fragewörter, Fürwörter, Hilfsverben und Verhältniswörter aus Anfragen in Bürgersprache
          "gegen", "über", "unter", "durch", "ohne", "bis", "vor", "seit", "um", "wegen", "was", "wer", "wann", "wo",
          "warum", "wieso", "weshalb", "welche", "welcher", "welches", "ich", "mein", "meine", "meinen", "meinem",
          "meiner", "mir", "mich", "du", "dein", "deine", "wir", "uns", "unser", "kann", "können", "muss", "müssen",
          "darf", "dürfen", "soll", "sollen", "habe", "hat", "haben", "hatte", "bin", "war", "wurde", "noch", "schon",
          "nur", "man", "bitte", "lange", "viel", "viele", "mehr", "gibt", "denn", "aber", "so", "da", "dann", "jetzt",
          "hier", "kein", "keine"}
_ENDUNGEN = ("en", "er", "es", "em", "e", "n", "s")

# Suche: Gewichte und Schutzgrenzen (erklärt in pruefki/wissen/synonyme.json und im README)
BM25_GEWICHTE = (3.0, 3.0, 4.0, 1.0, 1.0)     # jurabk, enbez, titel, text, wortteile
KERN_FAKTOR = 1.5                              # Normen der Kerngesetze
HINWEIS_FAKTOR = 2.0                           # Normen der Gesetze, auf die ein Suchwort hinweist ('Jobcenter' -> SGG)
ANLAGE_FAKTOR = 0.5                            # Anlagen (große Tabellen passen auf fast jedes Wort)
BONUS_ALLE = 2.0                               # Norm enthält alle Suchwörter
BONUS_FAST_ALLE = 1.5                          # alle bis auf eines (ab 4 Suchwörtern)
KANDIDATEN = 500                               # so viele ODER-Treffer werden neu gereiht
MAX_WORTE = 8                                  # längere Anfragen: die 8 längsten Wörter
MAX_ZEICHEN = 2000                             # mehr Text wird nicht gelesen
SYNONYME_DATEI = Path(__file__).with_name("synonyme.json")

# Landesnamen hinter einem Bundesgesetz machen daraus Landesrecht ('VwVfG NRW'); Abkürzungen nur in dieser Schreibung
_LAENDER_ABK = {"BW", "BaWü", "BY", "Bay", "BE", "Bln", "BB", "Bbg", "HB", "Brem", "HH", "Hmb", "HE", "Hess", "MV",
                "M-V", "NI", "Nds", "NW", "NRW", "RP", "RLP", "SL", "Saarl", "SN", "Sachs", "ST", "LSA", "SH", "TH", "Thür"}
_LAENDER_NAMEN = {"baden-württemberg", "bayern", "berlin", "brandenburg", "bremen", "hamburg", "hessen",
                  "mecklenburg-vorpommern", "niedersachsen", "nordrhein-westfalen", "rheinland-pfalz", "saarland",
                  "sachsen", "sachsen-anhalt", "schleswig-holstein", "thüringen"}


def _stamm(w: str) -> str:
    if len(w) >= 6:
        for e in _ENDUNGEN:
            if w.endswith(e) and len(w) - len(e) >= 4:
                return w[: -len(e)]
    return w


def lade_suchwortschatz(pfad: Path = SYNONYME_DATEI) -> dict:
    """synonyme.json: {'synonyme': {wort: [...]}, 'gesetze': {wort: [...]}, 'kerngesetze': [...]}."""
    try:
        daten = json.loads(Path(pfad).read_text("utf-8"))
    except FileNotFoundError:
        daten = {}
    return {"synonyme": {k.lower(): [s.lower() for s in v] for k, v in (daten.get("synonyme") or {}).items()},
            "gesetze": {k.lower(): list(v) for k, v in (daten.get("gesetze") or {}).items()},
            "kerngesetze": list(daten.get("kerngesetze") or [])}


def suchworte(text: str) -> list[str]:
    """Freitext -> Suchwörter: klein, ohne Füllwörter und Einzelzeichen, ohne Doppelte; höchstens MAX_WORTE
    (bei langen Texten die längsten, in ursprünglicher Reihenfolge)."""
    worte = list(dict.fromkeys(w for w in re.findall(r"\w+", (text or "")[:MAX_ZEICHEN].lower())
                               if w not in _STOPP and len(w) >= 2 and "_" not in w))
    if len(worte) > MAX_WORTE:
        behalten = set(sorted(worte, key=len, reverse=True)[:MAX_WORTE])
        worte = [w for w in worte if w in behalten]
    return worte


def _gruppe(w: str, synonyme: dict[str, list[str]]) -> str:
    """Ein Suchwort als FTS5-Ausdruck: Wortstamm als Präfix ('vierter' -> "viert"*), Zahlen und Wörter aus zwei
    Buchstaben genau, Synonyme per ODER ('mietwohnung' -> ("mietwohnung"* OR "wohnraum"* OR "mietverhältnis"*))."""
    teile = [f'"{w}"' if w.isdigit() or len(w) < 3 else f'"{_stamm(w)}"*']
    for s in synonyme.get(w, []):
        ws = re.findall(r"\w+", s)
        if ws:
            teile.append('"' + " ".join(ws) + '"' + ("*" if len(ws) == 1 else ""))
    return teile[0] if len(teile) == 1 else "(" + " OR ".join(teile) + ")"


def fts_anfrage(text: str, verknuepfung: str = "AND", synonyme: dict[str, list[str]] | None = None) -> str:
    """Freitext -> FTS5-Anfrage mit groben Wortstämmen als Präfix ('vierter' -> "viert"*)."""
    return f" {verknuepfung} ".join(_gruppe(w, synonyme or {}) for w in suchworte(text))


class WissensbasisFehler(RuntimeError):
    """Datei ist keine (passende) Wissensbasis: leer, beschädigt, fremd oder mit altem Schema."""


class Wissensbasis:
    def __init__(self, pfad: str | Path = DB_STANDARD, suchwortschatz: Path = SYNONYME_DATEI) -> None:
        self.pfad = Path(pfad)
        if not self.pfad.is_file():
            raise FileNotFoundError(f"Wissensbasis fehlt: {self.pfad} (python3.12 -m pruefki.wissen.index --neu)")
        self.con = sqlite3.connect(nur_lesen_uri(self.pfad), uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        try:                                   # sqlite3.connect liest die Datei erst bei der ersten Abfrage
            version = self.meta().get("schema_version")
            self.con.execute("SELECT 1 FROM aliase LIMIT 1").fetchall()
        except sqlite3.DatabaseError as e:
            self.con.close()
            raise WissensbasisFehler(f"Wissensbasis nicht lesbar: {self.pfad} ({e}); neu bauen mit "
                                     "python3.12 -m pruefki.wissen.index --neu") from e
        if version != SCHEMA_VERSION:
            self.con.close()
            raise WissensbasisFehler(f"Wissensbasis {self.pfad} hat Schema {version}, erwartet {SCHEMA_VERSION}; "
                                     "neu bauen mit python3.12 -m pruefki.wissen.index --neu")
        self._alias_cache: dict[str, str | None] = {}
        self._schluessel_cache: dict[tuple[str, str], bool | None] = {}
        self.wortschatz = lade_suchwortschatz(suchwortschatz)
        self._kern: set[str] | None = None

    def schliessen(self) -> None:
        self.con.close()

    def meta(self) -> dict[str, str]:
        return {r["schluessel"]: r["wert"] for r in self.con.execute("SELECT schluessel, wert FROM meta")}

    # --- Gesetze ---------------------------------------------------------------------------------------------

    def gesetz_kuerzel(self, name: str) -> str | None:
        """Gesetzesname oder Abkürzung -> Kürzel ('SGB X' -> 'sgb_10'), None wenn unbekannt."""
        a, exakt = alias_schluessel(name), kompakt(name)
        if exakt not in self._alias_cache:
            r = self.con.execute("SELECT gesetz_kuerzel FROM aliase WHERE alias = ? "
                                 "ORDER BY rang, name != ?, wahl LIMIT 1", (a, exakt)).fetchone()
            self._alias_cache[exakt] = r[0] if r else None
        return self._alias_cache[exakt]

    def _gebeugt(self, name: str) -> str | None:
        """Name auch in gebeugter Form: 'SGB-II', 'des Sozialgerichtsgesetzes', 'des Bürgerlichen Gesetzbuchs',
        'Zehnten Buches Sozialgesetzbuch'. Es wird nur auf Namen zurückgeführt, die es genau so gibt."""
        k = self.gesetz_kuerzel(name)
        if k is None and "-" in name:
            k = self.gesetz_kuerzel(name.replace("-", " "))
        if k is None and re.search(r"(?:es|s)$", name) and len(name) > 12:   # Genitiv: '...gesetzes'
            k = self.gesetz_kuerzel(re.sub(r"(?:es|s)$", "", name))
        worte = name.split()
        if k is None and 2 <= len(worte) <= 4:
            formen = []
            for w in worte:
                f = [w]
                if w[:1].isupper() and len(w) > 4:
                    if re.search(r"(?:en|em|er)$", w):          # Adjektiv: 'Bürgerlichen' -> 'Bürgerliches'
                        f += [w[:-2] + "es", w[:-2] + "e", w[:-2] + "er"]
                    if w.endswith("es"):                        # Genitiv: 'Buches' -> 'Buch'
                        f.append(w[:-2])
                    if w.endswith("s"):
                        f.append(w[:-1])
                formen.append(list(dict.fromkeys(f)))
            for kombi in itertools.product(*formen):
                k = self.gesetz_kuerzel(" ".join(kombi))
                if k:
                    break
        return k

    def _aus_kandidaten(self, kandidaten: list[str]) -> str | None:
        """Längster bekannter Name; ein kürzerer zählt nicht, wenn ein Land folgt ('VwVfG NRW' ist Landesrecht)."""
        alle = kandidaten[0].split() if kandidaten else []
        for name in kandidaten:
            k = self._gebeugt(name)
            if k:
                n = len(name.split())
                if n < len(alle) and (alle[n] in _LAENDER_ABK or alle[n].lower() in _LAENDER_NAMEN):
                    return None
                return k
        return None

    def gesetz(self, name: str) -> dict | None:
        k = self.gesetz_kuerzel(name)
        if not k:
            return None
        r = self.con.execute("SELECT * FROM gesetze WHERE kuerzel = ?", (k,)).fetchone()
        return dict(r) if r else None

    # --- Normen ----------------------------------------------------------------------------------------------

    def _zeilen(self, sql: str, *args) -> list[sqlite3.Row]:
        return self.con.execute(
            "SELECT n.*, g.titel AS gesetz_titel, g.abk AS abk FROM normen n JOIN gesetze g "
            "ON g.kuerzel = n.gesetz_kuerzel WHERE " + sql, args).fetchall()

    @staticmethod
    def _treffer(r: sqlite3.Row, **extra) -> Treffer:
        return Treffer(zitat=r["zitat"], gesetz=r["gesetz_kuerzel"], abk=r["abk"], gesetz_titel=r["gesetz_titel"] or "",
                       enbez=r["enbez"] or "", enbez_norm=r["enbez_norm"] or "", titel=r["titel"] or "",
                       text=r["text"] or "", gliederung=r["gliederung"] or "", fussnoten=r["fussnoten"] or "",
                       art=r["art"], status=r["status"], quelle_url=r["quelle_url"], stand=r["stand"] or "",
                       builddate=r["builddate"] or "", **extra)

    def finde(self, kuerzel: str, schluessel: str) -> Treffer | None:
        """Norm eines Gesetzes über den Suchschlüssel ('§187', 'art1', 'art97§1')."""
        rows = self._zeilen("n.gesetz_kuerzel = ? AND n.enbez_norm = ? "
                            "ORDER BY n.status != 'geltend', n.position", kuerzel, schluessel)
        if rows:
            r = rows[0]
            hinweis = f"{len(rows)} Normen mit dieser Bezeichnung, die erste ist gezeigt" if len(rows) > 1 else ""
            if r["art"] == "artikel" and not (r["text"] or "").strip():
                teile = self._zeilen("n.gesetz_kuerzel = ? AND n.enbez_norm GLOB ? ORDER BY n.position",
                                     kuerzel, schluessel + "§*")
                if teile:
                    return self._zusammen(r, teile)
            return self._treffer(r, hinweis=hinweis)
        if schluessel.startswith("§"):
            # In Mantelgesetzen liegen §§ unter einem Artikel ('art4§1'); nur eindeutige Treffer zählen
            rows = self._zeilen("n.gesetz_kuerzel = ? AND n.enbez_norm GLOB ? ORDER BY n.position",
                                kuerzel, "art*" + schluessel)
            rows = [r for r in rows if re.fullmatch(r"art[0-9a-z]+" + re.escape(schluessel), r["enbez_norm"])]
            if len(rows) == 1:
                return self._treffer(rows[0], hinweis=f"gefunden als {rows[0]['zitat']}", unter_artikel=True)
        if schluessel.startswith("art") and "§" not in schluessel:
            teile = self._zeilen("n.gesetz_kuerzel = ? AND n.enbez_norm GLOB ? ORDER BY n.position",
                                 kuerzel, schluessel + "§*")
            if teile:
                return self._zusammen(None, teile)
        for r in self._zeilen("n.gesetz_kuerzel = ? AND n.status != 'geltend' AND "
                              "(n.enbez_norm GLOB '*-*' OR n.enbez_norm GLOB '*,*') ORDER BY n.position", kuerzel):
            if im_bereich(schluessel, r["enbez_norm"]):
                return self._treffer(r, hinweis=f"liegt im Bereich {r['zitat']}")
        return None

    def _zusammen(self, kopf: sqlite3.Row | None, teile: list[sqlite3.Row]) -> Treffer:
        erste = teile[0]
        basis = kopf or erste
        art = re.match(r"^(art[0-9a-z]+)§", erste["enbez_norm"])
        art_bez = re.sub(r"\s*§.*$", "", erste["zitat"])        # 'Art 97'
        text = "\n\n".join(f"{t['enbez']} {t['titel'] or ''}".strip() + "\n" + (t["text"] or "") for t in teile)
        t = self._treffer(basis, hinweis=f"zusammengesetzt aus {len(teile)} Normen")
        t.zitat = (kopf["zitat"] if kopf else f"{art_bez} {erste['abk']}")
        t.enbez_norm = art.group(1) if art else t.enbez_norm
        t.enbez = kopf["enbez"] if kopf else art_bez
        t.titel = kopf["titel"] if kopf else ""
        t.text = text
        t.status = "geltend" if any(x["status"] == "geltend" for x in teile) else t.status
        return t

    def treffer_fuer(self, v: Verweis, kuerzel: str | None = None) -> tuple[str | None, Treffer | None]:
        k = kuerzel or self._aus_kandidaten(v.gesetz)
        if not k:
            return None, None
        t = self.finde(k, v.schluessel)
        if t and v.absatz:
            t.absatz = v.absatz
            t.absatz_text = absatz_text(t.text, v.absatz)
        return k, t

    def normen(self, zitat: str, gesetz: str | None = None) -> list[tuple[Verweis, Treffer | None]]:
        kuerzel = self.gesetz_kuerzel(gesetz) if gesetz else None
        if gesetz and not kuerzel:
            return [(v, None) for v in zerlege(zitat)]
        return [(v, self.treffer_fuer(v, kuerzel)[1]) for v in zerlege(zitat)]

    def norm(self, gesetz_oder_zitat: str, paragraph: str | None = None) -> Treffer | None:
        """norm('§ 187 BGB') oder norm('BGB', '§ 187') oder norm('BGB', '187') -> Treffer oder None.
        Eine nackte Zahl gilt als §, in Gesetzen mit Artikeln als Artikel (norm('GG', '19') = Art. 19 GG)."""
        if paragraph is None:
            paare = self.normen(gesetz_oder_zitat)
        else:
            p = paragraph.strip()
            if re.match(r"^\d", p):
                paare = self.normen("§ " + p, gesetz=gesetz_oder_zitat)
                if paare and paare[0][1] is None:
                    artikel = self.normen("Art. " + p, gesetz=gesetz_oder_zitat)
                    if artikel and artikel[0][1] is not None:
                        paare = artikel
            else:
                paare = self.normen(p, gesetz=gesetz_oder_zitat)
        return paare[0][1] if paare else None

    def pruefe(self, zitat: str) -> list[dict]:
        """Je erkannter Norm: Gesetz, Fundstelle, Status, Absatz/Satz/Nummer geprüft, Ergebnis.
        Ergebnisse: ok, gesetz_unbekannt, norm_fehlt, weggefallen, verschoben, zukuenftig, nur_unter_artikel
        ('§ 30 EGAO' steht nur als 'Art 97 § 30 EGAO'), absatz_fehlt, satz_fehlt, nr_fehlt."""
        out = []
        for v in zerlege(zitat):
            k, t = self.treffer_fuer(v)
            e = {"norm": v.text, "schluessel": v.schluessel, "gesetz": k, "zitat": t.zitat if t else None,
                 "titel": t.titel if t else None, "status": t.status if t else None,
                 "absatz": v.absatz, "absatz_ok": None, "satz": v.satz, "satz_ok": None, "nr": v.nr, "nr_ok": None,
                 "stand": t.stand if t else None, "hinweis": "; ".join(x for x in (v.hinweis, t.hinweis if t else "")
                                                                         if x)}
            if k is None:
                e["ergebnis"] = "gesetz_unbekannt"
            elif t is None:
                e["ergebnis"] = "norm_fehlt"
            elif t.status != "geltend":
                e["ergebnis"] = t.status
            else:
                e["ergebnis"] = "nur_unter_artikel" if t.unter_artikel else "ok"
                self._pruefe_gliederung(v, t, e)
            out.append(e)
        return out

    @staticmethod
    def _pruefe_gliederung(v: Verweis, t: Treffer, e: dict) -> None:
        """Absatz, Satz und Nummer gegen den Normtext. Satz: höchstens so viele Sätze, wie der Text Satzenden hat.
        Nummer: muss als Listenmarke vorkommen; ohne jede Liste (und ohne Tabelle oder Bild) gibt es keine Nummer."""
        bereich = t.text
        vorhanden = absaetze(t.text)
        if v.absatz:
            e["absatz_ok"] = v.absatz in vorhanden if vorhanden else v.absatz == "1"
            if not e["absatz_ok"]:
                e["ergebnis"] = "absatz_fehlt"
                return
            bereich = absatz_text(t.text, v.absatz) or t.text
        if v.satz and v.satz.isdigit() and (v.absatz or not vorhanden):
            e["satz_ok"] = int(v.satz) <= saetze_hoechstens(bereich)
            if not e["satz_ok"]:
                e["ergebnis"] = "satz_fehlt"
                return
        if v.nr and re.fullmatch(r"\d+[a-z]?", v.nr) and not _unklar_gegliedert(bereich):
            e["nr_ok"] = v.nr in nummern(bereich)
            if not e["nr_ok"]:
                e["ergebnis"] = "nr_fehlt"

    def existiert(self, zitat: str, streng: bool = True) -> bool:
        """True, wenn das Zitat mindestens eine Norm nennt und alle genannten Normen im Bundesrecht stehen.
        streng=True: nur geltende Normen in genauer Bezeichnung; genannte Absätze, Sätze und Nummern müssen passen.
        streng=False: auch weggefallene, verschobene oder künftige Normen und ungenaue Bezeichnungen zählen."""
        erg = self.pruefe(zitat)
        if not erg:
            return False
        ok = {"ok"} if streng else {"ok", "weggefallen", "verschoben", "zukuenftig", "nur_unter_artikel",
                                    "absatz_fehlt", "satz_fehlt", "nr_fehlt"}
        return all(e["ergebnis"] in ok for e in erg)

    def existiert_schluessel(self, paragraph: str, gesetz: str) -> bool | None:
        """Für die Benchmark-Schlüssel aus pruefki.fristen.normen: ('37', 'SGBX'), ('art1', 'GG').
        None, wenn das Gesetz nicht in der Wissensbasis steht (z. B. Landesrecht wie BayVwVfG)."""
        schl = (paragraph, gesetz)
        if schl not in self._schluessel_cache:
            k = self.gesetz_kuerzel(gesetz)
            if k is None:
                self._schluessel_cache[schl] = None
            else:
                p = paragraph.lower()
                t = self.finde(k, p if p.startswith("art") else "§" + p)
                self._schluessel_cache[schl] = bool(t and t.status == "geltend")
        return self._schluessel_cache[schl]

    # --- Volltext --------------------------------------------------------------------------------------------

    def _kerngesetze(self) -> set[str]:
        if self._kern is None:
            self._kern = {k for k in map(self.gesetz_kuerzel, self.wortschatz["kerngesetze"]) if k}
        return self._kern

    def suche(self, text: str, limit: int = 10, gesetz: str | None = None, roh: bool = False) -> list[Treffer]:
        """BM25-Volltextsuche über Titel, Text und Wortteile (Grundwörter von Komposita).

        Freitext: Jedes Suchwort (Wortstamm als Präfix, dazu seine Synonyme aus synonyme.json) ist eine Gruppe. Gesucht
        wird mit ODER über alle Gruppen; die Rangfolge ist BM25 mal Faktoren: Norm enthält alle Gruppen x2, alle bis
        auf eine (ab 4 Gruppen) x1,5, Kerngesetz x1,5, Gesetz mit Hinweis aus synonyme.json x2, Anlage x0,5.
        Schutz: höchstens 2000 Zeichen und 8 Wörter, Einzelzeichen fallen weg.
        roh=True: text ist eine FTS5-Anfrage, ohne Gruppen und Synonyme."""
        filt, extra = "", []
        if gesetz:
            k = self.gesetz_kuerzel(gesetz)
            if not k:
                return []
            filt, extra = "AND n.gesetz_kuerzel = ?", [k]
        if roh:
            gruppen, anfrage = [], text
            hinweise: set[str] = set()
        else:
            worte = suchworte(text)
            gruppen = [_gruppe(w, self.wortschatz["synonyme"]) for w in worte]
            anfrage = " OR ".join(gruppen)
            hinweise = {k for w in worte for k in map(self.gesetz_kuerzel, self.wortschatz["gesetze"].get(w, [])) if k}
        if not anfrage:
            return []
        kern, hin = sorted(self._kerngesetze()), sorted(hinweise)
        sql = ("SELECT n.id, bm25(normen_fts, " + ", ".join(map(str, BM25_GEWICHTE)) + ")"
               f" * (CASE WHEN n.gesetz_kuerzel IN ({','.join('?' * len(kern))}) THEN {KERN_FAKTOR} ELSE 1 END)"
               f" * (CASE WHEN n.gesetz_kuerzel IN ({','.join('?' * len(hin))}) THEN {HINWEIS_FAKTOR} ELSE 1 END)"
               f" * (CASE WHEN n.art = 'anlage' THEN {ANLAGE_FAKTOR} ELSE 1 END) AS score "
               "FROM normen_fts JOIN normen n ON n.id = normen_fts.rowid "
               "WHERE normen_fts MATCH ? AND n.status = 'geltend' AND n.art != 'inhaltsuebersicht' "
               f"{filt} ORDER BY score LIMIT ?")
        kandidaten = self.con.execute(sql, (*kern, *hin, anfrage, *extra, KANDIDATEN)).fetchall()
        alle: set[int] = set()
        fast_alle: set[int] = set()
        if len(gruppen) >= 2:
            alle = self._rowids(" AND ".join(gruppen))
        if len(gruppen) >= 4:
            fast_alle = self._rowids(" OR ".join("(" + " AND ".join(gruppen[:i] + gruppen[i + 1:]) + ")"
                                                 for i in range(len(gruppen))))
        wertung = {i: s * (BONUS_ALLE if i in alle else BONUS_FAST_ALLE if i in fast_alle else 1.0)
                   for i, s in kandidaten}
        beste = sorted(wertung, key=wertung.get)[:limit]
        if not beste:
            return []
        rows = {r["id"]: r for r in self.con.execute(
            "SELECT n.*, g.titel AS gesetz_titel, g.abk AS abk, "
            "snippet(normen_fts, 3, '»', '«', ' … ', 16) AS ausschnitt "
            "FROM normen_fts JOIN normen n ON n.id = normen_fts.rowid JOIN gesetze g ON g.kuerzel = n.gesetz_kuerzel "
            f"WHERE normen_fts MATCH ? AND normen_fts.rowid IN ({','.join('?' * len(beste))})", (anfrage, *beste))}
        return [self._treffer(rows[i], score=round(wertung[i], 3), alle_worte=(i in alle) if len(gruppen) >= 2 else
                              None if roh else True, ausschnitt=(rows[i]["ausschnitt"] or "").replace("\n", " / "))
                for i in beste if i in rows]

    def _rowids(self, anfrage: str) -> set[int]:
        return {r for (r,) in self.con.execute("SELECT rowid FROM normen_fts WHERE normen_fts MATCH ?", (anfrage,))}


_STANDARD: Wissensbasis | None = None


def standard() -> Wissensbasis:
    global _STANDARD
    if _STANDARD is None:
        _STANDARD = Wissensbasis()
    return _STANDARD


def norm(gesetz: str, paragraph: str | None = None) -> Treffer | None:
    return standard().norm(gesetz, paragraph)


def suche(text: str, limit: int = 10, gesetz: str | None = None) -> list[Treffer]:
    return standard().suche(text, limit, gesetz)


def existiert(zitat: str, streng: bool = True) -> bool:
    return standard().existiert(zitat, streng)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normtext abrufen, Volltext suchen, Zitate prüfen")
    ap.add_argument("zitat", nargs="?", help="z. B. '§ 41 VwVfG', '§ 37 Abs. 2 SGB X', 'Art. 1 GG'")
    ap.add_argument("--suche", metavar="TEXT")
    ap.add_argument("--existiert", metavar="ZITAT")
    ap.add_argument("--gesetz", help="Suche auf ein Gesetz beschränken")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--db", type=Path, default=DB_STANDARD)
    args = ap.parse_args(argv)
    try:
        wb = Wissensbasis(args.db)
    except (FileNotFoundError, WissensbasisFehler) as e:
        print(e, file=sys.stderr)
        return 2
    if args.suche:
        if args.gesetz and not wb.gesetz_kuerzel(args.gesetz):
            print(f"Gesetz unbekannt: {args.gesetz!r} (nicht im Bundesrecht der Wissensbasis)", file=sys.stderr)
            return 2
        treffer = wb.suche(args.suche, args.limit, args.gesetz)
        if args.json:
            print(json.dumps([asdict(t) | {"text": None} for t in treffer], ensure_ascii=False, indent=1))
        else:
            print(f"Suche: {args.suche!r} -> {fts_anfrage(args.suche, 'OR', wb.wortschatz['synonyme'])}")
            for i, t in enumerate(treffer, 1):
                print(f"{i:2}. {t.zitat}" + (f" – {t.titel}" if t.titel else "") + f"  (Wert {t.score})")
                print(f"    {t.ausschnitt}")
            if not treffer:
                print("keine Treffer")
        return 0 if treffer else 1
    if args.existiert:
        erg = wb.pruefe(args.existiert)
        ok = wb.existiert(args.existiert)
        if args.json:
            print(json.dumps({"existiert": ok, "normen": erg}, ensure_ascii=False, indent=1))
        else:
            print(("JA" if ok else "NEIN") + f": {args.existiert}")
            for e in erg:
                fund = f" -> {e['zitat']} {e['titel'] or ''}".rstrip() if e["zitat"] else ""
                print(f"  {e['norm']}: {e['ergebnis']}{fund}" + (f" ({e['hinweis']})" if e["hinweis"] else ""))
        return 0 if ok else 1
    if not args.zitat:
        ap.print_help()
        return 2
    paare = wb.normen(args.zitat)
    if args.json:
        print(json.dumps([{"verweis": asdict(v), "treffer": asdict(t) if t else None} for v, t in paare],
                         ensure_ascii=False, indent=1))
        return 0 if paare and all(t for _, t in paare) else 1
    if not paare:
        print(f"Keine Norm erkannt in {args.zitat!r}", file=sys.stderr)
        return 1
    rc = 0
    for i, (v, t) in enumerate(paare):
        if i:
            print("\n" + "-" * 72 + "\n")
        if t is None:
            print(f"NICHT GEFUNDEN: {v.text}")
            rc = 1
            continue
        print(t.als_text())
        if v.absatz:
            print(f"\nAbs. {v.absatz}: " + (t.absatz_text or "nicht vorhanden"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
