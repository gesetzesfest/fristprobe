"""Tests für die Wissensbasis (pruefki/wissen): Parser, Index, Abruf, Anbindung an den Benchmark.

Fixtures: drei kleine echte Dateien von gesetze-im-internet.de (amtliche Werke, § 5 UrhG) unter tests/fixtures/gii/
(1-DM-Goldmünzgesetz, WDNeuOG, EURHGAusnahmV) mit ihrem Eintrag aus stand.json. Für Aliase und Absätze kommt ein
erfundenes Kurzgesetz dazu ("SGB 10"/"SGB X", Text ausdrücklich erfunden). Keine Personendaten.

Die Klasse EchteDatenbank läuft nur, wenn daten/wissen.sqlite gebaut ist (python3.12 -m pruefki.wissen.index --neu).
"""

import io
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

WURZEL = Path(__file__).resolve().parents[1]
FRISTEN = WURZEL / "benchmark" / "fristen"
for p in (str(WURZEL), str(FRISTEN)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pruefki.wissen import abruf, gii, index  # noqa: E402
from pruefki.wissen.abruf import (Wissensbasis, WissensbasisFehler, absaetze, absatz_text, fts_anfrage,  # noqa: E402
                                  im_bereich, nummern, saetze_hoechstens, suchworte, zerlege)

FIXTURES = WURZEL / "tests" / "fixtures" / "gii"
ECHTE_DB = WURZEL / "daten" / "wissen.sqlite"


def _fixture(kuerzel: str) -> gii.Gesetz:
    return gii.lese_dateien(sorted((FIXTURES / "xml" / kuerzel).glob("*.xml")))


def _norm(g: gii.Gesetz, enbez: str) -> gii.Norm:
    return next(n for n in g.normen if n.enbez == enbez)


def _xml(jurabk: str, normen: str, amtabk: str = "", langue: str = "Erfundenes Testgesetz",
         builddate: str = "20260101120000") -> str:
    amt = f"<amtabk>{amtabk}</amtabk>" if amtabk else ""
    return (f'<?xml version="1.0" encoding="UTF-8" ?><dokumente builddate="{builddate}" doknr="TEST">'
            f'<norm builddate="{builddate}" doknr="TEST"><metadaten><jurabk>{jurabk}</jurabk>{amt}'
            f'<ausfertigung-datum manuell="ja">2020-01-01</ausfertigung-datum><langue>{langue}</langue>'
            f'<standangabe checked="ja"><standtyp>Stand</standtyp><standkommentar>erfunden für Tests'
            f'</standkommentar></standangabe></metadaten></norm>{normen}</dokumente>')


def _paragraph(jurabk: str, enbez: str, titel: str, text_xml: str) -> str:
    t = f'<titel format="parat">{titel}</titel>' if titel else ""
    return (f'<norm builddate="20260101120000" doknr="TEST{enbez}"><metadaten><jurabk>{jurabk}</jurabk>'
            f'<enbez>{enbez}</enbez>{t}</metadaten><textdaten><text format="XML"><Content>{text_xml}</Content>'
            f'</text></textdaten></norm>')


def _gliederung(jurabk: str, kz: str, bez: str, titel: str, fussnote: str = "") -> str:
    fn = (f'<textdaten><fussnoten format="XML"><Content><P>{fussnote}</P></Content></fussnoten></textdaten>'
          if fussnote else "")
    return (f'<norm builddate="20260101120000" doknr="TESTG{kz}"><metadaten><jurabk>{jurabk}</jurabk>'
            f'<gliederungseinheit><gliederungskennzahl>{kz}</gliederungskennzahl><gliederungsbez>{bez}'
            f'</gliederungsbez><gliederungstitel>{titel}</gliederungstitel></gliederungseinheit></metadaten>{fn}'
            '</norm>')


# Erfundenes Kurzgesetz unter dem Namen "SGB 10" / "SGB X" (kein echter Gesetzestext)
SGB_TEST = _xml("SGB 10", "".join([
    _paragraph("SGB 10", "§ 37", "Bekanntgabe (erfunden)",
               "<P>(1) Erfundener Satz eins.</P><P>(2) Ein Testbescheid gilt am vierten Tag nach der Aufgabe zur "
               "Post als bekannt gegeben.</P>"),
    _paragraph("SGB 10", "§ 38", "", "<P>-</P>"),
]), amtabk="SGB X", langue="Erfundenes Zehntes Testbuch")
# Erfundenes Gesetz mit Einführungsgesetz (juris-Schreibweise XyzGEG -> zitiert EGXyzG)
XYZ_TEST = _xml("XyzG", _paragraph("XyzG", "§ 1", "Zweck", "<P>Erfundener Text.</P>"))
XYZ_EG_TEST = _xml("XyzGEG", _paragraph("XyzGEG", "Art 1", "", "<P>Erfundener Einführungstext.</P>"))


def baue_quelle(ziel: Path) -> Path:
    """Fixtures plus erfundene Testgesetze in einen Quellordner wie daten/bund."""
    quelle = ziel / "bund"
    shutil.copytree(FIXTURES, quelle)
    stand = json.loads((quelle / "stand.json").read_text("utf-8"))
    for kuerzel, xml in (("sgb_test", SGB_TEST), ("xyzg", XYZ_TEST), ("xyzgeg", XYZ_EG_TEST)):
        (quelle / "xml" / kuerzel).mkdir(parents=True)
        (quelle / "xml" / kuerzel / "TEST.xml").write_text(xml, "utf-8")
        stand[kuerzel] = {"titel": "erfunden", "url": f"https://example.invalid/{kuerzel}/xml.zip", "etag": "\"1\"",
                          "dateien": ["TEST.xml"], "geladen": "2026-10-15T00:00:00+00:00"}
    (quelle / "stand.json").write_text(json.dumps(stand, ensure_ascii=False), "utf-8")
    return quelle


def _still(*_a, **_k):
    return None


# ---------------------------------------------------------------------------------------------------------------


class Parser(unittest.TestCase):
    def test_metadaten(self):
        g = _fixture("1-dm-goldm_nzg")
        self.assertEqual(g.jurabk, "1-DM-GoldmünzG")
        self.assertEqual(g.abk, "1-DM-GoldmünzG")
        self.assertIn("Ausprägung einer 1-DM-Goldmünze", g.langue)
        self.assertNotIn("\n", g.langue)
        self.assertEqual(g.ausfertigung, "2000-12-27")
        self.assertEqual(g.builddate, "2026-05-06T17:56:47")
        self.assertEqual(g.fundstellen, ["BGBl I 2000, 2045"])
        self.assertIn("Textnachweis ab: 31.12.2000", g.hinweise)
        e = _fixture("eurhgausnahmv")
        self.assertEqual((e.amtabk, e.kurzue), ("EURHGAusnahmV", "EU-RHG-Ausnahmeverordnung"))
        self.assertIn("Zuletzt geändert durch Art. 1 V v. 14.4.2026 I Nr. 102", e.stand)

    def test_normen_gliederung_position(self):
        g = _fixture("1-dm-goldm_nzg")
        self.assertEqual([n.enbez for n in g.normen], [f"§ {i}" for i in range(1, 20)])
        self.assertEqual([n.position for n in g.normen], list(range(1, 20)))
        self.assertEqual(_norm(g, "§ 1").gliederung, "Erster Abschnitt Ausgabe einer 1-DM Goldmünze")
        self.assertEqual(_norm(g, "§ 10").gliederung, "Zweiter Abschnitt Stiftung \"Geld und Währung\"")
        self.assertEqual(_norm(g, "§ 19").gliederung, "Dritter Abschnitt")
        self.assertEqual(_norm(g, "§ 19").titel, "Inkrafttreten")
        self.assertTrue(all(n.art == "paragraph" and n.status == "geltend" for n in g.normen))
        self.assertEqual(_norm(g, "§ 7").enbez_norm, "§7")

    def test_absaetze_und_listen_als_zeilen(self):
        g = _fixture("1-dm-goldm_nzg")
        self.assertEqual([z[:3] for z in _norm(g, "§ 2").text.split("\n")], ["(1)", "(2)", "(3)"])
        zeilen = _norm(g, "§ 11").text.split("\n")
        self.assertEqual(zeilen[1], "(2) Der Erfüllung dieses Zwecks dienen insbesondere:")
        self.assertEqual(zeilen[2], "1. die Durchführung und Finanzierung von Forschungsprojekten;")
        self.assertTrue(zeilen[4].startswith("3. die Förderung des wissenschaftlichen Meinungsaustauschs"))
        self.assertNotIn("  ", _norm(g, "§ 15").text)

    def test_anlage_tabelle_fussnoten(self):
        e = _fixture("eurhgausnahmv")
        self.assertEqual(e.normen[0].art, "eingangsformel")
        p1 = _norm(e, "§ 1").text.split("\n")
        self.assertTrue(p1[1].startswith("1. abweichend von § 9 Absatz 1 Satz 1 Nummer 3"))
        self.assertTrue(p1[-1].startswith("werden, soweit sein Gehalt"))
        anl = _norm(e, "Anlage")
        self.assertEqual((anl.art, anl.enbez_norm, anl.titel), ("anlage", "anlage", "(zu § 1)"))
        self.assertIn("Wirkstoff | Code[*] | Erzeugnisgruppe[*] | Rückstandshöchstgehalt mg/kg", anl.text)
        self.assertIn("Difluoressigsäure | 0700000 | Hopfen | 3", anl.text)
        # juris-Notiz <kommentar typ="Fundstelle"> ist kein Normtext: steht vorn bei den Fußnoten
        self.assertNotIn("Fundstelle", anl.text)
        self.assertEqual(anl.fussnoten, "(Fundstelle: BGBl. 2026 I Nr. 102, S. 1)\n[*] Code und Erzeugnisgruppe im "
                                        "Sinne des Anhangs I der Verordnung (EG) Nr. 396/2005.")
        self.assertNotIn("Anhangs I", anl.text)

    def test_mantelgesetz_artikel_und_platzhalter(self):
        w = _fixture("wdneuog")
        self.assertEqual([n.enbez for n in w.normen],
                         ["Eingangsformel", "Art VIII", "(XXXX) §§ 1 bis 8", "Art IX", "Art X"])
        viii = _norm(w, "Art VIII")
        self.assertEqual((viii.art, viii.status, viii.enbez_norm), ("artikel", "weggefallen", "artviii"))
        platz = _norm(w, "(XXXX) §§ 1 bis 8")
        self.assertEqual((platz.enbez_norm, platz.status, platz.artikel, platz.gliederung),
                         ("artviii§1-8", "weggefallen", "Art VIII", "Art VIII"))
        x = _norm(w, "Art X")
        self.assertEqual((x.titel, x.text, x.status), ("Inkrafttreten", "Dieses Gesetz tritt drei Monate nach "
                                                                         "Verkündung in Kraft.", "geltend"))
        self.assertTrue(_norm(w, "Art IX").text.startswith("(3) Sofern in diesem Gesetz"))
        self.assertIn("Geändert durch Art. 2 G v. 16.8.2001 I 2093", w.stand)

    def test_enbez_normal(self):
        f = gii.enbez_normal
        self.assertEqual(f("§ 187"), "§187")
        self.assertEqual(f("§ 573c"), "§573c")
        self.assertEqual(f("Art 1"), "art1")
        self.assertEqual(f("Artikel 3"), "art3")
        self.assertEqual(f("Anlage 2a"), "anlage2a")
        self.assertEqual(f("Anlage"), "anlage")
        self.assertEqual(f("(XXXX) §§ 3 bis 6"), "§3-6")
        self.assertEqual(f("(XXXX) §§ 26 u. 27"), "§26,27")
        self.assertEqual(f("(XXXX) Art 5 bis Art 11"), "art5-11")
        self.assertEqual(f("§ 1.01"), "§1.01")
        self.assertEqual(f("Schlußformel"), "schlussformel")
        self.assertEqual(f("(XXXX)"), "")

    def test_status_sonderfaelle(self):
        g = gii.lese_bytes(_xml("TestG", "".join([
            _paragraph("TestG", "§ 1", "", "<P>-</P>"),
            _paragraph("TestG", "§ 2", "(jetzt § 9)", "<P/>"),
            _paragraph("TestG", "§ 3", "(zukünftig in Kraft)", "<P/>"),
            _paragraph("TestG", "§ 4", "(weggefallen)", "<P/>"),
            _paragraph("TestG", "§ 5", "Inhalt", "<P>Text mit m<SUP>2</SUP> und <B>fett</B><BR/>neue Zeile</P>"),
        ])).encode())
        self.assertEqual([n.status for n in g.normen], ["weggefallen", "verschoben", "zukuenftig", "weggefallen",
                                                        "geltend"])
        self.assertEqual(g.normen[4].text, "Text mit m² und fett\nneue Zeile")

    def test_tabellentitel_trenner_notizen_gliederungsfussnoten(self):
        g = gii.lese_bytes(_xml("TestG", "".join([
            _gliederung("TestG", "010", "Abschnitt 1", "Allgemeines", "(+++ Abschn. 1: Zur Anwendung vgl. § 9 +++)"),
            _paragraph("TestG", "§ 1", "Werte",
                       '<P>(1) SO<SUB>2</SUB><Split Leader="0"/>520 und um<Split Leader="0"/>30 vom Hundert</P>'
                       '<P>(2) Bild<ABWFORMAT typ="E"/>(Inhalt: nicht darstellbar) und z<Split Leader="0"/>= 1</P>'
                       '<P>(3) Quoten<SUP>1</SUP><SUP>,&#160;</SUP><SUP>2</SUP></P>'),
            _paragraph("TestG", "§ 2", "Tabelle",
                       '<P>Text<noindex><kommentar typ="Fundstelle">(Fundstelle: BGBl. I 2020, 1)</kommentar>'
                       '</noindex></P><table><Title>Beträge in Euro</Title><tgroup cols="2"><tbody><row>'
                       '<entry>A</entry><entry>1</entry></row></tbody></tgroup></table>'
                       '<P><noindex>(Fundstelle: BGBl. I 2020, 2)</noindex></P>'
                       '<P><noindex>Diese Verordnung dient der Umsetzung (erfunden).</noindex></P>'),
            _gliederung("TestG", "020", "Abschnitt 2", "Ohne Fußnote"),
            _paragraph("TestG", "§ 3", "", "<P>Erfundener Text.</P>"),
            _gliederung("TestG", "030", "Abschnitt 3", "Leer", "Amtlicher Hinweis: erfunden."),
        ])).encode())
        p1, p2, p3 = g.normen
        self.assertEqual(p1.text.split("\n"), ["(1) SO2 520 und um 30 vom Hundert",
                                                "(2) Bild (Inhalt: nicht darstellbar) und z = 1", "(3) Quoten¹, ²"])
        self.assertEqual(p2.text, "Text\nBeträge in Euro\nA | 1\nDiese Verordnung dient der Umsetzung (erfunden).")
        self.assertEqual(p2.fussnoten.split("\n"), [
            "(Fundstelle: BGBl. I 2020, 1)", "(Fundstelle: BGBl. I 2020, 2)",
            "Zu Abschnitt 1 Allgemeines: (+++ Abschn. 1: Zur Anwendung vgl. § 9 +++)"])
        self.assertEqual(p1.fussnoten, "Zu Abschnitt 1 Allgemeines: (+++ Abschn. 1: Zur Anwendung vgl. § 9 +++)")
        self.assertEqual((p3.fussnoten, p3.gliederung), ("", "Abschnitt 2 Ohne Fußnote"))
        self.assertIn("Zu Abschnitt 3 Leer: Amtlicher Hinweis: erfunden.", g.hinweise)   # ohne Norm darunter

    def test_entity_und_kaputtes_xml_abgelehnt(self):
        boese = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
                 b"<dokumente>&b;</dokumente>")
        with self.assertRaises(gii.GiiFehler):
            gii.lese_bytes(boese)
        with self.assertRaises(gii.GiiFehler):
            gii.lese_bytes(b"<dokumente><norm></dokumente>")
        with self.assertRaises(gii.GiiFehler):
            gii.lese_bytes(b"<html/>")

    def test_kein_netz_beim_parsen(self):
        # Die Dateien verweisen per DOCTYPE auf eine DTD im Netz; geladen werden darf sie nicht.
        def verboten(*a, **k):
            raise AssertionError("Netzzugriff beim Parsen")
        with mock.patch.object(socket, "socket", verboten), mock.patch("urllib.request.urlopen", verboten):
            g = _fixture("1-dm-goldm_nzg")
        self.assertEqual(len(g.normen), 19)


