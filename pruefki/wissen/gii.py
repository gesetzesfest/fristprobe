"""Parser für gii-norm-XML von gesetze-im-internet.de (DTD 1.01).

Eine Datei ist ein Gesetz oder eine Verordnung (<dokumente>) mit einer Folge von <norm>-Elementen:

- Die erste Norm mit <langue> ist der Rahmen: Langtitel, Ausfertigung, Fundstelle, Stand, Hinweise (Fußnoten).
- Normen mit <gliederungseinheit> und ohne <enbez> sind Überschriften (Buch, Abschnitt, Artikel). Sie bilden den
  Gliederungspfad. Haben sie eigenen Text (Artikel in Änderungsgesetzen) oder sind sie ein Artikel, werden sie
  zusätzlich als Norm geführt. Fußnoten einer Überschrift ohne eigenen Text stehen bei jeder Norm darunter
  ('Zu Abschnitt 2 ...: Amtlicher Hinweis ...'), ohne Norm darunter bei den Hinweisen des Gesetzes.
- Text: Tabellenüberschriften gehören dazu; juris-Notizen (<kommentar>, '(Fundstelle: ...)') stehen bei den Fußnoten.
- Alle übrigen sind Einzelnormen: §, Art, Anlage, Eingangsformel, Inhaltsübersicht, Schlussformel ...

Sicherheit: Die Dateien sind fremde Daten. Geparst wird nur mit xml.etree (expat). expat lädt die externe DTD nicht
und löst keine externen Entitäten auf, beim Parsen gibt es also keinen Netzzugriff. Dokumente mit eigener
<!ENTITY>-Deklaration werden abgelehnt (Schutz gegen Entity-Expansion). Nichts aus den Dateien wird ausgeführt.

  python3.12 -m pruefki.wissen.gii daten/bund/xml/vwvfg/BJNR012530976.xml [--enbez "§ 41"]
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


class GiiFehler(ValueError):
    """Datei ist kein lesbares gii-norm-Dokument."""


def _ws(s: str | None) -> str:
    return " ".join(s.split()) if s else ""


def _datum(builddate: str | None) -> str:
    """'20260506175647' -> '2026-05-06T17:56:47' (sonst unverändert)."""
    b = (builddate or "").strip()
    if re.fullmatch(r"\d{14}", b):
        return f"{b[0:4]}-{b[4:6]}-{b[6:8]}T{b[8:10]}:{b[10:12]}:{b[12:14]}"
    return b


# ---------------------------------------------------------------------------------------------------------------
# Bezeichnungen normalisieren
# ---------------------------------------------------------------------------------------------------------------

_TYPWORTE = (
    (r"§§?", "§"), (r"Artikel|Art\.?", "art"), (r"Anlagen?", "anlage"), (r"Anhang|Anh\.", "anhang"),
    (r"Muster", "muster"), (r"Formblatt", "formblatt"), (r"Regel", "regel"), (r"Nr\.?", "nr"),
    (r"Tabelle", "tabelle"),
)
_TYP_RE = re.compile(
    r"^(?:" + "|".join(f"(?P<t{i}>{p})" for i, (p, _) in enumerate(_TYPWORTE)) + r")(?=[\s\d]|$)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_WIEDERHOLT = r"(?:§§?|Artikel|Art\.?|Anlagen?)?"
_BIS = re.compile(r"\s*(?:\bbis\b|–|(?<=\w)-(?=\s*\w))\s*" + _WIEDERHOLT + r"\s*", re.IGNORECASE)
_UND = re.compile(r"\s*(?:,|\bund\b|\bu\.)\s*" + _WIEDERHOLT + r"\s*", re.IGNORECASE)
_ART_EINZEL = re.compile(r"^(?:Artikel|Art\.?)\s*(?:\d+[a-z]?|[IVXLC]+)$")


def enbez_normal(enbez: str) -> str:
    """Bezeichnung -> Suchschlüssel: '§ 187' -> '§187', 'Art 1' -> 'art1', 'Anlage 2a' -> 'anlage2a',
    '(XXXX) §§ 3 bis 6' -> '§3-6', '(XXXX) §§ 26 u. 27' -> '§26,27', 'Eingangsformel' -> 'eingangsformel'."""
    s = _ws(enbez)
    s = re.sub(r"^\(XXXX\)\s*", "", s)
    if not s:
        return ""
    m = _TYP_RE.match(s)
    if m:
        typ = next(_TYPWORTE[i][1] for i in range(len(_TYPWORTE)) if m.group(f"t{i}"))
        rest = _UND.sub(",", _BIS.sub("-", m.group("rest")))
        rest = re.sub(r"\s+", "", rest).lower().rstrip(".")
        return typ + rest
    return re.sub(r"\s+", "", s).lower().replace("ß", "ss").rstrip(".")


def _art_der_norm(enbez: str) -> str:
    e = re.sub(r"^\(XXXX\)\s*", "", _ws(enbez))
    if not e:
        return "text"
    if e.startswith("§"):
        return "paragraph"
    if re.match(r"(?:Artikel|Art\.?)(?:\s|\d|$)", e):
        return "artikel"
    if re.match(r"(?:Anlage|Anhang|Muster|Formblatt|Tabelle)", e):
        return "anlage"
    if e.startswith("Eingangsformel"):
        return "eingangsformel"
    if re.match(r"Schlu(?:ss|ß)formel", e):
        return "schlussformel"
    if re.match(r"(?:Inhaltsübersicht|Inhaltsverzeichnis|Übersicht|Inhalt|Gliederung)$", e):
        return "inhaltsuebersicht"
    if e.startswith("Präambel"):
        return "praeambel"
    return "sonstige"


_WEGGEFALLEN = re.compile(r"\(?\s*(?:weggefallen|aufgehoben|gegenstandslos|entfällt|entfallen)\s*\)?\.?", re.I)


def _status(enbez: str, enbez_norm: str, titel: str, text: str) -> str:
    """geltend, weggefallen, verschoben ('(jetzt § 650)') oder zukuenftig ('(zukünftig in Kraft)')."""
    t = titel.strip()
    if "zukünftig in kraft" in t.lower():
        return "zukuenftig"
    if re.fullmatch(r"\(jetzt\b[^)]*\)", t) and not text.strip():
        return "verschoben"
    if (_WEGGEFALLEN.fullmatch(t) or re.search(r"\((?:weggefallen|aufgehoben|gegenstandslos)\)$", t)
            or _WEGGEFALLEN.fullmatch(text.strip()) or text.strip() in ("-", "–")):
        return "weggefallen"
    if enbez.startswith("(XXXX)") and enbez_norm and not text.strip():
        return "weggefallen"
    return "geltend"


# ---------------------------------------------------------------------------------------------------------------
# Text: XML -> lesbarer Klartext
# ---------------------------------------------------------------------------------------------------------------

_BLOCK = {"P", "Title", "Subtitle", "LA", "pre", "Ident", "Content", "text", "fussnoten", "Footnote", "TOC", "FnArea",
          "kommentar"}
_STUMM = {"Accolade", "QuoteR", "colspec", "Footnotes"}
# Trenner ohne eigenen Text (Tabulator, Füllpunkte, Formatwechsel): stehen für ein Leerzeichen, damit die Wörter
# links und rechts nicht verkleben ('SO2<Split/>520' -> 'SO2 520', 'z<Split/>= ' -> 'z = ').
_TRENNER = {"Split", "ABWFORMAT"}
# juris-Quellenangabe ohne <kommentar>, aber als abgeschlossene Klammer in <noindex>: '(Fundstelle: BGBl. I 2012, 1546)'
_FUNDSTELLE = re.compile(r"\(Fundstelle\b[^()]*(?:\([^()]*\)[^()]*)*\)")
# Platzhalter für Inhalte, die nur im Bundesgesetzblatt stehen ('(Inhalt: nicht darstellbares Muster, Fundstelle:
# ...)'): sie vertreten den Normtext und bleiben darin
_PLATZHALTER = re.compile(r"\W*(?:Inhalt\b|[^()]{0,40}nicht (?:darstellbar|erfa(?:ß|ss)t))", re.IGNORECASE)
_HOCH = str.maketrans("0123456789+-−()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁽⁾")


class _Schreiber:
    """Sammelt Text. Fließtext wird je Zeile auf einfache Leerzeichen gebracht; fertige Zeilen (Listen,
    Tabellen) bleiben mit ihrer Einrückung stehen."""

    def __init__(self) -> None:
        self.zeilen: list[str] = []
        self._teile: list[str] = []

    def text(self, s: str | None) -> None:
        if s:
            self._teile.append(s)

    def umbruch(self) -> None:
        if self._teile:
            z = _ws("".join(self._teile))
            if z:
                self.zeilen.append(z)
            self._teile = []

    def fertige_zeilen(self, zeilen: list[str]) -> None:
        self.umbruch()
        self.zeilen.extend(z.rstrip() for z in zeilen if z.strip())

    def ergebnis(self) -> list[str]:
        self.umbruch()
        return self.zeilen


@dataclass
class _Kontext:
    fussnotenzeichen: dict[str, str] = field(default_factory=dict)
    mit_verweisen: bool = True       # FnR als [*] ausgeben (im Titel nicht)
    # Redaktionelle juris-Notizen (<kommentar typ="Fundstelle|Hinweis|Stand">) sind kein Normtext. Im Text einer Norm
    # werden sie hier gesammelt und zu den Fußnoten gelegt; None: an Ort und Stelle ausgeben (Fußnoten, Titel).
    kommentare: list[str] | None = None


def _ist_notiz(el: ET.Element) -> bool:
    """juris-Notiz statt Normtext: <kommentar> (außer Platzhaltern) oder '(Fundstelle: ...)' in <noindex>."""
    inhalt = _ws("".join(el.itertext()))
    if el.tag == "kommentar":
        return not _PLATZHALTER.match(inhalt)
    return el.tag == "noindex" and bool(_FUNDSTELLE.fullmatch(inhalt))


def _kinder(el: ET.Element, w: _Schreiber, ctx: _Kontext) -> None:
    w.text(el.text)
    for c in el:
        _element(c, w, ctx)
        w.text(c.tail)


def _element(el: ET.Element, w: _Schreiber, ctx: _Kontext) -> None:
    tag = el.tag
    if tag == "BR":
        w.umbruch()
    elif tag in _STUMM:
        return
    elif tag in _TRENNER:
        w.text(" ")
    elif ctx.kommentare is not None and _ist_notiz(el):
        notiz = _ws(" ".join(_zeilen(el, ctx)))
        if notiz:
            ctx.kommentare.append(notiz)
    elif tag == "DL":
        _liste(el, w, ctx)
    elif tag == "table":
        _tabelle(el, w, ctx)
    elif tag == "FnR":
        if ctx.mit_verweisen:
            w.text(f"[{ctx.fussnotenzeichen.get(el.get('ID') or '', '*')}]")
    elif tag == "IMG":
        alt = _ws(el.get("alt"))
        w.text(f"[Bild: {alt}]" if alt else "[Bild]")
    elif tag == "FILE":
        w.text(f"[Datei: {_ws(el.get('SRC'))}]")
    elif tag == "SUP":
        s = _inline(el, ctx)
        s = s.translate(_HOCH) if re.fullmatch(r"[0-9+\-−()]+", s) else s
        roh = "".join(el.itertext())         # Leerraum am Rand ('<SUP>,&#160;</SUP>') bleibt ein Leerzeichen
        if s and roh[:1].isspace():
            s = " " + s
        if s and roh[-1:].isspace():
            s += " "
        w.text(s)
    elif tag == "FnArea" and not "".join(el.itertext()).strip():
        return                       # nur Verweise auf Fußnoten, die getrennt stehen
    elif tag in _BLOCK:
        w.umbruch()
        _kinder(el, w, ctx)
        w.umbruch()
    else:                            # B, I, U, F, SP, NB, small, SUB, noindex ...: Fließtext
        _kinder(el, w, ctx)


def _zeilen(el: ET.Element, ctx: _Kontext) -> list[str]:
    w = _Schreiber()
    _kinder(el, w, ctx)
    return w.ergebnis()


def _inline(el: ET.Element | None, ctx: _Kontext | None = None) -> str:
    if el is None:
        return ""
    return " ".join(_zeilen(el, ctx or _Kontext(mit_verweisen=False)))


def _liste(dl: ET.Element, w: _Schreiber, ctx: _Kontext) -> None:
    """DL/DT/DD -> '1. Text', Folgezeilen und Unterlisten eingerückt."""
    standard = {"dash": "–", "bullet": "•"}.get((dl.get("Type") or "").lower(), "")
    zeilen: list[str] = []
    marke: str | None = None
    if dl.text and dl.text.strip():
        zeilen.append(_ws(dl.text))
    for c in dl:
        if c.tag == "DT":
            marke = _inline(c, ctx) or standard
        elif c.tag == "DD":
            inhalt = _zeilen(c, ctx) or [""]
            m = marke if marke is not None else standard
            if m:
                zeilen.append(f"{m} {inhalt[0]}".rstrip())
                zeilen.extend(" " * (len(m) + 1) + z for z in inhalt[1:])
            else:
                zeilen.extend(inhalt)
            marke = None
        else:
            sub = _Schreiber()
            _element(c, sub, ctx)
            zeilen.extend(sub.ergebnis())
        if c.tail and c.tail.strip():
            zeilen.append(_ws(c.tail))
    w.fertige_zeilen(zeilen)


def _tabelle(tab: ET.Element, w: _Schreiber, ctx: _Kontext) -> None:
    """Tabellen grob als Text: Überschrift (<Title>) als eigene Zeile, dann je Zeile die Zellen mit ' | ' getrennt."""
    zeilen: list[str] = []
    gruppen = [c for c in tab if c.tag in ("Title", "tgroup")] or [tab]
    for tg in gruppen:
        if tg.tag == "Title":
            ueberschrift = " ".join(_zeilen(tg, ctx))
            if ueberschrift:
                zeilen.append(ueberschrift)
            continue
        teile = [t for t in tg if t.tag in ("thead", "tbody", "tfoot")] or [tg]
        for teil in teile:
            for row in teil.findall("row"):
                zellen = [" ".join(_zeilen(e, ctx)) for e in row.findall("entry")]
                if any(zellen):
                    zeilen.append(" | ".join(zellen).strip())
    w.fertige_zeilen(zeilen)


def _textdaten(norm: ET.Element) -> tuple[str, str]:
    """(Text, Fußnoten) einer Norm. Redaktionelle Notizen (<kommentar>) aus dem Text stehen vorn bei den Fußnoten."""
    td = norm.find("textdaten")
    if td is None:
        return "", ""
    text_el = td.find("text")
    fn_el = td.find("fussnoten")
    ctx = _Kontext()
    fussnoten: list[str] = []
    text = ""
    if text_el is not None:
        for f in text_el.iter("Footnote"):
            ctx.fussnotenzeichen[f.get("ID") or ""] = f.get("FnZ") or "*"
        ctx.kommentare = []
        text = "\n".join(_zeilen(text_el, ctx))
        if text.strip() or not ctx.kommentare:
            fussnoten.extend(ctx.kommentare)
            ctx.kommentare = None
        else:                                # die Notiz ist der einzige Inhalt: bleibt Text (sonst wäre er leer)
            ctx.kommentare = None
            text = "\n".join(_zeilen(text_el, ctx))
        for f in text_el.iter("Footnote"):
            inhalt = " ".join(_zeilen(f, ctx))
            if inhalt:
                fussnoten.append(f"[{f.get('FnZ') or '*'}] {inhalt}")
    if fn_el is not None:
        fussnoten.extend(_zeilen(fn_el, ctx))
    return text, "\n".join(fussnoten)


# ---------------------------------------------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------------------------------------------

@dataclass
class Norm:
    position: int            # Reihenfolge im Gesetz, ab 1
    enbez: str               # wie im XML: '§ 187', 'Art 1', 'Anlage 2', '(XXXX) §§ 3 bis 6', 'Eingangsformel'
    enbez_norm: str          # Suchschlüssel: '§187', 'art1', 'anlage2', '§3-6', in Mantelgesetzen 'art97§1'
    art: str                 # paragraph, artikel, anlage, eingangsformel, schlussformel, inhaltsuebersicht, ...
    status: str              # geltend, weggefallen, verschoben ('(jetzt § 650)'), zukuenftig
    titel: str
    gliederung: str          # 'Buch 1 Allgemeiner Teil > Abschnitt 4 Fristen, Termine'
    text: str                # Klartext, Absätze und Listenpunkte je Zeile
    fussnoten: str
    jurabk: str
    doknr: str
    builddate: str
    artikel: str = ""        # umgebender Artikel in Mantelgesetzen ('Art 97'), sonst leer


@dataclass
class Gesetz:
    jurabk: str = ""
    jurabk_weitere: list[str] = field(default_factory=list)
    amtabk: str = ""
    kurzue: str = ""
    langue: str = ""
    ausfertigung: str = ""
    fundstellen: list[str] = field(default_factory=list)
    standangaben: list[tuple[str, str]] = field(default_factory=list)
    hinweise: str = ""
    builddate: str = ""
    doknr: str = ""
    normen: list[Norm] = field(default_factory=list)

    @property
    def abk(self) -> str:
        """Abkürzung für Zitate: amtliche, sonst juristische ('AO' statt 'AO 1977', 'SGB X' statt 'SGB 10')."""
        return self.amtabk or self.jurabk

    @property
    def stand(self) -> str:
        return "; ".join(f"{t}: {k}" if t else k for t, k in self.standangaben if k or t)

    def namen(self) -> list[tuple[str, str]]:
        """Alle Namen des Gesetzes mit Herkunft, Grundlage der Alias-Tabelle."""
        out = [(self.jurabk, "jurabk")] if self.jurabk else []
        if self.amtabk:
            out.append((self.amtabk, "amtabk"))
        out += [(j, "jurabk_weitere") for j in self.jurabk_weitere]
        if self.kurzue:
            out.append((self.kurzue, "kurzue"))
        if self.langue:
            out.append((self.langue, "langue"))
        return out


# ---------------------------------------------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------------------------------------------

def _rahmen(g: Gesetz, md: ET.Element, norm: ET.Element) -> None:
    jur = [_ws(x.text) for x in md.findall("jurabk") if _ws(x.text)]
    g.jurabk = jur[0] if jur else g.jurabk
    g.jurabk_weitere = [j for j in jur[1:] if j != g.jurabk]
    g.amtabk = _ws(md.findtext("amtabk"))
    g.kurzue = _inline(md.find("kurzue"))
    g.langue = _inline(md.find("langue"))
    g.ausfertigung = _ws(md.findtext("ausfertigung-datum"))
    g.fundstellen = [_ws(f"{f.findtext('periodikum') or ''} {f.findtext('zitstelle') or ''}")
                     for f in md.findall("fundstelle")]
    g.standangaben = [(_ws(s.findtext("standtyp")), _ws(s.findtext("standkommentar")).rstrip(" ;"))
                      for s in md.findall("standangabe")]
    text, fn = _textdaten(norm)
    g.hinweise = "\n".join(t for t in (text, fn) if t)


def _label(bez: str, titel: str) -> str:
    if bez in ("", "-"):
        return titel
    return f"{bez} {titel}".strip()


@dataclass
class _Ebene:
    """Eine offene Gliederungseinheit (Buch, Abschnitt ...) auf dem Stapel."""
    kennzahl: str
    label: str
    bez: str
    fussnoten: str = ""      # Fußnoten einer Überschrift ohne eigene Normzeile, gehen an die Normen darunter
    genutzt: bool = False


def _geerbt(stapel: list[_Ebene]) -> list[str]:
    """Fußnoten der umgebenden Überschriften, z. B. 'Zu Abschnitt 2 ...: Dieser Abschnitt dient der Umsetzung ...'."""
    out: list[str] = []
    for e in stapel:
        if e.fussnoten:
            e.genutzt = True
            out += [f"Zu {e.label or e.kennzahl}: {z}" for z in e.fussnoten.split("\n")]
    return out


def _lese(wurzel: ET.Element) -> Gesetz:
    g = Gesetz(builddate=_datum(wurzel.get("builddate")), doknr=wurzel.get("doknr") or "")
    stapel: list[_Ebene] = []
    verwaist: list[str] = []                         # Überschriften-Fußnoten ohne Norm darunter -> Hinweise
    rahmen = False
    weitere: list[str] = []

    def weg(e: _Ebene) -> None:
        if e.fussnoten and not e.genutzt:
            verwaist.extend(_geerbt([e]))

    for norm in wurzel.findall("norm"):
        md = norm.find("metadaten")
        if md is None:
            continue
        jur = [_ws(x.text) for x in md.findall("jurabk") if _ws(x.text)]
        if not rahmen and md.find("langue") is not None:
            _rahmen(g, md, norm)
            rahmen = True
            continue
        if not g.jurabk and jur:
            g.jurabk = jur[0]
        weitere += [j for j in jur if j != g.jurabk and j not in weitere]

        enbez = _ws(md.findtext("enbez"))
        ge = md.find("gliederungseinheit")
        text, fussnoten = _textdaten(norm)
        bez = gtitel = ""
        if ge is not None:
            kz = _ws(ge.findtext("gliederungskennzahl"))
            bez = _ws(ge.findtext("gliederungsbez"))
            gtitel = _inline(ge.find("gliederungstitel"))
            while stapel and not (kz and kz.startswith(stapel[-1].kennzahl) and kz != stapel[-1].kennzahl):
                weg(stapel.pop())
            stapel.append(_Ebene(kz, _label(bez, gtitel), bez))

        if enbez:
            titel = _inline(md.find("titel"))
            pfad = [e.label for e in stapel]
            artikel = next((e.bez for e in reversed(stapel) if _ART_EINZEL.match(e.bez)), "")
            geerbt = _geerbt(stapel[:-1] if ge is not None else stapel)
        elif ge is not None and (text or _ART_EINZEL.match(bez)):
            # Überschrift mit eigenem Text (z. B. 'Art 3' eines Änderungsgesetzes) oder Artikel als Rahmen
            enbez, titel = bez, gtitel
            pfad = [e.label for e in stapel[:-1]]
            artikel = ""
            geerbt = _geerbt(stapel[:-1])
        else:
            if ge is not None and fussnoten:
                # Überschrift ohne eigenen Text, aber mit Fußnote (Amtlicher Hinweis, '(+++ Abschn. 5 ...+++)'):
                # die Fußnote gilt für alle Normen darunter
                stapel[-1].fussnoten = fussnoten
            continue
        schluessel = enbez_normal(enbez)
        if artikel and schluessel.startswith("§"):
            schluessel = enbez_normal(artikel) + schluessel
        else:
            artikel = ""
        g.normen.append(Norm(
            position=len(g.normen) + 1, enbez=enbez, enbez_norm=schluessel, art=_art_der_norm(enbez),
            status=_status(enbez, schluessel, titel, text), titel=titel, gliederung=" > ".join(p for p in pfad if p),
            text=text, fussnoten="\n".join(x for x in (fussnoten, *geerbt) if x), jurabk=jur[0] if jur else g.jurabk,
            doknr=norm.get("doknr") or "", builddate=_datum(norm.get("builddate")), artikel=artikel))
    for e in stapel:
        weg(e)
    if verwaist:
        g.hinweise = "\n".join(x for x in (g.hinweise, *verwaist) if x)
    g.jurabk_weitere += [j for j in weitere if j not in g.jurabk_weitere]
    return g


def lese_bytes(daten: bytes, quelle: str = "") -> Gesetz:
    if b"<!ENTITY" in daten:
        raise GiiFehler(f"{quelle}: eigene ENTITY-Deklaration, abgelehnt")
    try:
        wurzel = ET.fromstring(daten, parser=ET.XMLParser())
    except ET.ParseError as e:
        raise GiiFehler(f"{quelle}: kein gültiges XML ({e})") from e
    if wurzel.tag != "dokumente":
        raise GiiFehler(f"{quelle}: Wurzel ist <{wurzel.tag}>, erwartet <dokumente>")
    return _lese(wurzel)


def lese_datei(pfad: str | Path) -> Gesetz:
    p = Path(pfad)
    return lese_bytes(p.read_bytes(), str(p))


def lese_dateien(pfade: list[str | Path]) -> Gesetz:
    """Mehrere XML-Dateien eines Gesetzes (selten) zu einem zusammenführen."""
    if not pfade:
        raise GiiFehler("keine Datei")
    g = lese_datei(pfade[0])
    for p in pfade[1:]:
        weiteres = lese_datei(p)
        for n in weiteres.normen:
            n.position = len(g.normen) + 1
            g.normen.append(n)
        g.builddate = max(g.builddate, weiteres.builddate)
    return g


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="gii-norm-XML lesen und als Text ausgeben")
    ap.add_argument("datei", type=Path)
    ap.add_argument("--enbez", help="nur diese Norm, z. B. '§ 41'")
    args = ap.parse_args(argv)
    g = lese_datei(args.datei)
    print(f"{g.abk} | {g.langue} | Ausfertigung {g.ausfertigung} | {g.stand} | Build {g.builddate}")
    for n in g.normen:
        if args.enbez and enbez_normal(args.enbez) not in (n.enbez_norm, enbez_normal(n.enbez)):
            continue
        print(f"\n[{n.position}] {n.enbez} {n.titel} ({n.art}, {n.status}) {{{n.enbez_norm}}}")
        if n.gliederung:
            print(f"  Gliederung: {n.gliederung}")
        print(n.text)
        if n.fussnoten:
            print("  Fußnoten: " + n.fussnoten.replace("\n", "\n  "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
