"""Baut die Wissensbasis daten/wissen.sqlite aus daten/bund (gesetze-im-internet.de).

  python3.12 -m pruefki.wissen.index --neu     # alles neu: baut in <ziel>.neu und ersetzt die Datei dann atomar
  python3.12 -m pruefki.wissen.index           # nur Geändertes: stand.json (etag/geladen), dann builddate

Tabellen:
  gesetze     ein Eintrag je Gesetz/Verordnung mit Titel, Ausfertigung, Stand, Quelle-URL, builddate, geladen
  normen      jede Einzelnorm als Klartext mit Gliederung, Fußnoten, Position und Herkunft (Quelle-URL, Stand)
  normen_fts  FTS5-Volltext über jurabk, enbez, titel, text, wortteile (unicode61, Umlaute bleiben erhalten)
              wortteile: Grundwörter zusammengesetzter Substantive ('Berufungsfrist' -> 'frist'), damit die Suche nach
              'Frist' auch 'Berufungsfrist' findet. Grundwort ist der längste hintere Wortteil, der im Korpus als
              eigenes Substantiv steht (meist groß geschrieben, mindestens 4 Buchstaben); der vordere Teil muss ein
              Wort sein, auch mit Fugen-s ('Kündigungs|frist'), und mindestens 4 Buchstaben haben.
  grundwoerter  die Substantive aus dem letzten Neubau, Grundlage der Wortteile beim Aktualisieren
  namen       alle Namen eines Gesetzes aus dem XML (jurabk, amtabk, weitere jurabk, Kurz- und Langtitel)
  aliase      Suchschlüssel -> Gesetz ('SGBX' und 'SGB10' -> sgb_10, 'AO' -> ao_1977, 'EGBGB' -> bgbeg).
              Tragen mehrere Gesetze denselben Namen, entscheidet der Rang (manuell, amtliche Abkürzung,
              juris-Abkürzung, weitere, abgeleitet, Kurztitel, Langtitel, Kürzel), dann gleiche Schreibung
              (GBV/GbV), dann Übereinstimmung von amtlicher und juris-Abkürzung, dann die jüngere Ausfertigung
  meta        Schema-Version, Bauzeit, Quelle

Quelle: Bundesministerium der Justiz, www.gesetze-im-internet.de. Gesetze und Verordnungen sind amtliche Werke
(§ 5 UrhG); die Nutzung der Daten ist nach § 4 Datennutzungsgesetz (DNG) frei.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from pruefki.wissen import gii

SCHEMA_VERSION = "3"
WURZEL = Path(__file__).resolve().parents[2]
DB_STANDARD = WURZEL / "daten" / "wissen.sqlite"
QUELLE_STANDARD = WURZEL / "daten" / "bund"
QUELLE_HINWEIS = ("Bundesministerium der Justiz, www.gesetze-im-internet.de; amtliche Werke (§ 5 UrhG), "
                  "Nutzung frei nach § 4 DNG")

SCHEMA = """
CREATE TABLE meta(schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL);
CREATE TABLE gesetze(
  kuerzel TEXT PRIMARY KEY, jurabk TEXT NOT NULL, amtabk TEXT, abk TEXT NOT NULL, titel TEXT, kurztitel TEXT,
  ausfertigung TEXT, fundstelle TEXT, stand TEXT, hinweise TEXT, quelle_url TEXT, builddate TEXT, doknr TEXT,
  etag TEXT, geladen TEXT, dateien TEXT, normen_anzahl INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE normen(
  id INTEGER PRIMARY KEY, gesetz_kuerzel TEXT NOT NULL REFERENCES gesetze(kuerzel), jurabk TEXT NOT NULL,
  enbez TEXT, enbez_norm TEXT, zitat TEXT, art TEXT, status TEXT, titel TEXT, gliederung TEXT, text TEXT,
  fussnoten TEXT, position INTEGER, doknr TEXT, builddate TEXT, quelle_url TEXT, stand TEXT, wortteile TEXT
);
CREATE INDEX normen_schluessel ON normen(gesetz_kuerzel, enbez_norm);
CREATE TABLE namen(gesetz_kuerzel TEXT NOT NULL, name TEXT NOT NULL, art TEXT NOT NULL);
CREATE INDEX namen_gesetz ON namen(gesetz_kuerzel);
CREATE TABLE aliase(
  alias TEXT NOT NULL, gesetz_kuerzel TEXT NOT NULL, art TEXT NOT NULL, rang INTEGER NOT NULL,
  wahl INTEGER NOT NULL, name TEXT NOT NULL, PRIMARY KEY(alias, gesetz_kuerzel)
) WITHOUT ROWID;
CREATE TABLE grundwoerter(wort TEXT PRIMARY KEY) WITHOUT ROWID;
CREATE VIRTUAL TABLE normen_fts USING fts5(
  jurabk, enbez, titel, text, wortteile, content='normen', content_rowid='id',
  tokenize='unicode61 remove_diacritics 0'
);
"""

TRIGGER = """
CREATE TRIGGER normen_ai AFTER INSERT ON normen BEGIN
  INSERT INTO normen_fts(rowid, jurabk, enbez, titel, text, wortteile)
  VALUES (new.id, new.jurabk, new.enbez, new.titel, new.text, new.wortteile);
END;
CREATE TRIGGER normen_ad AFTER DELETE ON normen BEGIN
  INSERT INTO normen_fts(normen_fts, rowid, jurabk, enbez, titel, text, wortteile)
  VALUES ('delete', old.id, old.jurabk, old.enbez, old.titel, old.text, old.wortteile);
END;
CREATE TRIGGER normen_au AFTER UPDATE ON normen BEGIN
  INSERT INTO normen_fts(normen_fts, rowid, jurabk, enbez, titel, text, wortteile)
  VALUES ('delete', old.id, old.jurabk, old.enbez, old.titel, old.text, old.wortteile);
  INSERT INTO normen_fts(rowid, jurabk, enbez, titel, text, wortteile)
  VALUES (new.id, new.jurabk, new.enbez, new.titel, new.text, new.wortteile);
END;
"""

# ---------------------------------------------------------------------------------------------------------------
# Aliase
# ---------------------------------------------------------------------------------------------------------------

RANG = {"manuell": 0, "amtabk": 1, "jurabk": 2, "jurabk_weitere": 3, "abgeleitet": 4, "kurzue": 5, "langue": 6,
        "kuerzel": 7}

# Gängige Zitierweisen, die sich nicht von selbst ergeben oder besonders sicher sitzen sollen (nur wenn vorhanden).
MANUELL = {
    "BGB": "bgb", "EGBGB": "bgbeg", "GG": "gg", "Grundgesetz": "gg", "ZPO": "zpo", "EGZPO": "zpoeg",
    "GVG": "gvg", "EGGVG": "gvgeg", "StGB": "stgb", "EGStGB": "stgbeg", "StPO": "stpo",
    "VwVfG": "vwvfg", "VwGO": "vwgo", "VwZG": "vwzg_2005", "VwVG": "vwvg", "SGG": "sgg", "FGO": "fgo",
    "AO": "ao_1977", "EGAO": "aoeg_1977", "KSchG": "kschg", "ArbGG": "arbgg", "BUrlG": "burlg", "TzBfG": "tzbfg",
    "BetrVG": "betrvg", "MuSchG": "muschg_2018", "HGB": "hgb", "EStG": "estg", "UStG": "ustg_1980",
    "GKG": "gkg_2004", "RVG": "rvg", "BEEG": "beeg", "WoGG": "wogg", "BAföG": "baf_g", "SGB IX": "sgb_9_2018",
    "UrhG": "urhg", "DNG": "dng", "BDSG": "bdsg_2018", "InsO": "inso", "BauGB": "bbaug", "StVO": "stvo_2013",
    "StVG": "stvg", "AufenthG": "aufenthg_2004", "AsylG": "asylvfg_1992", "IfSG": "ifsg", "BBG": "bbg_2009",
    "AEG": "aeg_1994", "UmwStG": "umwstg_2006",
}

_ROEMISCH = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]
_ORDINAL = ["", "Erstes", "Zweites", "Drittes", "Viertes", "Fünftes", "Sechstes", "Siebtes", "Achtes", "Neuntes",
            "Zehntes", "Elftes", "Zwölftes", "Dreizehntes", "Vierzehntes"]
_UMLAUT = str.maketrans({"Ä": "AE", "Ö": "OE", "Ü": "UE", "ä": "ae", "ö": "oe", "ü": "ue"})


_KOMPAKT = re.compile("[\\s.\u00a0\u202f]+")


def kompakt(name: str) -> str:
    """Name ohne Leerraum und Punkte, Schreibung bleibt ('SGB X' -> 'SGBX', 'GbV' -> 'GbV')."""
    return _KOMPAKT.sub("", unicodedata.normalize("NFC", name or ""))


def alias_schluessel(name: str) -> str:
    """Vergleichsform eines Gesetzesnamens: ohne Leerraum und Punkte, Großbuchstaben ('SGB X' -> 'SGBX')."""
    return kompakt(name).upper()


def varianten(name: str) -> list[str]:
    """Abgeleitete Schreibweisen: SGB römisch/arabisch und als 'Zehntes Buch Sozialgesetzbuch', ohne Jahreszahl,
    Umlaute als ae/oe/ue."""
    s = " ".join((name or "").split())
    out: list[str] = []
    m = re.fullmatch(r"SGB\s*([IVX]+|\d{1,2})(?:\s+(?:19|20)\d{2})?", s, re.IGNORECASE)
    if m:
        teil = m.group(1).upper()
        zahl = int(teil) if teil.isdigit() else (_ROEMISCH.index(teil) if teil in _ROEMISCH else 0)
        if 1 <= zahl <= 14:
            out += [f"SGB {zahl}", f"SGB {_ROEMISCH[zahl]}", f"{_ORDINAL[zahl]} Buch Sozialgesetzbuch",
                    f"Sozialgesetzbuch {_ORDINAL[zahl]} Buch"]
    m = re.fullmatch(r"(.*\S)\s+(?:19|20)\d{2}", s)
    if m:
        out.append(m.group(1))
    for x in [s, *out]:
        if re.search("[ÄÖÜäöü]", x):
            out.append(x.translate(_UMLAUT))
    return [x for x in dict.fromkeys(out) if alias_schluessel(x) != alias_schluessel(s)]


def berechne_aliase(con: sqlite3.Connection) -> dict:
    """Füllt die Tabelle aliase neu aus namen, MANUELL und den Ableitungsregeln."""
    gesetze = {k: (a or "") for k, a in con.execute("SELECT kuerzel, ausfertigung FROM gesetze")}
    kand: dict[str, dict[str, dict]] = {}

    def neu(name: str, kuerzel: str, art: str) -> None:
        a = alias_schluessel(name)
        if not a or kuerzel not in gesetze:
            return
        e = kand.setdefault(a, {}).get(kuerzel)
        if e is None or RANG[art] < e["rang"]:
            e = kand[a][kuerzel] = {"rang": RANG[art], "art": art, "name": kompakt(name),
                                    "konsens": e["konsens"] if e else set()}
        if RANG[art] <= RANG["jurabk"]:
            e["konsens"].add(art)

    namen = list(con.execute("SELECT gesetz_kuerzel, name, art FROM namen"))
    for k, name, art in namen:
        neu(name, k, art)
        for v in varianten(name):
            neu(v, k, "abgeleitet")
    for name, k in MANUELL.items():
        neu(name, k, "manuell")
    for k in gesetze:
        neu(k, k, "kuerzel")
    # Einführungsgesetze: juris schreibt 'BGBEG', zitiert wird 'EGBGB'
    stark = {a for a, ks in kand.items() if any(e["rang"] <= RANG["jurabk"] for e in ks.values())}
    for k, name, art in namen:
        if art not in ("jurabk", "amtabk"):
            continue
        basis = re.sub(r"\s+(?:19|20)\d{2}$", "", name)
        if basis.upper().endswith("EG") and alias_schluessel(basis[:-2]) in stark:
            neu("EG" + basis[:-2], k, "abgeleitet")

    def ordnung(kv: tuple[str, dict]) -> tuple:
        k, e = kv
        return (e["rang"], -len(e["konsens"]), _neg(gesetze.get(k, "")), k)

    con.execute("DELETE FROM aliase")
    zeilen = []
    kollisionen = 0
    for a, ks in kand.items():
        geordnet = sorted(ks.items(), key=ordnung)
        if len(geordnet) > 1 and ordnung(geordnet[0])[:2] == ordnung(geordnet[1])[:2]:
            kollisionen += 1
        zeilen += [(a, k, e["art"], e["rang"], i, e["name"]) for i, (k, e) in enumerate(geordnet)]
    con.executemany("INSERT INTO aliase(alias, gesetz_kuerzel, art, rang, wahl, name) VALUES (?,?,?,?,?,?)", zeilen)
    return {"aliase": len(kand), "alias_zeilen": len(zeilen), "gleichrangige_kollisionen": kollisionen}


def _neg(datum: str) -> str:
    """Sortierschlüssel: spätere Ausfertigung zuerst."""
    return "".join(chr(0x10FFFF - ord(c)) for c in datum)


# ---------------------------------------------------------------------------------------------------------------
# Wortteile: Grundwörter zusammengesetzter Substantive
# ---------------------------------------------------------------------------------------------------------------

_WORT = re.compile(r"[^\W\d_]{4,}")
_LANGES_WORT = re.compile(r"[^\W\d_]{8,}")
_FUGEN = ("s", "es", "n", "en", "er", "e")


class Wortzaehler:
    """Zählt je Wort, wie oft es groß und wie oft klein geschrieben im Korpus steht (Substantive stehen groß)."""

    def __init__(self) -> None:
        self.gross: Counter = Counter()
        self.klein: Counter = Counter()

    def zaehle(self, *texte: str | None) -> None:
        for t in texte:
            if t:
                worte = _WORT.findall(t)
                self.gross.update(w.lower() for w in worte if w[0].isupper())
                self.klein.update(w for w in worte if w[0].islower())

    def nomen(self, mindestens: int = 5) -> set[str]:
        """Wörter, die mindestens 5-mal und mindestens doppelt so oft groß wie klein geschrieben stehen."""
        return {w for w, n in self.gross.items() if n >= mindestens and n >= 2 * self.klein.get(w, 0)}

    def worte(self) -> set[str]:
        return set(self.gross) | set(self.klein)


class Zerleger:
    """'Berufungsfrist' -> ['frist'], 'Kündigungsschutzklage' -> ['klage'], 'Rentenversicherung' -> ['versicherung'].
    Nur Substantive werden zerlegt; Grundwort ist der längste hintere Teil (ab 4 Buchstaben), der selbst ein Substantiv
    ist, wenn der vordere Teil (ab 4 Buchstaben) ein Wort ist, auch mit Fuge ('Kündigungs-', 'Miet-' zu 'Miete')."""

    def __init__(self, nomen: set[str], worte: set[str]) -> None:
        self.nomen, self.worte = nomen, worte
        self._cache: dict[str, tuple[str, ...]] = {}

    def _vorne_ok(self, p: str) -> bool:
        if len(p) < 4:
            return False
        if p in self.worte or p + "e" in self.worte or p + "en" in self.worte:
            return True
        return any(p.endswith(f) and len(p) - len(f) >= 3 and p[:-len(f)] in self.worte for f in _FUGEN)

    def teile(self, wort: str) -> tuple[str, ...]:
        w = wort.lower()
        if w not in self._cache:
            out: list[str] = []
            x = w
            while True:
                t = next((x[i:] for i in range(4, len(x) - 3) if x[i:] in self.nomen and self._vorne_ok(x[:i])), None)
                if not t:
                    break
                out.append(t)
                x = t
            self._cache[w] = tuple(out)
        return self._cache[w]

    def wortteile(self, *texte: str | None) -> str:
        teile: set[str] = set()
        for t in texte:
            for w in _LANGES_WORT.findall((t or "").lower()):
                if w in self.nomen:
                    teile.update(self.teile(w))
        return " ".join(sorted(teile))


def setze_wortteile(con: sqlite3.Connection, zerleger: Zerleger, ids: list[int] | None = None) -> int:
    """Spalte normen.wortteile füllen (alle Normen oder nur ids)."""
    if ids is None:
        rows = con.execute("SELECT id, titel, text FROM normen").fetchall()
    else:
        rows = [r for i in ids for r in con.execute("SELECT id, titel, text FROM normen WHERE id = ?", (i,))]
    werte = [(zerleger.wortteile(ti, tx) or None, i) for i, ti, tx in rows]
    con.executemany("UPDATE normen SET wortteile = ? WHERE id = ?", werte)
    return sum(1 for w, _ in werte if w)


def zerleger_aus_db(con: sqlite3.Connection) -> Zerleger:
    """Für das Aktualisieren: Substantive aus dem letzten Neubau, Wörter aus dem Volltextindex."""
    nomen = {w for (w,) in con.execute("SELECT wort FROM grundwoerter")}
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.normen_vokabular USING fts5vocab(main, normen_fts, row)")
    worte = {t for (t,) in con.execute("SELECT term FROM temp.normen_vokabular")}
    return Zerleger(nomen, worte)


# ---------------------------------------------------------------------------------------------------------------
# Laden und Schreiben
# ---------------------------------------------------------------------------------------------------------------

_SICHERER_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")


def xml_pfade(quelle: Path, kuerzel: str, info: dict) -> list[Path]:
    if not _SICHERER_NAME.fullmatch(kuerzel) or ".." in kuerzel:
        raise gii.GiiFehler(f"unzulässiges Kürzel {kuerzel!r}")
    ordner = quelle / "xml" / kuerzel
    namen = [d for d in info.get("dateien") or [] if d.lower().endswith(".xml")]
    if namen:
        for d in namen:
            if not _SICHERER_NAME.fullmatch(d) or ".." in d:
                raise gii.GiiFehler(f"{kuerzel}: unzulässiger Dateiname {d!r}")
        return [ordner / d for d in namen]
    return sorted(ordner.glob("*.xml"))


def kurzstand(g: gii.Gesetz) -> str:
    """Stand für jede Normzeile: die Standangabe 'Stand' (sonst 'Neuf' oder die erste), plus Builddatum."""
    st = dict(g.standangaben)
    s = st.get("Stand") or st.get("Neuf") or (g.standangaben[0][1] if g.standangaben else "")
    return f"{s} (Build {g.builddate})" if s else f"Build {g.builddate}"


def anzeige_abk(kuerzel: str, g: gii.Gesetz) -> str:
    """Abkürzung für Zitate: amtliche Abkürzung, sonst gängige (EGBGB statt BGBEG, SGB III statt SGB 3),
    sonst die juris-Abkürzung."""
    if g.amtabk:
        return g.amtabk
    gaengig = [n for n, k in MANUELL.items() if k == kuerzel and " " not in n and len(n) <= 10]
    if gaengig:
        return gaengig[0]
    m = re.fullmatch(r"SGB (\d{1,2})(?: (?:19|20)\d{2})?", g.jurabk)
    if m and 1 <= int(m.group(1)) <= 14:
        return f"SGB {_ROEMISCH[int(m.group(1))]}"
    return g.jurabk


def _zitat(n: gii.Norm, abk: str) -> str:
    e = re.sub(r"^\(XXXX\)\s*", "", n.enbez)
    teile = [n.artikel, e, abk] if n.artikel else [e, abk]
    return " ".join(t for t in teile if t)


def schreibe_gesetz(con: sqlite3.Connection, kuerzel: str, info: dict, g: gii.Gesetz) -> int:
    url = info.get("url") or f"https://www.gesetze-im-internet.de/{kuerzel}/xml.zip"
    stand = kurzstand(g)
    abk = anzeige_abk(kuerzel, g)
    con.execute(
        "INSERT INTO gesetze(kuerzel, jurabk, amtabk, abk, titel, kurztitel, ausfertigung, fundstelle, stand, "
        "hinweise, quelle_url, builddate, doknr, etag, geladen, dateien, normen_anzahl) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (kuerzel, g.jurabk, g.amtabk or None, abk, g.langue or info.get("titel"), g.kurzue or None,
         g.ausfertigung, "; ".join(g.fundstellen), g.stand, g.hinweise, url, g.builddate, g.doknr,
         info.get("etag"), info.get("geladen"), json.dumps(info.get("dateien") or []), len(g.normen)))
    con.executemany(
        "INSERT INTO normen(gesetz_kuerzel, jurabk, enbez, enbez_norm, zitat, art, status, titel, gliederung, text, "
        "fussnoten, position, doknr, builddate, quelle_url, stand) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(kuerzel, n.jurabk or g.jurabk, n.enbez, n.enbez_norm, _zitat(n, abk), n.art, n.status, n.titel,
          n.gliederung, n.text, n.fussnoten, n.position, n.doknr, n.builddate, url, stand) for n in g.normen])
    con.executemany("INSERT INTO namen(gesetz_kuerzel, name, art) VALUES (?,?,?)",
                    [(kuerzel, name, art) for name, art in g.namen()])
    return len(g.normen)


def loesche_gesetz(con: sqlite3.Connection, kuerzel: str) -> None:
    con.execute("DELETE FROM normen WHERE gesetz_kuerzel = ?", (kuerzel,))
    con.execute("DELETE FROM namen WHERE gesetz_kuerzel = ?", (kuerzel,))
    con.execute("DELETE FROM gesetze WHERE kuerzel = ?", (kuerzel,))


def lies_stand(quelle: Path) -> dict:
    return json.loads((quelle / "stand.json").read_text("utf-8"))


def _setze_meta(con: sqlite3.Connection, quelle: Path) -> None:
    gesetze = con.execute("SELECT COUNT(*) FROM gesetze").fetchone()[0]
    normen = con.execute("SELECT COUNT(*) FROM normen").fetchone()[0]
    werte = {"schema_version": SCHEMA_VERSION, "gebaut": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "quelle": QUELLE_HINWEIS, "quelle_ordner": str(quelle), "gesetze": str(gesetze),
             "normen": str(normen)}
    con.executemany("INSERT OR REPLACE INTO meta(schluessel, wert) VALUES (?,?)", list(werte.items()))


def baue_neu(quelle: Path, ziel: Path, log=print) -> dict:
    """Ganze Datenbank neu bauen (in ziel.neu, dann atomar umbenennen)."""
    stand = lies_stand(quelle)
    tmp = ziel.with_name(ziel.name + ".neu")
    for p in (tmp, tmp.with_name(tmp.name + "-journal")):
        if p.exists():
            p.unlink()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp)
    erg = {"neu": 0, "fehler": [], "uebersprungen": 0}
    zaehler = Wortzaehler()
    try:
        con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA cache_size=-200000;")
        con.executescript(SCHEMA)
        con.execute("BEGIN")
        for i, (kuerzel, info) in enumerate(sorted(stand.items()), 1):
            if not info.get("dateien") and not (quelle / "xml" / kuerzel).is_dir():
                erg["uebersprungen"] += 1
                continue
            try:
                g = gii.lese_dateien(xml_pfade(quelle, kuerzel, info))
            except (gii.GiiFehler, OSError) as e:
                erg["fehler"].append(f"{kuerzel}: {e}")
                continue
            schreibe_gesetz(con, kuerzel, info, g)
            for n in g.normen:
                zaehler.zaehle(n.titel, n.text)
            erg["neu"] += 1
            if i % 1000 == 0:
                log(f"  {i}/{len(stand)} gelesen")
        log("  Wortteile ...")
        nomen = zaehler.nomen()
        con.executemany("INSERT INTO grundwoerter(wort) VALUES (?)", [(w,) for w in sorted(nomen)])
        erg["normen_mit_wortteilen"] = setze_wortteile(con, Zerleger(nomen, zaehler.worte()))
        del zaehler
        log("  Volltextindex ...")
        con.execute("INSERT INTO normen_fts(normen_fts) VALUES ('rebuild')")
        for stmt in _trigger_statements():
            con.execute(stmt)
        erg.update(berechne_aliase(con))
        _setze_meta(con, quelle)
        con.execute("INSERT INTO normen_fts(normen_fts) VALUES ('optimize')")
        con.commit()
        con.execute("ANALYZE")
        con.commit()
    except BaseException:
        con.close()
        tmp.unlink(missing_ok=True)
        raise
    con.close()
    os.replace(tmp, ziel)
    return erg


def _trigger_statements() -> list[str]:
    return [s.strip() + "\nEND;" for s in TRIGGER.split("END;") if s.strip()]


def aktualisiere(quelle: Path, ziel: Path, log=print) -> dict:
    """Nur geänderte Gesetze neu einlesen. Ohne vorhandene Datenbank: wie baue_neu."""
    if not ziel.exists():
        return baue_neu(quelle, ziel, log)
    stand = lies_stand(quelle)
    con = sqlite3.connect(ziel)
    erg = {"neu": 0, "geaendert": 0, "nur_meta": 0, "unveraendert": 0, "entfernt": 0, "fehler": [],
           "uebersprungen": 0}
    try:
        try:
            version = con.execute("SELECT wert FROM meta WHERE schluessel='schema_version'").fetchone()
        except sqlite3.DatabaseError:          # keine oder fremde Datei
            version = None
        if not version or version[0] != SCHEMA_VERSION:
            con.close()
            log("  Schema veraltet, baue neu")
            return baue_neu(quelle, ziel, log)
        vorhanden = {k: (e, gl, b) for k, e, gl, b in
                     con.execute("SELECT kuerzel, etag, geladen, builddate FROM gesetze")}
        zerleger: Zerleger | None = None
        con.execute("BEGIN IMMEDIATE")
        for kuerzel, info in sorted(stand.items()):
            alt = vorhanden.get(kuerzel)
            if not info.get("dateien") and not (quelle / "xml" / kuerzel).is_dir():
                erg["uebersprungen"] += 1
                continue
            if alt and alt[0] == info.get("etag") and alt[1] == info.get("geladen"):
                erg["unveraendert"] += 1
                continue
            try:
                g = gii.lese_dateien(xml_pfade(quelle, kuerzel, info))
            except (gii.GiiFehler, OSError) as e:
                erg["fehler"].append(f"{kuerzel}: {e}")
                continue
            if alt and alt[2] == g.builddate:
                con.execute("UPDATE gesetze SET etag = ?, geladen = ? WHERE kuerzel = ?",
                            (info.get("etag"), info.get("geladen"), kuerzel))
                erg["nur_meta"] += 1
                continue
            if alt:
                loesche_gesetz(con, kuerzel)
            schreibe_gesetz(con, kuerzel, info, g)
            zerleger = zerleger or zerleger_aus_db(con)
            setze_wortteile(con, zerleger, [i for (i,) in con.execute(
                "SELECT id FROM normen WHERE gesetz_kuerzel = ?", (kuerzel,))])
            erg["geaendert" if alt else "neu"] += 1
        for kuerzel in sorted(set(vorhanden) - set(stand)):
            loesche_gesetz(con, kuerzel)
            erg["entfernt"] += 1
        erg.update(berechne_aliase(con))
        _setze_meta(con, quelle)
        con.commit()
    except BaseException:
        con.rollback()
        con.close()
        raise
    con.close()
    return erg


def nur_lesen_uri(pfad: Path) -> str:
    """SQLite-URI zum Lesen; der Pfad wird maskiert ('#', '?', '%' im Ordnernamen)."""
    return Path(pfad).resolve().as_uri() + "?mode=ro"


def kennzahlen(ziel: Path) -> dict:
    con = sqlite3.connect(nur_lesen_uri(ziel), uri=True)
    try:
        return {
            "gesetze": con.execute("SELECT COUNT(*) FROM gesetze").fetchone()[0],
            "normen": con.execute("SELECT COUNT(*) FROM normen").fetchone()[0],
            "normen_geltend": con.execute("SELECT COUNT(*) FROM normen WHERE status='geltend'").fetchone()[0],
            "paragraphen_artikel": con.execute(
                "SELECT COUNT(*) FROM normen WHERE art IN ('paragraph','artikel')").fetchone()[0],
            "groesse_bytes": ziel.stat().st_size,
        }
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Wissensbasis Bundesrecht bauen oder aktualisieren")
    ap.add_argument("--neu", action="store_true", help="komplett neu bauen")
    ap.add_argument("--quelle", type=Path, default=QUELLE_STANDARD, help="Ordner mit stand.json und xml/")
    ap.add_argument("--db", type=Path, default=DB_STANDARD)
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    erg = baue_neu(args.quelle, args.db) if args.neu else aktualisiere(args.quelle, args.db)
    dauer = time.perf_counter() - t0
    k = kennzahlen(args.db)
    print(f"FERTIG in {dauer:.1f} s: {k['gesetze']} Gesetze, {k['normen']} Normen "
          f"({k['normen_geltend']} geltend, {k['paragraphen_artikel']} §/Art), "
          f"{k['groesse_bytes'] / 1e6:.1f} MB -> {args.db}")
    print("  " + ", ".join(f"{a} {b}" for a, b in erg.items() if a != "fehler"))
    for f in erg["fehler"][:20]:
        print(f"  FEHLER {f}")
    return 0 if not erg["fehler"] else 1


if __name__ == "__main__":
    sys.exit(main())