class Zitate(unittest.TestCase):
    def _s(self, zitat):
        return [(v.schluessel, v.gesetz[0] if v.gesetz else None, v.absatz) for v in zerlege(zitat)]

    def test_schreibweisen(self):
        self.assertEqual(self._s("§ 187 BGB"), [("§187", "BGB", None)])
        self.assertEqual(self._s("§187 Abs. 1 BGB"), [("§187", "BGB", "1")])
        self.assertEqual(self._s("Art. 1 GG"), [("art1", "GG", None)])
        self.assertEqual(self._s("§ 37 Abs. 2 SGB X"), [("§37", "SGB X", "2")])
        self.assertEqual(self._s("§ 84 SGG"), [("§84", "SGG", None)])
        self.assertEqual(self._s("Art. 97 § 1 EGAO"), [("art97§1", "EGAO", None)])
        self.assertEqual(self._s("§ 999 BGB-erfunden"), [("§999", "BGB-erfunden", None)])

    def test_listen_bereiche_verkettung(self):
        self.assertEqual(self._s("§§ 187, 188 BGB"), [("§187", "BGB", None), ("§188", "BGB", None)])
        self.assertEqual([v.schluessel for v in zerlege("§§ 187 bis 190 BGB")], ["§187", "§188", "§189", "§190"])
        self.assertEqual(self._s("§ 57 Abs. 2 VwGO i. V. m. § 222 ZPO"), [("§57", "VwGO", "2"), ("§222", "ZPO", None)])
        self.assertEqual(self._s("§ 41 Abs. 2, 3 VwVfG"), [("§41", "VwVfG", "2")])
        v = zerlege("§ 122 Abs. 2 Nr. 1 AO")[0]
        self.assertEqual((v.absatz, v.nr), ("2", "1"))
        self.assertEqual(zerlege("Die Frist nach § 41 VwVfG beträgt einen Monat.")[0].gesetz[-1], "VwVfG")
        self.assertEqual(zerlege("kein Zitat"), [])

    def test_bereiche_und_absaetze(self):
        self.assertTrue(im_bereich("§4", "§3-6"))
        self.assertFalse(im_bereich("§4a", "§3-6"))
        self.assertTrue(im_bereich("§16b", "§16a-16c"))
        self.assertTrue(im_bereich("§27", "§26,27"))
        self.assertTrue(im_bereich("artviii§2", "artviii§1-8"))
        self.assertFalse(im_bereich("§2", "artviii§1-8"))
        text = "(1) Eins.\n(2) Zwei\n1. Punkt\n(2a) Zwei a."
        self.assertEqual(absaetze(text), ["1", "2", "2a"])
        self.assertEqual(absatz_text(text, "2"), "(2) Zwei\n1. Punkt")
        self.assertIsNone(absatz_text(text, "3"))

    def test_fts_anfrage(self):
        self.assertEqual(fts_anfrage("Bekanntgabe vierter Tag"), '"bekanntgab"* AND "viert"* AND "tag"*')
        self.assertEqual(fts_anfrage("Frist nach § 187", "OR"), '"frist"* OR "187"')
        self.assertEqual(fts_anfrage("Mietwohnung", synonyme={"mietwohnung": ["wohnraum", "agentur für arbeit"]}),
                         '("mietwohnung"* OR "wohnraum"* OR "agentur für arbeit")')
        # Schutzgrenzen: Einzelzeichen fallen weg, lange Texte werden auf die 8 längsten Wörter gekürzt
        self.assertEqual(suchworte("a b c d e f 1 2"), [])
        self.assertEqual(suchworte("Wie lange habe ich Zeit für einen Widerspruch?"), ["zeit", "widerspruch"])
        lang = suchworte(" ".join(f"Testwort{i:03d}" + "x" * (i % 5) for i in range(300)))
        self.assertEqual(len(lang), 8)
        self.assertTrue(all(w.endswith("xxxx") for w in lang))

    def test_parallelzitate(self):
        self.assertEqual(self._s("§§ 41 Abs. 2 VwVfG, 37 Abs. 2 SGB X, 122 Abs. 2 AO"),
                         [("§41", "VwVfG", "2"), ("§37", "SGB X", "2"), ("§122", "AO", "2")])
        self.assertEqual(self._s("§§ 41 VwVfG, 999 SGB X"), [("§41", "VwVfG", None), ("§999", "SGB X", None)])
        self.assertEqual(self._s("§ 41 VwVfG sowie 999 erfundenG"),
                         [("§41", "VwVfG", None), ("§999", "erfundenG", None)])
        self.assertEqual(self._s("Art. 19 GG und 999 BGB"), [("art19", "GG", None), ("art999", "BGB", None)])
        self.assertEqual(self._s("§ 41 VwVfG, 37, 39 SGB X"),
                         [("§41", "VwVfG", None), ("§37", "SGB X", None), ("§39", "SGB X", None)])
        # Zahlen ohne folgenden Gesetzesnamen sind keine Normen
        self.assertEqual(self._s("§ 41 VwVfG, 3 Wochen nach Zugang"), [("§41", "VwVfG", None)])
        self.assertEqual(self._s("§ 41 VwVfG, 2026 BGBl. I S. 5"), [("§41", "VwVfG", None)])

    def test_roemische_absaetze_und_schreibweisen(self):
        self.assertEqual(self._s("§ 41 II VwVfG"), [("§41", "VwVfG", "2")])
        self.assertEqual(self._s("Art 19 IV GG"), [("art19", "GG", "4")])
        self.assertEqual(self._s("§ 37 II SGB X"), [("§37", "SGB X", "2")])
        v = zerlege("§ 41 II 1 VwVfG")[0]
        self.assertEqual((v.absatz, v.satz), ("2", "1"))
        self.assertEqual(self._s("§ 1 II. BV"), [("§1", "II BV", None)])          # 'II.' gehört zum Namen
        self.assertEqual(self._s("§ 31 SGB II"), [("§31", "SGB II", None)])
        self.assertEqual(self._s("§ 41 abs. 2 vwvfg"), [("§41", "vwvfg", "2")])
        self.assertEqual(self._s("art. 19 abs. 4 gg"), [("art19", "gg", "4")])
        self.assertEqual(self._s("ART. 19 GG"), [("art19", "GG", None)])
        self.assertEqual(self._s("§ 41 ABS. 2 VWVFG"), [("§41", "VWVFG", "2")])
        self.assertEqual(zerlege("§ 9 abs 1 nr 4 EStG")[0].nr, "4")
        self.assertEqual(self._s("§41VwVfG"), [("§41", "VwVfG", None)])
        self.assertEqual(self._s("§ 41 a VwVfG"), [("§41a", "VwVfG", None)])
        self.assertEqual(self._s("Paragraf 41 VwVfG"), [("§41", "VwVfG", None)])
        self.assertEqual(self._s("Paragraphen 41, 43 VwVfG"), [("§41", "VwVfG", None), ("§43", "VwVfG", None)])
        self.assertEqual(self._s("Anlage BKatV"), [("anlage", "BKatV", None)])
        self.assertEqual(zerlege("Anlage BKatV")[0].text, "Anlage BKatV")
        self.assertEqual(zerlege("die Anlage des Bescheids"), [])
        b = zerlege("§§ 187 bis 999 BGB")
        self.assertEqual((len(b), b[-2].schluessel, b[-1].schluessel), (202, "§387", "§999"))
        self.assertIn("gekürzt", b[-1].hinweis)

    def test_saetze_und_nummern(self):
        self.assertEqual(saetze_hoechstens("(1) Eins. Zwei."), 2)
        self.assertEqual(saetze_hoechstens("(2) Ohne Punkt am Ende"), 1)
        self.assertEqual(nummern("(2) Liste:\n1. eins;\n2a. zwei\n   3. drei."), ["1", "2a", "3"])


class Index(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.quelle = baue_quelle(Path(cls.tmp.name))
        cls.db = Path(cls.tmp.name) / "wissen.sqlite"
        cls.erg = index.baue_neu(cls.quelle, cls.db, log=_still)
        cls.wb = Wissensbasis(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.wb.schliessen()
        cls.tmp.cleanup()

    def test_zahlen_und_meta(self):
        self.assertEqual(self.erg["neu"], 6)
        self.assertEqual(self.erg["fehler"], [])
        k = index.kennzahlen(self.db)
        self.assertEqual(k["gesetze"], 6)
        self.assertEqual(k["normen"], 19 + 5 + 4 + 2 + 1 + 1)
        meta = self.wb.meta()
        self.assertEqual(meta["schema_version"], index.SCHEMA_VERSION)
        self.assertIn("§ 5 UrhG", meta["quelle"])
        self.assertFalse(self.db.with_name(self.db.name + ".neu").exists())

    def test_herkunft_je_zeile(self):
        con = sqlite3.connect(self.db)
        url, stand, bd = con.execute("SELECT quelle_url, stand, builddate FROM normen WHERE zitat = '§ 2 EURHGAusnahmV'"
                                     ).fetchone()
        g = con.execute("SELECT titel, ausfertigung, quelle_url, builddate, geladen, etag FROM gesetze "
                        "WHERE kuerzel = 'eurhgausnahmv'").fetchone()
        con.close()
        self.assertEqual(url, "https://www.gesetze-im-internet.de/eurhgausnahmv/xml.zip")
        self.assertIn("Zuletzt geändert durch Art. 1 V v. 14.4.2026 I Nr. 102", stand)
        self.assertIn("Build 2026-05-06", stand)
        self.assertEqual(bd, "2026-05-06T17:46:49")
        self.assertEqual(g[1:], ("2010-04-14", url, "2026-05-06T17:46:49", "2026-10-14T21:36:45+00:00",
                                 '"72d-651281264e1a2"'))

    def test_aliase(self):
        for name in ("SGB X", "SGB 10", "SGB10", "sgb x", "Erfundenes Zehntes Testbuch"):
            self.assertEqual(self.wb.gesetz_kuerzel(name), "sgb_test", name)
        self.assertIsNone(self.wb.gesetz_kuerzel("SGB XI"))
        self.assertEqual(self.wb.gesetz_kuerzel("EGXyzG"), "xyzgeg")
        self.assertEqual(self.wb.gesetz_kuerzel("XyzG"), "xyzg")
        self.assertEqual(self.wb.gesetz_kuerzel("EU-RHG-Ausnahmeverordnung"), "eurhgausnahmv")
        self.assertEqual(self.wb.gesetz_kuerzel("1-DM-GoldmuenzG"), "1-dm-goldm_nzg")
        self.assertEqual(index.varianten("SGB 9 2018"), ["SGB 9", "SGB IX", "Neuntes Buch Sozialgesetzbuch",
                                                         "Sozialgesetzbuch Neuntes Buch"])
        self.assertIn("SGB 2", index.varianten("SGB II"))

    def test_norm_mit_absatz_quelle_stand(self):
        t = self.wb.norm("§ 37 Abs. 2 SGB X")
        self.assertEqual(t.zitat, "§ 37 SGB X")
        self.assertIn("vierten Tag", t.absatz_text)
        self.assertNotIn("Satz eins", t.absatz_text)
        self.assertEqual(t.quelle_url, "https://example.invalid/sgb_test/xml.zip")
        self.assertIn("erfunden für Tests", t.stand)
        self.assertEqual(self.wb.norm("SGB X", "37").zitat, "§ 37 SGB X")
        self.assertEqual(self.wb.norm("1-DM-GoldmünzG", "§ 11").titel, "Stiftungszweck")
        self.assertEqual(self.wb.norm("Art. X WDNeuOG").titel, "Inkrafttreten")
        self.assertIsNone(self.wb.norm("§ 99 SGB X"))
        self.assertEqual(self.wb.norm("Art. VIII § 4 WDNeuOG").status, "weggefallen")

    def test_existiert(self):
        wb = self.wb
        self.assertTrue(wb.existiert("§ 2 1-DM-GoldmünzG"))
        self.assertTrue(wb.existiert("§ 37 Abs. 2 SGB X"))
        self.assertFalse(wb.existiert("§ 37 Abs. 9 SGB X"))          # Absatz gibt es nicht
        self.assertFalse(wb.existiert("§ 38 SGB X"))                 # weggefallen
        self.assertTrue(wb.existiert("§ 38 SGB X", streng=False))
        self.assertFalse(wb.existiert("§ 99 SGB X"))
        self.assertFalse(wb.existiert("§ 37 SGB X-erfunden"))
        self.assertFalse(wb.existiert("Art. VIII § 4 WDNeuOG"))
        self.assertFalse(wb.existiert("ohne Norm"))
        self.assertEqual([e["ergebnis"] for e in wb.pruefe("§ 37 SGB X und § 99 SGB X")], ["ok", "norm_fehlt"])
        self.assertIs(wb.existiert_schluessel("37", "SGBX"), True)
        self.assertIs(wb.existiert_schluessel("99", "SGBX"), False)
        self.assertIsNone(wb.existiert_schluessel("31", "BAYVWVFG"))

    def test_gesetzesnamen_gebeugt_und_landesrecht(self):
        wb = self.wb
        for zitat in ("§ 37 Abs. 2 des Zehnten Buches Sozialgesetzbuch", "§ 37 Zehntes Buch Sozialgesetzbuch (SGB X)",
                      "§ 37 SGB-X", "§ 37 II SGB X", "§ 37 SGB X gilt entsprechend"):
            self.assertTrue(wb.existiert(zitat), zitat)
        for zitat in ("§ 37 SGB X NRW", "§ 37 SGB X Bayern", "§ 37 SGB X-erfunden"):
            self.assertFalse(wb.existiert(zitat), zitat)
            self.assertEqual(wb.pruefe(zitat)[0]["ergebnis"], "gesetz_unbekannt", zitat)

    def test_satz_und_nummer(self):
        wb = self.wb
        self.assertTrue(wb.existiert("§ 37 Abs. 2 Satz 1 SGB X"))
        self.assertEqual(wb.pruefe("§ 37 Abs. 2 Satz 2 SGB X")[0]["ergebnis"], "satz_fehlt")
        self.assertTrue(wb.existiert("§ 37 Abs. 2 Satz 2 SGB X", streng=False))
        self.assertEqual(wb.pruefe("§ 37 Abs. 2 Nr. 1 SGB X")[0]["ergebnis"], "nr_fehlt")   # Absatz ohne Liste
        self.assertTrue(wb.existiert("§ 11 Abs. 2 Nr. 3 1-DM-GoldmünzG"))
        self.assertEqual(wb.pruefe("§ 11 Abs. 2 Nr. 9 1-DM-GoldmünzG")[0]["ergebnis"], "nr_fehlt")
        self.assertEqual(wb.pruefe("§§ 37, 99 SGB X")[1]["ergebnis"], "norm_fehlt")
        self.assertEqual(wb.norm("EGXyzG", "1").zitat, "Art 1 XyzGEG")          # nackte Zahl, Gesetz mit Artikeln

    def test_wortteile(self):
        z = index.Zerleger({"frist", "klage", "berufungsfrist", "notfrist", "kündigungsschutzklage"},
                           {"berufung", "kündigungsschutz", "frist", "klage", "not"})
        self.assertEqual(z.teile("Berufungsfrist"), ("frist",))
        self.assertEqual(z.teile("Kündigungsschutzklage"), ("klage",))
        self.assertEqual(z.teile("Notfrist"), ())                                  # vorderer Teil zu kurz
        self.assertEqual(z.wortteile("Die Berufungsfrist", "erforderlichen Notfrist"), "frist")
        zaehler = index.Wortzaehler()
        zaehler.zaehle("Frist Frist Frist Frist Frist frist", "enden Enden enden")
        self.assertEqual(zaehler.nomen(), {"frist"})
        # Ende zu Ende: erfundenes Gesetz, in dem § 6 'Frist' nur als Teil von 'Berufungsfrist' enthält
        absatz = "<P>Die Frist beginnt. Die Berufung ist zulässig. Die Berufungsfrist läuft.</P>"
        xml = _xml("FristG", "".join(_paragraph("FristG", f"§ {i}", "", absatz) for i in range(1, 6))
                   + _paragraph("FristG", "§ 6", "Erfunden", "<P>Eine Berufungsfrist ist erfunden.</P>"))
        with tempfile.TemporaryDirectory() as tmp:
            quelle = Path(tmp) / "bund"
            (quelle / "xml" / "fristg").mkdir(parents=True)
            (quelle / "xml" / "fristg" / "TEST.xml").write_text(xml, "utf-8")
            stand = {"fristg": {"dateien": ["TEST.xml"], "etag": '"1"'}}
            (quelle / "stand.json").write_text(json.dumps(stand), "utf-8")
            db = Path(tmp) / "w.sqlite"
            self.assertEqual(index.baue_neu(quelle, db, log=_still)["normen_mit_wortteilen"], 6)
            wb = Wissensbasis(db)
            try:
                self.assertEqual(wb.norm("§ 6 FristG").text, "Eine Berufungsfrist ist erfunden.")
                self.assertIn("§ 6 FristG", [t.zitat for t in wb.suche("Frist")])
                self.assertEqual(len(wb.suche("wortteile : frist", roh=True)), 6)
            finally:
                wb.schliessen()

    def test_datei_kaputt_oder_fremd(self):
        with tempfile.TemporaryDirectory() as tmp:
            leer = Path(tmp) / "leer.sqlite"
            leer.write_bytes(b"")
            zufall = Path(tmp) / "zufall.sqlite"
            zufall.write_bytes(bytes(range(256)) * 16)
            alt = Path(tmp) / "alt.sqlite"
            shutil.copy(self.db, alt)
            con = sqlite3.connect(alt)
            con.execute("UPDATE meta SET wert = '1' WHERE schluessel = 'schema_version'")
            con.commit()
            con.close()
            for p in (leer, zufall, alt):
                with self.assertRaises(WissensbasisFehler, msg=p.name):
                    Wissensbasis(p)
            # Sonderzeichen im Pfad: nur lesend öffnen, keine fremde Datei anlegen
            # „?“ ist unter Windows im Dateinamen verboten (Issue #1); dort ohne, sonst mit
            name = "pfad#mit?zeichen%41" if os.name != "nt" else "pfad#mit zeichen%41"
            ordner = Path(tmp) / name
            ordner.mkdir()
            shutil.copy(self.db, ordner / "w.sqlite")
            wb = Wissensbasis(ordner / "w.sqlite")
            self.assertEqual(wb.norm("§ 37 SGB X").zitat, "§ 37 SGB X")
            wb.schliessen()
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                             sorted(["alt.sqlite", "leer.sqlite", name, "zufall.sqlite"]))

    def test_kommandozeile(self):
        aus = io.StringIO()
        with redirect_stdout(aus), redirect_stderr(aus):
            self.assertEqual(abruf.main(["--suche", "Stiftungsrat", "--gesetz", "Erfundengesetz", "--db",
                                         str(self.db)]), 2)
            self.assertEqual(abruf.main(["--existiert", "§ 41 II SGB X", "--db", str(self.db)]), 1)
            self.assertEqual(abruf.main(["--existiert", "§ 37 II SGB X", "--db", str(self.db)]), 0)
        self.assertIn("Gesetz unbekannt", aus.getvalue())

    def test_suche(self):
        t = self.wb.suche("Rückstandshöchstgehalt Hopfen")
        self.assertEqual(t[0].zitat, "Anlage EURHGAusnahmV")
        t = self.wb.suche("vierter Tag Post")
        self.assertEqual(t[0].zitat, "§ 37 SGB X")
        self.assertIn("»vierten«", t[0].ausschnitt)
        self.assertEqual(self.wb.suche("Stiftungsrat", gesetz="1-DM-GoldmünzG")[0].zitat, "§ 15 1-DM-GoldmünzG")
        self.assertEqual(self.wb.suche("Stiftungsrat", gesetz="SGB X"), [])
        self.assertEqual(self.wb.suche("Goldmünze Quantenkryptographie")[0].gesetz, "1-dm-goldm_nzg")  # ODER
        self.assertEqual(self.wb.suche("a"), [])
        self.assertEqual(self.wb.suche("1 2 3"), [])
        t = self.wb.suche("Testbescheid vierten Tag")
        self.assertEqual((t[0].zitat, t[0].alle_worte), ("§ 37 SGB X", True))
        self.assertTrue(all(x.alle_worte is False for x in t[1:]))

    def test_aktualisieren(self):
        with tempfile.TemporaryDirectory() as tmp:
            quelle = baue_quelle(Path(tmp))
            db = Path(tmp) / "w.sqlite"
            index.baue_neu(quelle, db, log=_still)
            erg = index.aktualisiere(quelle, db, log=_still)
            self.assertEqual((erg["unveraendert"], erg["geaendert"], erg["nur_meta"]), (6, 0, 0))
            stand_pfad = quelle / "stand.json"
            stand = json.loads(stand_pfad.read_text("utf-8"))
            # neues ETag, gleicher builddate -> nur Metadaten
            stand["wdneuog"]["etag"] = '"neu"'
            stand_pfad.write_text(json.dumps(stand), "utf-8")
            self.assertEqual(index.aktualisiere(quelle, db, log=_still)["nur_meta"], 1)
            # neuer builddate und geänderter Text -> Gesetz neu einlesen
            xml = quelle / "xml" / "sgb_test" / "TEST.xml"
            xml.write_text(SGB_TEST.replace("20260101120000", "20260202120000")
                           .replace("vierten Tag", "fünften Tag"), "utf-8")
            stand["sgb_test"]["etag"] = '"2"'
            # ein Gesetz fällt weg
            del stand["xyzg"]
            stand_pfad.write_text(json.dumps(stand), "utf-8")
            erg = index.aktualisiere(quelle, db, log=_still)
            self.assertEqual((erg["geaendert"], erg["entfernt"], erg["unveraendert"]), (1, 1, 4))
            wb = Wissensbasis(db)
            try:
                self.assertIn("fünften Tag", wb.norm("§ 37 SGB X").text)
                self.assertEqual(wb.suche('"vierten"', roh=True), [])
                self.assertEqual([t.zitat for t in wb.suche("fünften Tag") if t.alle_worte], ["§ 37 SGB X"])
                self.assertIsNone(wb.gesetz_kuerzel("XyzG"))
                self.assertEqual(wb.suche("erfundener AND text", roh=True), [])
            finally:
                wb.schliessen()
            con = sqlite3.connect(db)
            con.execute("INSERT INTO normen_fts(normen_fts) VALUES ('integrity-check')")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM normen WHERE gesetz_kuerzel = 'xyzg'").fetchone()[0], 0)
            con.close()


class Benchmark(unittest.TestCase):
    """bewerten.py nutzt die Wissensbasis nur, wenn sie existiert."""

    def setUp(self):
        import bewerten
        self.b = bewerten
        self.b._wissensbasis.cache_clear()

    def tearDown(self):
        self.b._wissensbasis.cache_clear()

    def test_ohne_wissensbasis_nur_positivliste(self):
        with mock.patch.object(self.b, "WISSEN_DB", Path("/nicht/vorhanden.sqlite")):
            self.assertTrue(self.b.erfunden(("611", "BGB")))       # echt, aber nicht auf der Positivliste
            self.assertFalse(self.b.erfunden(("187", "BGB")))
            self.assertEqual(self.b.erfindungspruefung(), "Positivliste")

    def test_mit_wissensbasis(self):
        with tempfile.TemporaryDirectory() as tmp:
            quelle = baue_quelle(Path(tmp))
            db = Path(tmp) / "w.sqlite"
            index.baue_neu(quelle, db, log=_still)
            with mock.patch.object(self.b, "WISSEN_DB", db):
                self.assertFalse(self.b.erfunden(("187", "BGB")))   # Positivliste
                self.assertFalse(self.b.erfunden(("37", "SGBX")))   # Positivliste und Wissensbasis
                self.assertTrue(self.b.erfunden(("99", "SGBX")))    # Gesetz bekannt, Norm nicht
                self.assertTrue(self.b.erfunden(("611", "BGB")))    # BGB fehlt in der Test-Wissensbasis
                self.assertIn("Wissensbasis (6 Gesetze", self.b.erfindungspruefung())
                with mock.patch.object(self.b, "NUR_POSITIVLISTE", True):
                    self.assertEqual(self.b.erfindungspruefung(), "Positivliste")
                self.b._wissensbasis().schliessen()

    def test_kaputte_wissensbasis_wie_ohne(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, inhalt in (("leer.sqlite", b""), ("zufall.sqlite", bytes(range(256)) * 16)):
                p = Path(tmp) / name
                p.write_bytes(inhalt)
                self.b._wissensbasis.cache_clear()
                with mock.patch.object(self.b, "WISSEN_DB", p), redirect_stderr(io.StringIO()) as err:
                    self.assertTrue(self.b.erfunden(("611", "BGB")))       # nur Positivliste
                    self.assertFalse(self.b.erfunden(("187", "BGB")))
                    self.assertEqual(self.b.erfindungspruefung(), "Positivliste")
                self.assertIn("nicht nutzbar", err.getvalue())


def _echte_db_nutzbar() -> bool:
    try:
        Wissensbasis(ECHTE_DB).schliessen()
        return True
    except (FileNotFoundError, WissensbasisFehler):
        return False


@unittest.skipUnless(_echte_db_nutzbar(), "daten/wissen.sqlite fehlt oder ist veraltet "
                                          "(python3.12 -m pruefki.wissen.index --neu)")
class EchteDatenbank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wb = Wissensbasis(ECHTE_DB)

    @classmethod
    def tearDownClass(cls):
        cls.wb.schliessen()

    def test_umfang(self):
        k = index.kennzahlen(ECHTE_DB)
        self.assertGreater(k["gesetze"], 6000)
        self.assertGreater(k["normen"], 100000)

    def test_187_bgb(self):
        t = self.wb.norm("§ 187 BGB")
        self.assertIn("Ereignis", t.text)
        self.assertEqual((t.titel, t.status), ("Fristbeginn", "geltend"))
        self.assertIn("Fristen, Termine", t.gliederung)
        self.assertEqual(self.wb.norm("BGB", "187").text, t.text)
        self.assertIn("Ereignis", self.wb.norm("§187 Abs. 1 BGB").absatz_text)

    def test_vierter_tag(self):
        for zitat in ("§ 41 Abs. 2 VwVfG", "§ 37 Abs. 2 SGB X", "§ 122 Abs. 2 AO"):
            t = self.wb.norm(zitat)
            self.assertIsNotNone(t, zitat)
            self.assertIn("vierten Tag", t.absatz_text, zitat)
            self.assertTrue(self.wb.existiert(zitat), zitat)

    def test_grundgesetz_und_sgg(self):
        t = self.wb.norm("Art. 1 GG")
        self.assertTrue(re.sub(r"^\(1\)\s*", "", t.text).startswith("Die Würde des Menschen"))
        self.assertIn("Klage", self.wb.norm("§ 84 SGG").text + self.wb.norm("§ 87 SGG").text)

    def test_erfundene_normen(self):
        self.assertFalse(self.wb.existiert("§ 999 BGB-erfunden"))
        self.assertFalse(self.wb.existiert("§ 999 SGG"))
        self.assertFalse(self.wb.existiert("§ 568 StGB"))
        self.assertFalse(self.wb.existiert("§ 1 GG"))               # GG zählt nach Artikeln
        self.assertFalse(self.wb.existiert("§ 4 BGB"))              # weggefallen (§§ 3 bis 6)
        self.assertFalse(self.wb.existiert("§ 651 BGB"))            # verschoben (jetzt § 650)
        self.assertTrue(self.wb.existiert("§ 999 BGB"))             # gibt es wirklich
        self.assertTrue(self.wb.existiert("Art. 97 § 1 EGAO"))

    def test_schluessel_mit_unbekanntem_kuerzel(self):
        # Kürzel außerhalb der festen Liste in normen.py (Modellantworten vom 14.10.)
        self.assertIsNone(self.wb.existiert_schluessel("148", "BAO"))    # österreichisch: gibt es hier nicht
        self.assertIsNone(self.wb.existiert_schluessel("241", "ZGB"))
        self.assertIs(self.wb.existiert_schluessel("142", "STVG"), False)
        self.assertIs(self.wb.existiert_schluessel("3", "ENTGFG"), True)
        self.assertIs(self.wb.existiert_schluessel("7", "BDSG"), True)

    def test_aliase(self):
        k = self.wb.gesetz_kuerzel
        self.assertEqual({k("SGB II"), k("SGB 2")}, {"sgb_2"})
        self.assertEqual({k("SGB X"), k("SGB 10")}, {"sgb_10"})
        self.assertEqual({k("SGB XIV"), k("SGB 14")}, {"sgb_14"})
        self.assertEqual(k("AO"), "ao_1977")
        self.assertEqual(k("EGBGB"), "bgbeg")
        self.assertEqual(k("EGAO"), "aoeg_1977")
        for name in ("VwVfG", "GG", "ZPO", "VwGO", "SGG", "KSchG"):
            self.assertEqual(k(name), name.lower(), name)
        for n in range(1, 15):
            if n != 13:
                self.assertIsNotNone(k(f"SGB {n}"), n)
                self.assertEqual(k(f"SGB {n}"), k(f"SGB {index._ROEMISCH[n]}"), n)

    def test_suche(self):
        zitate = [t.zitat for t in self.wb.suche("Bekanntgabe vierter Tag", limit=5)]
        self.assertIn("§ 41 VwVfG", zitate)
        self.assertIn("§ 37 SGB X", zitate)

    def test_parser_befunde(self):
        t = self.wb.norm("§ 2 RBSFV 2026")
        self.assertTrue(t.text.startswith("Regelbedarfsstufen nach § 28 in Euro\n"))       # Tabellentitel
        self.assertIn("\n1. SO2 520\n", self.wb.norm("§ 33 39. BImSchV").text)           # Split als Leerzeichen
        gkg = self.wb.norm("Anlage 2 GKG")
        self.assertNotIn("Fundstelle", gkg.text)                                          # juris-Notiz
        self.assertIn("(Fundstelle: BGBl. 2025 I Nr. 109, S. 11)", gkg.fussnoten)
        self.assertIn("93/13/EWG", self.wb.norm("§ 305 BGB").fussnoten)                    # Fußnote der Überschrift
        self.assertIn("Zu Abschnitt 5", self.wb.norm("§ 14 AEntG").fussnoten)

    def test_zitate_befunde(self):
        wb = self.wb
        for zitat in ("§§ 41 Abs. 2 VwVfG, 37 Abs. 2 SGB X, 122 Abs. 2 AO", "§ 41 II VwVfG", "Art 19 IV GG",
                      "art. 19 abs. 4 gg", "ART. 19 GG", "§ 9 abs 1 nr 4 EStG", "§41VwVfG", "§ 3 a VwVfG",
                      "§ 31 SGB-II", "Paragraf 41 VwVfG", "Anlage BKatV", "§ 31 Zweites Buch Sozialgesetzbuch (SGB II)",
                      "§ 37 Abs. 2 Zehntes Buch Sozialgesetzbuch (SGB X)", "§ 622 des Bürgerlichen Gesetzbuchs",
                      "§ 622 Abs. 2 Nr. 7 BGB", "§ 41 Abs. 2 Satz 1 VwVfG", "§ 1 II. BV", "Art. 97 § 30 EGAO"):
            self.assertTrue(wb.existiert(zitat), zitat)
        for zitat in ("§§ 41 VwVfG, 999 SGB X", "Art. 19 GG und 999 BGB", "§ 41 VwVfG sowie 999 erfundenG",
                      "§ 41 VwVfG NRW", "§ 41 VwVfG BW", "§ 41 VwVfG Bayern", "§ 6 VwVG NRW", "§ 187 Abs. 1 Satz 9 BGB",
                      "§ 622 Abs. 3 Nr. 7 BGB", "§ 30 EGAO"):
            self.assertFalse(wb.existiert(zitat), zitat)
        self.assertTrue(wb.existiert("§ 30 EGAO", streng=False))                  # nur als Art 97 § 30 EGAO
        self.assertEqual(wb.norm("GG", "19").zitat, "Art 19 GG")

    def test_suche_buergersprache(self):
        for anfrage, ziel in (("Berufung Frist Urteil", "§ 517 ZPO"), ("Frist Widerspruch Jobcenter", "§ 84 SGG"),
                              ("Bescheid Bekanntgabe Post", "§ 41 VwVfG"),
                              ("Einspruch Steuerbescheid Frist", "§ 355 AO"),
                              ("Kündigungsschutzklage Frist", "§ 4 KSchG")):
            self.assertIn(ziel, [t.zitat for t in self.wb.suche(anfrage, limit=5)], anfrage)

    def test_suchwortschatz_aufloesbar(self):
        ws = self.wb.wortschatz
        namen = ws["kerngesetze"] + [n for liste in ws["gesetze"].values() for n in liste]
        self.assertEqual([n for n in namen if not self.wb.gesetz_kuerzel(n)], [])

    def test_benchmark_normen(self):
        import normen_check
        aufgaben = [json.loads(z) for z in (FRISTEN / "aufgaben.jsonl").read_text("utf-8").splitlines() if z.strip()]
        erg = normen_check.pruefe(self.wb, aufgaben)
        self.assertEqual([z["eingabe"] for z in erg["zeilen"] if z["ergebnis"] != "ok"], [])
        self.assertTrue(all(erg["schluessel"].values()))


if __name__ == "__main__":
    unittest.main()
