"""Tests für die Kette „Modell liest, Code rechnet“ (kette.py, prompt_kette.py, fehleranalyse.py).

Kein Netz: das Modell ist ein Stub (chat_fn) oder ein nachgebauter Ollama-Server (urlopen).
"""

import ast
import io
import json
import re
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

WURZEL = Path(__file__).resolve().parents[1]
FRISTEN = WURZEL / "benchmark" / "fristen"
for p in (str(WURZEL), str(FRISTEN)):
    if p not in sys.path:
        sys.path.insert(0, p)

import bewerten  # noqa: E402
import fehleranalyse  # noqa: E402
import generator  # noqa: E402
import kette as K  # noqa: E402
import prompt_kette as PK  # noqa: E402
from pruefki.fristen import rechner as R  # noqa: E402
from pruefki.fristen.normen import schluessel, treffer  # noqa: E402

AUFGABEN = generator.lade()
NACH_ID = {a["id"]: a for a in AUFGABEN}


def _bewerte(verzeichnis, laeufe=3):
    # nur Positivliste: unabhängig davon, ob daten/wissen.sqlite lokal gebaut ist
    with mock.patch.object(bewerten, "NUR_POSITIVLISTE", True):
        return bewerten.bewerte(NACH_ID, bewerten.lade_ergebnisse([Path(verzeichnis)]), laeufe)


def _roh(**kw) -> dict:
    roh = {n: None for n in PK.FELDNAMEN}
    roh.update(kw)
    return roh


def _felder(**kw) -> dict:
    f, hinweise = K.normalisiere(_roh(**kw))
    assert hinweise == [], hinweise
    return f


def _aufgabe_aus_nachricht(nachrichten) -> dict:
    user = nachrichten[1]["content"]
    treffer_ = [a for a in AUFGABEN if a["dokument"] in user]
    assert len(treffer_) == 1
    return treffer_[0]


def _zeile_mit(a: dict, text: str) -> str:
    """Erste Zeile des Dokuments, die ``text`` enthält (als Fundstelle einer Nachfrage)."""
    return next(z.strip() for z in a["dokument"].splitlines() if text in z)


class Schema(unittest.TestCase):
    def test_nur_tatsachen_keine_rechenergebnisse(self):
        schemata = [f.schema for f in PK.FASSUNGEN.values()] + [PK.nachfrage_schema(n) for n in PK.NACHFRAGEN]
        for schema in schemata:
            props = schema["properties"]
            for verboten in ("antwortart", "fristende", "normen", "sicherheit", "begruendung", "termin", "mietende"):
                self.assertNotIn(verboten, props)
            self.assertEqual(schema["required"], list(props))
            self.assertIs(schema["additionalProperties"], False)
            for n, s in props.items():
                self.assertIn("null", s["type"], n)
                if "enum" in s:
                    self.assertIn(None, s["enum"], n)
            json.dumps(schema)
        for f in PK.FASSUNGEN.values():
            self.assertEqual(list(f.schema["properties"]), PK.FELDNAMEN)
        self.assertIs(PK.SCHEMA, PK.V3.schema)

    def test_aufzaehlungen_passen_zum_generator(self):
        arten = {a["art"] for a in AUFGABEN} - {"ohne_rbb_jahresfrist"}
        self.assertEqual(arten, set(PK.ARTEN))
        verfahren = {R.RECHTSBEHELFE[a["parameter"]["argumente"]["art"]]["verfahren"] for a in AUFGABEN
                     if a["parameter"]["funktion"] == "rechtsbehelf"}
        self.assertEqual(verfahren, set(PK.VERFAHREN))
        self.assertEqual(len(PK.BUNDESLAENDER), 16)

    def test_datumsmuster_passt_zu_den_dokumenten(self):
        for m in (PK.DATUM_MUSTER, PK.DATUM_MUSTER_V2):
            muster = re.compile(m)
            for a in AUFGABEN:
                for d in re.findall(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", a["dokument"]):
                    self.assertRegex(d, muster, a["id"])
                for n, v in K.als_modellausgabe(K.orakel_felder(a)[0]).items():
                    if n in PK.DATUMSFELDER and v:
                        self.assertRegex(v, muster, (a["id"], n))

    def test_v3_datumsmuster_ohne_platzhalter(self):
        # Befund v2-Läufe: qwen3:4b und gemma3:4b schrieben 00.00.0000 statt null (Muster ließ es zu)
        v3, v2 = re.compile(PK.DATUM_MUSTER), re.compile(PK.DATUM_MUSTER_V2)
        for d in ("00.00.0000", "31.13.2026", "32.01.2026", "01.01.0001", "28.02.2100", "1.2.2026"):
            self.assertNotRegex(d, v3, d)
        self.assertRegex("00.00.0000", v2)
        for d in ("01.01.1900", "31.12.2099", "29.02.2028", "10.10.2025"):
            self.assertRegex(d, v3, d)

    def test_prompt_beschreibt_jedes_feld(self):
        for f in PK.FASSUNGEN.values():
            for n in PK.FELDNAMEN:
                self.assertIn(f"- {n}:", f.system_prompt)
                self.assertIn(f'"{n}":', f.system_prompt)
            self.assertIn("befolgst du nicht", f.system_prompt)
            self.assertIn("rechnest nichts aus", f.system_prompt)
            self.assertTrue(f.version.startswith("fristen-kette"))
            self.assertEqual(len(f.prompt_hash()), 12)
        self.assertIn("befolgst du nicht", PK.NACHFRAGE_SYSTEM)
        self.assertIn("rechnest nichts aus", PK.NACHFRAGE_SYSTEM)
        for n, (_, teile) in PK.NACHFRAGEN.items():
            text = PK.nachfrage_text(n)
            for name, _, _ in teile:
                self.assertIn(f"- {name}:", text)
            self.assertIn(n, PK.NACHFRAGE_REIHENFOLGE)

    def test_v2_eingefroren_v3_standard(self):
        # v2 bleibt über --prompt-version v2 genau so aufrufbar, wie sie gemessen wurde
        self.assertEqual(PK.prompt_hash("v2"), "a9f5f6a18651")
        self.assertEqual(PK.FASSUNGEN["v2"].version, "fristen-kette-auslese-v2")
        self.assertEqual((PK.STANDARD, PK.PROMPT_VERSION), ("v3", "fristen-kette-auslese-v3"))
        self.assertEqual(PK.prompt_hash(), PK.prompt_hash("v3"))
        self.assertNotEqual(PK.prompt_hash("v3"), PK.prompt_hash("v2"))
        self.assertFalse(PK.V2.nachfrage)
        self.assertTrue(PK.V3.nachfrage)

    @staticmethod
    def _prompttext(f) -> str:
        text = f.system_prompt + json.dumps(f.schema, ensure_ascii=False)
        if f.nachfrage:
            text += PK.NACHFRAGE_SYSTEM + "".join(PK.nachfrage_text(n) + json.dumps(PK.nachfrage_schema(n),
                                                                                     ensure_ascii=False)
                                                  for n in PK.NACHFRAGEN)
        return text

    def test_prompt_ohne_daten_namen_und_fallen_der_aufgaben(self):
        # Befund Gegenprüfer 15.10.2026: v1 nahm Fallen einzelner Aufgaben vorweg (auch im privaten Split)
        namen = list(generator.BUNDESBEHOERDEN) + list(generator.HAUSVERWALTUNGEN) + list(generator.FIRMEN)
        namen += [o for orte in generator.ORTE.values() for o in orte] + [f"{v} {n}" for _, v, n in generator.NAMEN]
        namen += list(generator.SACHBEARBEITUNG) + list(generator.STRASSEN)
        wendungen = ["Nicht das", "Geburtsdatum", "Mietvertrag", "Zahlungsfrist", "Eigentümerin", "Hausverwaltung",
                     "Bundesanstalt", "Bundesamt", "Sozialamt", "Jobcenter", "Empfangsbestätigung",
                     "Botenprotokoll", "Postausgangsvermerk", "sechs Monate", "Ablauf der Frist"]
        # v3 zusätzlich: Wendungen der Vorlagen für Zugang, Zustellung, Absendung und Vermerke Dritter
        wendungen_v3 = ["Eingangsstempel", "eingegangen am", "persönlich erhalten", "persönlich übergeben",
                        "zur Post gegeben", "Briefkasten eingelegt", "Auszug", "Fristenbuch", "Vorfrist",
                        "Kanzlei", "Betriebsrat", "Mieterverein", "Personalbüro", "Erwerbslosenberatung",
                        "nächstmöglichen", "Brief, Inland", "Nachzahlung", "Zuwendung", "Förder", "Zuschuss",
                        "Ehrenamt", "Bürgergeld", "Kaution", "Eigenbedarf", "Schriftstück", "Vermerk",
                        "datum des schreibens", "nicht das datum"]
        for f in PK.FASSUNGEN.values():
            text = self._prompttext(f)
            self.assertNotRegex(text, r"\d{1,2}\.\d{1,2}\.\d{4}", f.name)
            self.assertNotRegex(text, r"\b(19|20)\d\d\b", f.name)
            for name in namen:
                self.assertNotIn(name, text, f.name)
            for wendung in wendungen + (wendungen_v3 if f.name != "v2" else []):
                # am Wortanfang (sonst träfe „Förder“ auch „Beförderung“)
                self.assertNotRegex(text.lower(), r"(?<![a-zäöüß])" + re.escape(wendung.lower()), (f.name, wendung))
            for a in AUFGABEN:
                self.assertNotIn(a["id"], text, f.name)

    def test_v3_keine_wortfolge_aus_aufgaben_oder_generator(self):
        # Schutz gegen Abschreiben, nicht gegen Zuschnitt: keine Folge von vier Wörtern aus Dokumenten, Fragen oder
        # Texten von generator.py. Umschriebene Vorlagenfallen bestehen diesen Test (Gegenprüfer 15.10.2026); dagegen
        # helfen nur Durchsicht und ein Holdout mit neuen Vorlagen (test_v3_ohne_umschriebene_vorlagenfallen).
        def ngramme(text, n=4):
            w = re.findall(r"[a-zäöüß]+", text.lower())
            return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}
        quellen = [t for a in AUFGABEN for t in (a["dokument"], a["frage"])]
        baum = ast.parse((FRISTEN / "generator.py").read_text("utf-8"))
        quellen += [k.value for k in ast.walk(baum) if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        fremd = set().union(*(ngramme(q) for q in quellen))
        for f in PK.FASSUNGEN.values():
            self.assertEqual(ngramme(self._prompttext(f)) & fremd, set(), f.name)

    def test_v3_ohne_umschriebene_vorlagenfallen(self):
        # Befund Gegenprüfer 15.10.2026: v3 enthielt Umschreibungen, die genau die Vorlagen abdeckten (drei
        # Zugangsnachweise, zwei Zustellweisen der Urkunde, Behördennamen mit Geld- und Abgabenbezug, Vermerke
        # Dritter). Sie sind entfernt und dürfen nicht zurückkommen. Die Liste ist eine Sperre für diese bekannten
        # Fälle, keine allgemeine Erkennung von Zuschnitt.
        gesperrt = ["aushändigung an", "aushändigung, erhalt", "erhalt", "eingang", "einwurf", "ersatzweise",
                    "ersatzzustellung", "selbst gab", "abgaben", "finanzverwaltung", "um geld", "name der behörde",
                    "anmerkungen anderer", "anderer personen oder stellen"]
        text = Schema._prompttext(PK.V3).lower()
        for wendung in gesperrt:
            self.assertNotRegex(text, r"(?<![a-zäöüß])" + re.escape(wendung), wendung)
        # Feiertage am Ort, an dem die Frist zu wahren ist: bei Klagen der Sitz des Gerichts (Gegenprüfer, § 222 ZPO)
        land = dict((n, t) for n, _, t in PK.FELDER_V3)["bundesland"]
        self.assertIn("Gericht seinen Sitz", land)
        self.assertIn("Regelfall", dict((n, t) for n, _, t in PK.FELDER_V3)["verfahren"])

    def test_nachricht_nur_dokument_und_frage(self):
        for a in AUFGABEN:
            nur = {"dokument": a["dokument"], "frage": a["frage"]}
            n = PK.nachrichten(a)
            self.assertEqual(n, PK.nachrichten(nur))
            self.assertEqual(n[0]["content"], PK.SYSTEM_PROMPT)
            self.assertEqual(PK.nachrichten(a, "v2")[0]["content"], PK.V2.system_prompt)
            texte = [json.dumps(n, ensure_ascii=False)]
            for feld in PK.NACHFRAGEN:      # Nachfrage: ebenfalls nur Dokument, Frage und die gesuchte Angabe
                nf = PK.nachfrage_nachrichten(a, feld)
                self.assertEqual(nf, PK.nachfrage_nachrichten(nur, feld))
                self.assertEqual(nf[0]["content"], PK.NACHFRAGE_SYSTEM)
                texte.append(json.dumps(nf, ensure_ascii=False))
            for text in texte:
                for verboten in ('"parameter"', '"sollwert"', "rechenweg", "pruefhinweis", "Typ:", a["id"]):
                    self.assertNotIn(verboten, text, a["id"])
                if a["typ"] == "berechnen":
                    d = date.fromisoformat(a["sollwert"]["fristende"])
                    self.assertNotIn(d.isoformat(), text, a["id"])
                    self.assertNotIn(d.strftime("%d.%m.%Y"), text, a["id"])


class Normalisieren(unittest.TestCase):
    def test_datum_mit_monatsnamen(self):
        # Gefunden mit Briefen in fremdem Stil (16.10.): Eingangsstempel und Briefdaten mit Monatsnamen
        self.assertEqual(K.lies_datum("02. APR. 2026"), ("2026-04-02", False))
        self.assertEqual(K.lies_datum("Dienstag, 3. März 2026"), ("2026-03-03", False))
        self.assertEqual(K.lies_datum("3. Mrz. 2026"), ("2026-03-03", False))
        self.assertEqual(K.lies_datum("12. Janssen 2026"), (None, True))
        self.assertEqual(K.datumsangaben("EINGEGANGEN 02. APR. 2026, Versand am 4. Sept. 2026")["2026-04-02"], 1)
        self.assertEqual(K.datumsangaben("Versand am 4. Sept. 2026")["2026-09-04"], 1)

    def test_schreibweisen(self):
        f, h = K.normalisiere(_roh(bundesland="baden-wuerttemberg", verfahren="SGB 10", art="Kündigung_Miete",
                                   datum_zugang="2.2.2027", datum_aufgabe_post="2027-02-03",
                                   rechtsbehelfsbelehrung=True, probezeit="ja", probezeit_monate="sechs"))
        self.assertEqual(h, [])
        self.assertEqual((f["bundesland"], f["verfahren"], f["art"]), ("BW", "SGB X", "kuendigung_miete"))
        self.assertEqual((f["datum_zugang"], f["datum_aufgabe_post"]), ("2027-02-02", "2027-02-03"))
        self.assertEqual((f["rechtsbehelfsbelehrung"], f["probezeit"], f["probezeit_monate"]), ("vorhanden", True, 6))

    def test_unlesbares_wird_null_mit_hinweis(self):
        f, h = K.normalisiere(_roh(schreiben="bescheid", bundesland="Bayernland", datum_zugang="31.02.2027",
                                   art="mahnung", x=1))
        self.assertEqual(f["schreiben"], "bescheid")
        self.assertIsNone(f["bundesland"])
        self.assertIsNone(f["datum_zugang"])
        self.assertIsNone(f["art"])
        self.assertEqual(len(h), 4)
        self.assertEqual(K.normalisiere("kein Objekt")[0], None)

    def test_leere_auslese_ist_unlesbar(self):
        for roh in ({}, _roh(), {"antwortart": "berechnet", "fristende": None},
                    _roh(bundesland="Bayernland", art="mahnung")):
            f, h = K.normalisiere(roh)
            self.assertIsNone(f, roh)
            self.assertIn("Auslese leer: kein Feld lesbar", h)

    def test_unplausible_jahre_sind_unlesbar(self):
        for v in ("31.12.9999", "28.12.9999", "01.01.0001", "0001-01-31", "31.12.1899", "01.01.2100"):
            self.assertEqual(K.lies_datum(v), (None, True), v)
        for v, iso in (("01.01.1900", "1900-01-01"), ("31.12.2099", "2099-12-31"), ("2.2.2027", "2027-02-02")):
            self.assertEqual(K.lies_datum(v), (iso, False), v)
        self.assertEqual(K._zahl(-3), (None, True))
        self.assertEqual(K._zahl(6.5), (None, True))

    def test_bundesland_schreibweisen(self):
        for v, code in (("NRW", "NW"), ("Freistaat Bayern", "BY"), ("Niedersachsen (NI)", "NI"),
                        ("Heidebrunn (Niedersachsen)", "NI"), ("Freie und Hansestadt Hamburg", "HH"),
                        ("Freie Hansestadt Bremen", "HB"), ("Land Berlin", "BE"), ("Saarland", "SL"),
                        ("Sachsen-Anhalt", "ST"), ("sachsen anhalt", "ST"), (" niedersachsen ", "NI")):
            self.assertEqual(K._land(v), (code, False), v)
        for v in ("Hannover", "Lower Saxony", "Sachsen (Bayern)", "Heidebrunn"):
            self.assertEqual(K._land(v), (None, True), v)

    def test_hin_und_zurueck(self):
        for a in AUFGABEN:
            f, _ = K.orakel_felder(a)
            self.assertEqual(K.normalisiere(K.als_modellausgabe(f)), (f, []), a["id"])


class Abbildung(unittest.TestCase):
    def test_orakel_je_art_gleich_dem_rechner(self):
        gesehen = set()
        for a in AUFGABEN:
            f, _ = K.orakel_felder(a)
            erg = K.rechne(f, a["typ"], a["frage"])
            ant, rechnung = erg["antwort"], erg["rechnung"]
            gesehen.add(a["art"])
            self.assertEqual(ant["antwortart"], a["sollwert"]["antwortart"], a["id"])
            self.assertEqual(ant["fristende"], a["sollwert"]["fristende"], a["id"])
            if a["sollwert"]["antwortart"] == "rueckfrage":
                self.assertTrue(rechnung["fehlend"], a["id"])
                continue
            e = R.berechne(a["parameter"]["funktion"], a["parameter"]["argumente"])
            self.assertEqual(rechnung["funktion"], a["parameter"]["funktion"], a["id"])
            self.assertEqual(ant["normen"], e.normen, a["id"])
            self.assertEqual(ant["sicherheit"], K.SICHER, a["id"])
            self.assertEqual((rechnung["annahmen"], rechnung["zweifel"]), ([], []), a["id"])
        self.assertEqual(gesehen, {a["art"] for a in AUFGABEN})

    def test_handgebaut_je_art(self):
        faelle = [
            (dict(schreiben="bescheid", verfahren="SGB X", bundesland="Niedersachsen", art="widerspruch_sgb2",
                  zustellart="einfacher_brief", datum_aufgabe_post="02.02.2027", rechtsbehelfsbelehrung="vorhanden"),
             R.rechtsbehelf("widerspruch_sgb2", "NI", aufgabe_post=date(2027, 2, 2))),
            (dict(schreiben="bescheid", verfahren="VwVfG", bundesland="Saarland", art="widerspruch_vwvfg",
                  zustellart="zustellungsurkunde", datum_zustellung="31.08.2026", rechtsbehelfsbelehrung="vorhanden"),
             R.rechtsbehelf("widerspruch_vwvfg", "SL", zustellart="pzu", zustellung=date(2026, 8, 31))),
            (dict(schreiben="bescheid", verfahren="AO", bundesland="Berlin", art="einspruch_ao",
                  zustellart="einfacher_brief", datum_aufgabe_post="08.05.2026", rechtsbehelfsbelehrung="fehlt"),
             R.rechtsbehelf("einspruch_ao", "BE", aufgabe_post=date(2026, 5, 8), rbb=False)),
            (dict(schreiben="widerspruchsbescheid", verfahren="SGB X", bundesland="Hamburg", art="klage_sgg",
                  zustellart="einfacher_brief", datum_aufgabe_post="11.07.2025", rechtsbehelfsbelehrung="vorhanden"),
             R.rechtsbehelf("klage_sgg", "HH", aufgabe_post=date(2025, 7, 11))),
            (dict(schreiben="widerspruchsbescheid", verfahren="VwVfG", bundesland="Brandenburg", art="klage_vwgo",
                  zustellart="zustellungsurkunde", datum_zustellung="27.04.2027", rechtsbehelfsbelehrung="vorhanden"),
             R.rechtsbehelf("klage_vwgo", "BB", zustellart="pzu", zustellung=date(2027, 4, 27))),
            (dict(schreiben="kuendigung_arbeitsverhaeltnis", bundesland="Hessen", art="kschg_klage",
                  zustellart="persoenliche_uebergabe", datum_zugang="29.11.2025", kuendigende_partei="arbeitgeber"),
             R.kschg_klage(date(2025, 11, 29), "HE")),
            (dict(schreiben="kuendigung_arbeitsverhaeltnis", bundesland="Baden-Württemberg", art="kuendigung_arbeit",
                  datum_zugang="27.04.2026", kuendigende_partei="arbeitgeber", beschaeftigungsbeginn="01.08.2018"),
             R.kuendigung_arbeit(date(2026, 4, 27), None, False, beginn=date(2018, 8, 1), land="BW")),
            (dict(schreiben="kuendigung_arbeitsverhaeltnis", bundesland="Nordrhein-Westfalen", art="kuendigung_arbeit",
                  datum_zugang="03.06.2026", kuendigende_partei="arbeitgeber", beschaeftigungsbeginn="01.04.2026",
                  probezeit=True, probezeit_monate=6),
             R.kuendigung_arbeit(date(2026, 6, 3), None, True, beginn=date(2026, 4, 1), land="NW")),
            (dict(schreiben="kuendigung_arbeitsverhaeltnis", bundesland="Bremen", art="kuendigung_arbeit",
                  datum_zugang="29.06.2026", kuendigende_partei="arbeitnehmer"),
             R.kuendigung_arbeit(date(2026, 6, 29), 0, False, partei="arbeitnehmer", land="HB")),
            (dict(schreiben="kuendigung_mietverhaeltnis", bundesland="Thüringen", art="kuendigung_miete",
                  datum_zugang="05.01.2026", kuendigende_partei="mieter"),
             R.kuendigung_miete(date(2026, 1, 5), "TH")),
            (dict(schreiben="kuendigung_mietverhaeltnis", bundesland="Brandenburg", art="kuendigung_miete",
                  datum_zugang="25.02.2025", kuendigende_partei="vermieter", ueberlassung="01.07.2019"),
             R.kuendigung_miete(date(2025, 2, 25), "BB", partei="vermieter", ueberlassung=date(2019, 7, 1))),
        ]
        arten = set()
        for roh, e in faelle:
            erg = K.rechne(_felder(**roh), "berechnen", "")
            arten.add(erg["rechnung"]["art"])
            self.assertEqual(erg["antwort"]["antwortart"], "berechnet", roh)
            self.assertEqual(erg["antwort"]["fristende"], e.datum.isoformat(), roh)
            self.assertEqual(erg["antwort"]["normen"], e.normen, roh)
            self.assertEqual(erg["antwort"]["sicherheit"], K.SICHER, roh)
            self.assertLessEqual(len(erg["antwort"]["begruendung"]), 500)
        self.assertEqual(arten, set(PK.ARTEN))

    def test_art_entscheidet_der_code_bei_bescheiden(self):
        roh = dict(schreiben="widerspruchsbescheid", verfahren="SGB X", bundesland="Berlin", art="widerspruch_sgb2",
                   zustellart="einfacher_brief", datum_aufgabe_post="14.01.2025", rechtsbehelfsbelehrung="vorhanden")
        erg = K.rechne(_felder(**roh), "berechnen")
        self.assertEqual(erg["rechnung"]["art"], "klage_sgg")
        self.assertEqual(erg["antwort"]["sicherheit"], K.MIT_ANNAHME)
        self.assertTrue(erg["rechnung"]["annahmen"])
        roh["art"] = "klage_sgg"
        self.assertEqual(K.rechne(_felder(**roh), "berechnen")["antwort"]["sicherheit"], K.SICHER)
        roh.update(art=None, verfahren=None)   # ohne verfahren und ohne art des Modells: keine Antwort
        erg = K.rechne(_felder(**roh), "berechnen")
        self.assertIsNone(erg["antwort"])
        self.assertEqual(erg["rechnung"]["fehlend"], ["art"])

    def test_kschg_oder_arbeit_aus_der_frage(self):
        f = _felder(schreiben="kuendigung_arbeitsverhaeltnis", bundesland="Hessen", datum_zugang="29.11.2025",
                    kuendigende_partei="arbeitgeber", beschaeftigungsbeginn="01.03.2020")
        klage = K.rechne(f, "berechnen", NACH_ID["F028"]["frage"])
        self.assertEqual(klage["rechnung"]["art"], "kschg_klage")
        self.assertEqual(klage["antwort"]["fristende"], "2025-12-22")
        self.assertEqual(klage["antwort"]["sicherheit"], K.MIT_ANNAHME)
        ende = K.rechne(f, "berechnen", "Zu welchem Termin endet das Arbeitsverhältnis?")
        self.assertEqual(ende["rechnung"]["art"], "kuendigung_arbeit")

    def test_art_des_modells_gegen_die_frage(self):
        # art passt nicht zur Frage: die Frage gilt, mit Annahme (vorher Klagefrist mit 0,9 statt Beendigungstermin)
        for i, falsche_art in (("F030", "kschg_klage"), ("F020", "kuendigung_arbeit"), ("F046", "kuendigung_arbeit"),
                               ("F048", "kschg_klage")):
            a = NACH_ID[i]
            f, _ = K.orakel_felder(a)
            f["art"] = falsche_art
            erg = K.rechne(f, a["typ"], a["frage"])
            self.assertTrue(K.ist_exakt(a, erg["antwort"]), i)
            self.assertEqual(erg["antwort"]["sicherheit"], K.MIT_ANNAHME, i)
        for a in AUFGABEN:
            if a["parameter"]["funktion"] in ("kschg_klage", "kuendigung_arbeit"):
                self.assertEqual(K.art_aus_frage(a["frage"]), a["parameter"]["funktion"], a["id"])
        self.assertIsNone(K.art_aus_frage("Was gilt hier?"))

    def test_pruefen_vergleicht_genanntes_mit_berechnetem_datum(self):
        a = next(x for x in AUFGABEN if x["sollwert"]["antwortart"] == "kein_befund")
        f, _ = K.orakel_felder(a)
        self.assertEqual(K.rechne(f, "pruefen")["antwort"]["antwortart"], "kein_befund")
        f["genanntes_fristende"] = "2099-12-31"
        ant = K.rechne(f, "pruefen")["antwort"]
        self.assertEqual((ant["antwortart"], ant["fristende"]), ("befund", a["sollwert"]["fristende"]))
        # bei berechnen spielt ein genanntes Datum keine Rolle
        self.assertEqual(K.rechne(f, "berechnen")["antwort"]["antwortart"], "berechnet")


class Rueckfrage(unittest.TestCase):
    def test_fehlende_felder_ergeben_rueckfrage(self):
        faelle = [("F001", "datum_aufgabe_post"), ("F011", "datum_zustellung"), ("F020", "datum_zugang"),
                  ("F031", "ueberlassung"), ("F030", "beschaeftigungsbeginn"), ("F008", "datum_zugang"),
                  ("F001", "bundesland"), ("F020", "bundesland"), ("F010", "genanntes_fristende")]
        for i, feld in faelle:
            a = NACH_ID[i]
            f, _ = K.orakel_felder(a)
            f[feld] = None
            erg = K.rechne(f, a["typ"], a["frage"])
            self.assertEqual(erg["antwort"]["antwortart"], "rueckfrage", (i, feld))
            self.assertIsNone(erg["antwort"]["fristende"], (i, feld))
            self.assertIn(feld, erg["rechnung"]["fehlend"], (i, feld))
            self.assertLess(erg["antwort"]["sicherheit"], K.SICHER, (i, feld))
            self.assertTrue(erg["antwort"]["normen"], (i, feld))

    def test_rueckfrage_aufgaben_treffen_die_pflichtnormen(self):
        for a in AUFGABEN:
            if a["sollwert"]["antwortart"] != "rueckfrage":
                continue
            ant = K.rechne(K.orakel_felder(a)[0], a["typ"], a["frage"])["antwort"]
            genannt = set().union(*(schluessel(n) for n in ant["normen"]))
            for p in a["sollwert"]["normen_pflicht"]:
                self.assertTrue(treffer(p, genannt), (a["id"], p))

    def test_art_unbestimmbar_gibt_keine_antwort(self):
        # Befund Gegenprüfer: sonst bekäme eine leere Auslese F002, F003 und F043 (Rückfrage) geschenkt
        erg = K.rechne({n: None for n in PK.FELDNAMEN}, "berechnen")
        self.assertIsNone(erg["antwort"])
        self.assertEqual(erg["rechnung"]["fehlend"], ["art"])
        self.assertIn("Art nicht bestimmbar", erg["rechnung"]["fehler"])
        z = K.verarbeite(NACH_ID["F002"], json.dumps(_roh(schreiben="sonstiges"), ensure_ascii=False))
        self.assertIsNotNone(z["felder"])
        self.assertIsNone(z["antwort"])
        self.assertIsNone(z["antwort_json"])

    def test_nullmodell_bekommt_nichts_geschenkt(self):
        inhalte = {"leer": "{}", "allesnull": json.dumps(_roh()),
                   "antwortform": json.dumps({"antwortart": "rueckfrage", "fristende": None}),
                   "sonstiges": json.dumps({"schreiben": "sonstiges"})}
        for fassung in ("v2", "v3"):
            aufrufe = []
            with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
                for name, inhalt in inhalte.items():
                    def antwort(*a, inhalt=inhalt, **k):
                        aufrufe.append(k["format_"])
                        return {"message": {"content": inhalt}}
                    K.main(["--modelle", f"{name}:0b", "--laeufe", "1", "--ausgabe-dir", tmp, "--datum", "2026-10-15",
                            "--prompt-version", fassung], chat_fn=antwort)
                rang = _bewerte(tmp, 1)
            self.assertEqual(len(aufrufe), 4 * 50, fassung)    # keine Art erkannt: keine Nachfrage
            for name in inhalte:
                g = rang[K.kettenname(f"{name}:0b", fassung)]["bereiche"]["gesamt"]
                self.assertEqual(g["exakt_alle_laeufe"], 0, (fassung, name))
                self.assertEqual(g["unlesbar_oder_fehler"], 50, (fassung, name))

    def test_vorgaben_rechnen_weiter_mit_geringerer_sicherheit(self):
        a = NACH_ID["F001"]
        for feld, sicherheit in (("rechtsbehelfsbelehrung", K.MIT_ANNAHME), ("zustellart", K.MIT_ANNAHME),
                                 ("art", K.SICHER), ("verfahren", K.SICHER)):
            f, _ = K.orakel_felder(a)
            f[feld] = None
            ant = K.rechne(f, a["typ"], a["frage"])["antwort"]
            self.assertEqual((ant["antwortart"], ant["fristende"]), ("berechnet", a["sollwert"]["fristende"]), feld)
            self.assertEqual(ant["sicherheit"], sicherheit, feld)

    def test_unlesbare_und_unplausible_felder_senken_die_sicherheit(self):
        a = NACH_ID["F044"]
        roh = K.als_modellausgabe(K.orakel_felder(a)[0])
        roh["probezeit"] = "sechs Monate"      # json-Fallback ohne Schema: unlesbar, Länge aber gelesen
        z = K.verarbeite(a, json.dumps(roh, ensure_ascii=False))
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(z["antwort_json"]["sicherheit"], K.MIT_ANNAHME)
        self.assertEqual(z["rechnung"]["unlesbar"], ["probezeit"])
        roh["probezeit_monate"] = None          # nichts zur Probezeit lesbar: gerechnet ohne, aber nicht sicher
        z = K.verarbeite(a, json.dumps(roh, ensure_ascii=False))
        self.assertFalse(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(z["antwort_json"]["sicherheit"], K.MIT_ANNAHME)
        for i, feld in (("F030", "beschaeftigungsbeginn"), ("F031", "ueberlassung"), ("F030", "datum_zugang"),
                        ("F001", "datum_aufgabe_post"), ("F020", "datum_zugang")):
            for wert in ("01.01.0001", "31.12.9999"):
                roh = K.als_modellausgabe(K.orakel_felder(NACH_ID[i])[0])
                roh[feld] = wert
                z = K.verarbeite(NACH_ID[i], json.dumps(roh, ensure_ascii=False))
                self.assertEqual(z["antwort_json"]["antwortart"], "rueckfrage", (i, feld, wert))
                self.assertLess(z["antwort_json"]["sicherheit"], K.SICHER, (i, feld, wert))
        f, _ = K.orakel_felder(NACH_ID["F031"])
        f["ueberlassung"] = "2025-06-01"        # Überlassung nach dem Zugang
        ant = K.rechne(f, "berechnen", NACH_ID["F031"]["frage"])["antwort"]
        self.assertEqual(ant["sicherheit"], K.MIT_ANNAHME)

    def test_overflow_im_rechner_ist_auslesefehler(self):
        # rechne direkt (ohne lies_datum): ein Jahr am Rand des Kalenders darf keine Ausnahme werfen
        f, _ = K.orakel_felder(NACH_ID["F020"])
        f["datum_zugang"] = "9999-12-28"
        erg = K.rechne(f, "berechnen", NACH_ID["F020"]["frage"])
        self.assertEqual(erg["antwort"]["antwortart"], "rueckfrage")
        self.assertEqual(erg["antwort"]["sicherheit"], K.UNBESTIMMT)
        self.assertIn("OverflowError", erg["rechnung"]["fehler"])

    def test_rechner_lehnt_ab_und_unplausibles(self):
        f = _felder(schreiben="widerspruchsbescheid", verfahren="VwVfG", bundesland="Bayern",
                    zustellart="einfacher_brief", datum_aufgabe_post="02.02.2027", rechtsbehelfsbelehrung="vorhanden")
        erg = K.rechne(f, "berechnen")    # Widerspruchsbescheid nach VwGO ist zuzustellen
        self.assertEqual(erg["antwort"]["antwortart"], "rueckfrage")
        self.assertEqual(erg["antwort"]["sicherheit"], K.UNBESTIMMT)
        self.assertIn("ValueError", erg["rechnung"]["fehler"])
        a = NACH_ID["F001"]
        f, _ = K.orakel_felder(a)
        f["datum_schreiben"] = "2027-02-10"   # Aufgabe zur Post vor dem Bescheiddatum
        erg = K.rechne(f, a["typ"], a["frage"])
        self.assertEqual(erg["antwort"]["fristende"], a["sollwert"]["fristende"])
        self.assertEqual(erg["antwort"]["sicherheit"], K.MIT_ANNAHME)
        self.assertTrue(erg["rechnung"]["zweifel"])


class Orakel(unittest.TestCase):
    def test_orakel_ergibt_50_von_50(self):
        for fassung, name in (("v2", "orakel+rechner"), ("v3", "orakel+rechner-v3")):
            with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
                argv = ["--orakel", "--ausgabe-dir", tmp, "--datum", "2026-10-15", "--prompt-version", fassung]
                self.assertEqual(K.main(argv), 0)
                datei = Path(tmp) / f"2026-10-15-{name}.jsonl"
                zeilen = [json.loads(z) for z in datei.read_text("utf-8").splitlines() if z.strip()]
                self.assertEqual(len(zeilen), 150)
                self.assertTrue(all(z["felder"] and z["rechnung"] and z["quelle"] == "orakel" for z in zeilen))
                self.assertTrue(all(z["aufrufe"] == 0 for z in zeilen))
                if fassung == "v3":
                    # keine Gegenprobe widerspricht den wahren Feldern; die Nachfrage (Orakel antwortet mit dem
                    # wahren Wert) kommt nur bei den Rückfrage-Aufgaben, bleibt dort leer und ändert nichts
                    self.assertTrue(all(z["gegenproben"] == [] for z in zeilen))
                    rueckfrage = {i for i, a in NACH_ID.items() if a["sollwert"]["antwortart"] == "rueckfrage"}
                    mit = {z["id"] for z in zeilen if z["nachfrage"]}
                    self.assertEqual(mit, rueckfrage)
                    self.assertTrue(all(z["nachfrage"]["uebernommen"] == [] and z["nachfrage"]["verworfen"] == []
                                        for z in zeilen if z["nachfrage"]))
                    self.assertTrue(all(z["prompt_version"] == "fristen-kette-auslese-v3" for z in zeilen))
                rang = _bewerte(tmp)
                g = rang[name]["bereiche"]["gesamt"]
                self.assertEqual(g["exakt_alle_laeufe"], 50, fassung)
                self.assertEqual(g["belegquote"], 1.0)
                self.assertEqual(g["erfindungsquote"], 0.0)
                self.assertEqual(g["sicher_und_falsch"], 0)
                an = fehleranalyse.analysiere(NACH_ID, fehleranalyse.lade_kette([Path(tmp)])[name])
                self.assertEqual(an["exakt_alle_laeufe"], "50/50")
                self.assertEqual(sum(s["falsch"] for s in an["felder"].values()), 0)
                # erneuter Start setzt auf und schreibt nichts doppelt
                K.main(argv)
                self.assertEqual(len(datei.read_text("utf-8").splitlines()), 150)


class StubModell(unittest.TestCase):
    """Gefälschtes Modell statt HTTP: liest richtig, außer bei absichtlich falschen Feldern."""

    FALSCH = {
        "F001": ("datum_aufgabe_post", "05.02.2027"),
        "F011": ("datum_zustellung", "04.02.2027"),
        "F020": ("datum_zugang", "07.10.2025"),            # Datum des Schreibens statt Zugang
        "F031": ("kuendigende_partei", "mieter"),          # Vermieterkündigung als Mieterkündigung
        "F010": ("genanntes_fristende", "13.07.2027"),     # kein_befund wird befund
        "F043": ("datum_aufgabe_post", "08.04.2027"),      # Bescheiddatum statt fehlender Aufgabe zur Post
        "F044": ("probezeit", False),                   # Probezeit übersehen
        "F026": ("rechtsbehelfsbelehrung", "vorhanden"),   # Jahresfrist übersehen
        "F024": ("bundesland", "Baden-Württemberg"),       # Feiertag im falschen Land
        "F006": ("beschaeftigungsbeginn", "14.04.2000"),   # Geburtsdatum statt Beschäftigungsbeginn
    }

    def setUp(self):
        self.aufrufe = []

    def stub(self, host, modell, nachrichten, *, think, timeout, optionen, format_="json", keep_alive="10m"):
        self.aufrufe.append({"modell": modell, "format": format_, "nachrichten": nachrichten, "think": think})
        a = _aufgabe_aus_nachricht(nachrichten)
        roh = K.als_modellausgabe(K.orakel_felder(a)[0])
        if a["id"] in self.FALSCH:
            feld, wert = self.FALSCH[a["id"]]
            roh[feld] = wert
        return {"message": {"content": json.dumps(roh, ensure_ascii=False)}, "eval_count": 60,
                "eval_duration": 2_000_000_000}

    def test_falsche_felder_werden_falsch_bewertet(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            rc = K.main(["--modelle", "stub:1b", "--ausgabe-dir", tmp, "--datum", "2026-10-15", "--prompt-version",
                         "v2"], chat_fn=self.stub)
            self.assertEqual(rc, 0)
            self.assertEqual(len(self.aufrufe), 150)      # v2: nie eine Nachfrage
            for r in self.aufrufe:
                self.assertEqual(r["format"], PK.V2.schema)
                self.assertEqual(r["nachrichten"], PK.nachrichten(_aufgabe_aus_nachricht(r["nachrichten"]), "v2"))
            datei = Path(tmp) / "2026-10-15-stub-1b+rechner.jsonl"
            zeilen = [json.loads(z) for z in datei.read_text("utf-8").splitlines() if z.strip()]
            self.assertTrue(all(z["format"] == "schema" and z["tokens_pro_s"] == 30.0 for z in zeilen))
            rang = _bewerte(tmp)["stub:1b+rechner"]
            self.assertEqual(rang["bereiche"]["gesamt"]["exakt_alle_laeufe"], 50 - len(self.FALSCH))
            for i, ergebnis in rang["pro_aufgabe"].items():
                self.assertEqual(ergebnis, "0/3" if i in self.FALSCH else "3/3", i)

            an = fehleranalyse.analysiere(NACH_ID, fehleranalyse.lade_kette([Path(tmp)])["stub:1b+rechner"])
            falsch = {n: s for n, s in an["felder"].items() if s["falsch"]}
            erwartet = {}
            for i, (feld, _) in self.FALSCH.items():
                erwartet.setdefault(feld, set()).add(i)
            self.assertEqual(set(falsch), set(erwartet))
            for feld, ids in erwartet.items():
                self.assertEqual(set(falsch[feld]["aufgaben"]), ids, feld)
                self.assertEqual(falsch[feld]["falsch"], 3 * len(ids), feld)
                self.assertEqual(falsch[feld]["falsch_noetig"], 3 * len(ids), feld)
            md = fehleranalyse.markdown({"stub:1b+rechner": an})
            self.assertIn("| datum_aufgabe_post |", md)
            self.assertIn("| F043 |", md)

    def test_format_json_als_kontrolllauf(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            K.main(["--modelle", "stub:1b", "--laeufe", "1", "--ids", "F004", "F005", "--format", "json",
                    "--ausgabe-dir", tmp, "--datum", "2026-10-15", "--prompt-version", "v2"], chat_fn=self.stub)
            self.assertEqual([r["format"] for r in self.aufrufe], ["json", "json"])
            datei = Path(tmp) / "2026-10-15-stub-1b+rechner-json.jsonl"
            zeilen = [json.loads(z) for z in datei.read_text("utf-8").splitlines() if z.strip()]
            self.assertEqual({(z["modell"], z["format"]) for z in zeilen}, {("stub:1b+rechner-json", "json")})
            rang = _bewerte(tmp, 1)
            self.assertEqual(rang["stub:1b+rechner-json"]["pro_aufgabe"]["F005"], "1/1")
            md = bewerten.markdown(rang, 1)
            self.assertIn("vergleichbar ist nur „exakt“", md)
            an = fehleranalyse.lade_kette([Path(tmp)])
            self.assertIn("stub:1b+rechner-json", an)
        self.assertNotIn("+rechner", bewerten.markdown({}, 3))

    def test_unlesbare_auslese_zaehlt_als_falsch(self):
        def kaputt(*a, **k):
            return {"message": {"content": "Ich kann das nicht lesen."}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            K.main(["--modelle", "kaputt:1b", "--laeufe", "1", "--ids", "F001", "--ausgabe-dir", tmp,
                    "--datum", "2026-10-15"], chat_fn=kaputt)
            z = json.loads((Path(tmp) / "2026-10-15-kaputt-1b+rechner-v3.jsonl").read_text("utf-8"))
            self.assertIsNone(z["felder"])
            self.assertIsNone(z["antwort_json"])
            self.assertIsNone(z["fehler"])
            self.assertEqual((z["aufrufe"], z["nachfrage"]), (1, None))
            self.assertEqual(_bewerte(tmp, 1)["kaputt:1b+rechner-v3"]["pro_aufgabe"]["F001"], "0/1")


class Fehleranalyse(unittest.TestCase):
    def test_gleichwertige_lesart_zaehlt_nicht_als_noetig(self):
        # Zustellungsurkunde mit persönlicher Übergabe als persoenliche_uebergabe + datum_zugang gelesen
        ids = [a["id"] for a in AUFGABEN if K.orakel_felder(a)[0]["zustellart"] == "zustellungsurkunde"
               and "persönlich übergeben" in a["dokument"]]
        self.assertTrue(ids)
        zeilen = []
        for i in ids:
            a = NACH_ID[i]
            f, _ = K.orakel_felder(a)
            f.update(zustellart="persoenliche_uebergabe", datum_zugang=f["datum_zustellung"], datum_zustellung=None)
            ant = K.rechne(f, a["typ"], a["frage"])["antwort"]
            self.assertTrue(K.ist_exakt(a, ant), i)
            diffs = fehleranalyse.vergleiche(a, f)
            self.assertEqual({d["feld"] for d in diffs}, {"zustellart", "datum_zustellung"}, i)
            self.assertTrue(all(d["gleichwertig"] and not d["noetig"] for d in diffs), i)
            zeilen.append({"id": i, "lauf": 1, "felder": f, "antwort_json": ant})
        an = fehleranalyse.analysiere(NACH_ID, zeilen, laeufe=1)
        self.assertEqual(an["felder"]["zustellart"]["falsch"], len(ids))
        self.assertEqual(an["felder"]["zustellart"]["falsch_noetig"], 0)
        self.assertEqual(an["felder"]["zustellart"]["gleichwertig"], len(ids))
        self.assertIn("(gleichwertig)", fehleranalyse.markdown({"x": an}))
        # eine echte Abweichung bleibt nötig
        a = NACH_ID[ids[0]]
        f, _ = K.orakel_felder(a)
        f["datum_zustellung"] = "2020-01-02"
        self.assertTrue(all(d["noetig"] and not d["gleichwertig"] for d in fehleranalyse.vergleiche(a, f)))


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class OllamaNachgebaut(unittest.TestCase):
    """kette.py gegen einen nachgebauten Ollama-Server (HTTP über urlopen)."""

    def setUp(self):
        self.anfragen = []
        self.schema_ablehnen = False

    def _urlopen(self, req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        body = json.loads(req.data) if not isinstance(req, str) and req.data else None
        self.anfragen.append((url, body))
        if url.endswith("/api/tags"):
            return _Antwort(json.dumps({"models": [{"name": "fake:1b", "model": "fake:1b"},
                                                   {"name": "qwen3:4b", "model": "qwen3:4b"}]}).encode())
        if url.endswith("/api/chat"):
            if self.schema_ablehnen and isinstance(body["format"], dict):
                raise urllib.error.HTTPError(url, 400, "Bad Request", {},
                                             io.BytesIO(b'{"error":"invalid JSON schema in format"}'))
            a = _aufgabe_aus_nachricht(body["messages"])
            if a["id"] == "F002":
                raise socket.timeout("timed out")
            inhalt = ("kein JSON" if a["id"] == "F003"
                      else json.dumps(K.als_modellausgabe(K.orakel_felder(a)[0]), ensure_ascii=False))
            return _Antwort(json.dumps({"message": {"content": inhalt, "thinking": None}, "eval_count": 100,
                                        "eval_duration": 4_000_000_000}).encode())
        raise AssertionError(url)

    def test_schema_abgelehnt_weiter_mit_json_und_robust_bei_fehlern(self):
        self.schema_ablehnen = True
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", self._urlopen), \
                mock.patch("builtins.print"), mock.patch("sys.stderr", io.StringIO()):
            rc = K.main(["--modelle", "fake:1b", "fehlt:7b", "--laeufe", "1", "--ids", "F001", "F002", "F003",
                         "--ausgabe-dir", tmp, "--datum", "2026-10-15"])
            self.assertEqual(rc, 0)
            pfad = Path(tmp) / "2026-10-15-fake-1b+rechner-v3.jsonl"
            zeilen = {z["id"]: z for z in map(json.loads, pfad.read_text("utf-8").splitlines())}
            self.assertEqual(set(zeilen), {"F001", "F002", "F003"})
            self.assertEqual(zeilen["F001"]["format"], "json")
            self.assertTrue(K.ist_exakt(NACH_ID["F001"], zeilen["F001"]["antwort_json"]))
            self.assertEqual(zeilen["F001"]["tokens_pro_s"], 25.0)
            self.assertIn("Zeitüberschreitung", zeilen["F002"]["fehler"])
            self.assertIsNone(zeilen["F003"]["felder"])
            chats = [b for u, b in self.anfragen if u.endswith("/api/chat")]
            self.assertIsInstance(chats[0]["format"], dict)        # erst mit Schema
            self.assertTrue(all(b["format"] == "json" for b in chats[1:]))  # danach ohne
            self.assertTrue(all(b["stream"] is False for b in chats))
            self.assertFalse(any("fehlt:7b" == b["model"] for b in chats))
            # Fortsetzen: nur die fehlerhafte Zeile (F002) wird neu abgefragt
            vorher = len(self.anfragen)
            K.main(["--modelle", "fake:1b", "--laeufe", "1", "--ids", "F001", "F002", "F003",
                    "--ausgabe-dir", tmp, "--datum", "2026-10-15"])
            neu = [b for u, b in self.anfragen[vorher:] if u.endswith("/api/chat")]
            self.assertEqual({_aufgabe_aus_nachricht(b["messages"])["id"] for b in neu}, {"F002"})

    def test_schema_und_denkschalter(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", self._urlopen), \
                mock.patch("builtins.print"):
            K.main(["--modelle", "qwen3:4b", "--laeufe", "1", "--ids", "F001", "--ausgabe-dir", tmp,
                    "--datum", "2026-10-15"])
            K.main(["--modelle", "fake:1b", "--laeufe", "1", "--ids", "F001", "--think", "--ausgabe-dir", tmp,
                    "--datum", "2026-10-15"])
            chats = [b for u, b in self.anfragen if u.endswith("/api/chat")]
            self.assertEqual(chats[0]["format"], PK.SCHEMA)
            self.assertIs(chats[0]["think"], False)
            self.assertIs(chats[1]["think"], True)
            z = json.loads((Path(tmp) / "2026-10-15-qwen3-4b+rechner-v3.jsonl").read_text("utf-8"))
            self.assertEqual((z["modell"], z["auslese_modell"], z["format"]),
                             ("qwen3:4b+rechner-v3", "qwen3:4b", "schema"))

    def test_schonmodus_pause_nach_jeder_aufgabe(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", self._urlopen), \
                mock.patch("builtins.print"), mock.patch.object(K.time, "sleep") as schlaf:
            K.main(["--modelle", "fake:1b", "--laeufe", "1", "--ids", "F001", "F004", "--pause", "2.5",
                    "--ausgabe-dir", tmp, "--datum", "2026-10-15"])
            self.assertEqual(schlaf.call_args_list, [mock.call(2.5), mock.call(2.5)])
            schlaf.reset_mock()
            K.main(["--modelle", "fake:1b", "--laeufe", "1", "--ids", "F002", "--ausgabe-dir", tmp,
                    "--datum", "2026-10-15"])
            schlaf.assert_not_called()                     # Standard: keine Pause
            K.main(["--orakel", "--laeufe", "1", "--ids", "F001", "--pause", "2", "--ausgabe-dir", tmp,
                    "--datum", "2026-10-15"])
            schlaf.assert_not_called()                     # Orakel ruft kein Modell, braucht keine Pause

    def test_server_nicht_erreichbar(self):
        def weg(*a, **k):
            raise urllib.error.URLError("Connection refused")
        with mock.patch("urllib.request.urlopen", weg), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(K.main(["--laeufe", "1"]), 2)


# ======================================================================== v3: Gegenproben, Nachfrage, Holdout

def _v3(a: dict, **aenderungen) -> dict:
    """Orakel-Felder einer Aufgabe in Modellschreibweise, mit absichtlich geänderten Feldern, durch die v3-Kette
    (ohne Nachfrage-Aufruf)."""
    roh = K.als_modellausgabe(K.orakel_felder(a)[0])
    roh.update(aenderungen)
    return K.verarbeite(a, json.dumps(roh, ensure_ascii=False), "v3")


def _regeln(teil) -> list[str]:
    return [e["regel"] for e in teil["gegenproben"]]


class GegenprobeV3(unittest.TestCase):
    def test_keine_regel_widerspricht_den_wahren_feldern(self):
        for a in AUFGABEN:
            f, _ = K.orakel_felder(a)
            g = K.gegenpruefe(f, a["dokument"], a["frage"], a["typ"])
            self.assertEqual(g["gegenproben"], [], a["id"])
            self.assertEqual(g["felder"], f, a["id"])
            self.assertEqual((g["annahmen"], g["zweifel"], g["unlesbar"]), ([], [], []), a["id"])

    def test_jede_regel_hat_eine_norm(self):
        self.assertEqual(set(K.REGELN), {"D1", "D2", "V", "S", "B", "Z", "N", "P"})
        for r, inhalt in K.REGELN.items():
            self.assertTrue(inhalt["text"] and inhalt["norm"], r)
            if r not in ("D1", "N"):        # Leseregeln ohne Rechtsnorm
                self.assertRegex(inhalt["norm"], r"§ \d+", r)

    def test_verfahren_aus_dem_gericht(self):
        for i, falsch, richtig, norm in (("F011", "SGB X", "VwVfG", "§ 40 Abs. 1 VwGO"),
                                         ("F034", "VwVfG", "SGB X", "§ 51 Abs. 1 SGG"),
                                         ("F042", "AO", "SGB X", "§ 51 Abs. 1 SGG")):
            a = NACH_ID[i]
            z = _v3(a, verfahren=falsch)
            self.assertTrue(K.ist_exakt(a, z["antwort_json"]), i)
            self.assertEqual(z["antwort_json"]["sicherheit"], K.MIT_ANNAHME, i)
            self.assertEqual(z["felder"]["verfahren"], richtig, i)
            self.assertEqual(z["felder_auslese"]["verfahren"], falsch, i)
            e = next(e for e in z["gegenproben"] if e["regel"] == "V")
            self.assertEqual((e["gelesen"], e["gesetzt"]), (falsch, richtig), i)
            self.assertIn(norm, e["norm"])
            self.assertIn("Gericht", e["grund"])

    def test_verfahren_aus_dem_rechtsbehelf(self):
        # Befund qwen3:4b (F050): verfahren AO bei einem Widerspruch; die Art der Auslese passt zum Dokument
        a = NACH_ID["F050"]
        z = _v3(a, verfahren="AO")
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual((z["felder"]["verfahren"], z["antwort_json"]["sicherheit"]), ("VwVfG", K.MIT_ANNAHME))
        a = NACH_ID["F004"]      # Einspruch -> AO
        z = _v3(a, verfahren="VwVfG", art="widerspruch_vwvfg")
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(z["felder"]["verfahren"], "AO")
        a = NACH_ID["F026"]      # ohne Belehrung: der Rechtsbehelf steht in der Frage
        z = _v3(a, verfahren="SGB X")
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(_regeln(z), ["V"])

    def test_verfahren_ohne_beleg_bleibt_wie_gelesen(self):
        # Ehrliche Grenze: Bei einem Widerspruch ohne Gericht und ohne Gesetz im Dokument kann der Code SGB X und
        # VwVfG nicht unterscheiden (F013, F050 in den v2-Läufen). Dann gilt die Auslese, keine erfundene Regel.
        a = NACH_ID["F013"]
        z = _v3(a, verfahren="SGB X", art="widerspruch_sgb2")
        self.assertEqual(_regeln(z), [])
        self.assertEqual((z["felder"]["verfahren"], z["rechnung"]["art"]), ("SGB X", "widerspruch_sgb2"))
        menge, quellen, _ = K.verfahren_aus_dokument(a["dokument"], a["frage"])
        self.assertEqual((menge, quellen), ({"SGB X", "VwVfG"}, ["Rechtsbehelf Widerspruch"]))
        z = _v3(a, verfahren=None)          # nicht gelesen: Art der Auslese entscheidet, ohne Annahme
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(z["felder"]["verfahren"], "VwVfG")

    def test_staerkere_quelle_gewinnt(self):
        def doc(belehrung, rest=""):
            return f"Bescheid\n{rest}\n\nRechtsbehelfsbelehrung\n{belehrung}\n"
        klage_sg = "Gegen diesen Bescheid kann innerhalb eines Monats Klage beim Sozialgericht erhoben werden."
        self.assertEqual(K.verfahren_aus_dokument(doc(klage_sg, "Rechtsgrundlage: § 49 VwVfG"))[0], {"SGB X"})
        wider = "Gegen diesen Bescheid ist innerhalb eines Monats der Widerspruch gegeben."
        self.assertEqual(K.verfahren_aus_dokument(doc(wider, "Rechtsgrundlage: § 48 SGB X"))[0], {"SGB X"})
        ein = "Gegen diesen Bescheid ist der Einspruch gegeben. Die Einspruchsfrist beträgt einen Monat."
        menge, quellen, _ = K.verfahren_aus_dokument(doc(ein, "nach § 48 SGB X"))
        self.assertEqual((menge, quellen), ({"AO"}, ["Rechtsbehelf Einspruch"]))
        zwei = "Klage beim Sozialgericht oder beim Verwaltungsgericht innerhalb eines Monats."
        self.assertIsNone(K.verfahren_aus_dokument(doc(zwei))[0])
        self.assertIsNone(K.verfahren_aus_dokument("Kein Hinweis.")[0])

    def test_schreiben_aus_dem_rechtsbehelf(self):
        # Befund gemma3:4b (F027, F049): Ausgangsbescheid als Widerspruchsbescheid gelesen
        for i, falsch, richtig in (("F027", "widerspruchsbescheid", "bescheid"),
                                   ("F034", "bescheid", "widerspruchsbescheid")):
            a = NACH_ID[i]
            z = _v3(a, schreiben=falsch)
            self.assertTrue(K.ist_exakt(a, z["antwort_json"]), i)
            self.assertEqual(z["felder"]["schreiben"], richtig, i)
            self.assertIn("S", _regeln(z))
            self.assertEqual(z["antwort_json"]["sicherheit"], K.MIT_ANNAHME)
        self.assertIsNone(K.schreiben_aus_dokument(NACH_ID["F049"]["dokument"], NACH_ID["F049"]["frage"]))

    def test_rechtsbehelfsbelehrung_braucht_rechtsbehelf_und_frist(self):
        # Befund qwen3:8b (F049): „vorhanden“, obwohl der Bescheid keine Belehrung enthält
        a = NACH_ID["F049"]
        z = _v3(a, rechtsbehelfsbelehrung="vorhanden")
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual((z["felder"]["rechtsbehelfsbelehrung"], z["antwort_json"]["sicherheit"]),
                         ("fehlt", K.MIT_ANNAHME))
        a = NACH_ID["F001"]      # „fehlt“ gelesen, Belehrung unter eigener Überschrift: gilt als vorhanden
        z = _v3(a, rechtsbehelfsbelehrung="fehlt")
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual((z["felder"]["rechtsbehelfsbelehrung"], z["antwort_json"]["sicherheit"]),
                         ("vorhanden", K.MIT_ANNAHME))
        self.assertIn("B", _regeln(z))
        ohne_kopf = dict(a, dokument=a["dokument"].replace("Rechtsbehelfsbelehrung\n", ""))
        self.assertFalse(K.belehrung_unter_ueberschrift(ohne_kopf["dokument"]))
        z = _v3(ohne_kopf, rechtsbehelfsbelehrung="fehlt")   # Rechtsbehelf und Frist ohne Überschrift: nur Zweifel
        self.assertEqual(z["felder"]["rechtsbehelfsbelehrung"], "fehlt")
        self.assertLessEqual(z["antwort_json"]["sicherheit"], K.MIT_ANNAHME)
        self.assertTrue(z["rechnung"]["zweifel"])
        z = _v3(a, rechtsbehelfsbelehrung=None)   # nicht gelesen, Belehrung mit Frist im Dokument: ohne Annahme
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(z["antwort_json"]["sicherheit"], K.SICHER)
        self.assertEqual(K.rechne(K.orakel_felder(a)[0] | {"rechtsbehelfsbelehrung": None}, a["typ"], a["frage"])
                         ["antwort"]["sicherheit"], K.MIT_ANNAHME)          # v2-Weg: Annahme „vorhanden“
        stellen, kopf = K.belehrung("Rechtsbehelfsbelehrung\nWiderspruch ist bei der Behörde einzulegen.\n")
        self.assertTrue(kopf)
        self.assertFalse(K._mit_frist(stellen))      # ohne Frist keine vollständige Belehrung

    def test_belehrung_unter_eigener_ueberschrift(self):
        # Befund qwen3:8b (Seed 20261018, F047, 3 von 3 Läufen): „fehlt“ trotz Überschrift mit Klage, Gericht und
        # Monatsfrist; neben der Belehrung ein Beratungsvermerk mit eigenem Fristende. Die Nein-Fälle stammen aus
        # der Gegenprüfung 17.10.2026 (Vermerke Dritter, Verneinung, falsche Frist, keine Stelle).
        klage = ("Gegen diesen Widerspruchsbescheid kann innerhalb eines Monats nach Bekanntgabe Klage beim "
                 "Sozialgericht Erzbrunn erhoben werden.")
        ja = (f"Widerspruchsbescheid\n\nRechtsbehelfsbelehrung\n{klage}\n\nPostausgangsvermerk: zur Post gegeben",
              f"Bescheid\n\nRechtsmittelbelehrung:\n\n{klage}\n",          # Leerzeile nach der Überschrift
              f"Bescheid\nRechtsbehelfsbelehrung: {klage}\n",                # Text hinter dem Doppelpunkt
              f"Bescheid\n\n3. Rechtsbehelfsbelehrung\n{klage}\n",          # nummeriert
              f"Bescheid\n\n**Rechtsbehelfsbelehrung**\n{klage}\n",         # fett
              f"Bescheid\n\nRechtsbehelfsbelehrung (§ 66 SGG)\n{klage}\n",  # Klammerzusatz
              "Bescheid\n\nRechtsbehelfsbelehrung\nDer Einspruch ist beim Finanzamt einzulegen.\n"
              "Die Einspruchsfrist beträgt einen Monat.\n",
              "Bescheid\n\nRechtsbehelfsbelehrung\nDer Bescheid kann innerhalb eines Monates nach Bekanntgabe mit dem "
              "Einspruch angefochten werden.\n\nDer Einspruch ist beim Finanzamt Havelufer einzulegen.\n",  # zwei Absätze
              "Bescheid\n\nRechtsbehelfsbelehrung\nGegen diesen Bescheid ist der Widerspruch gegeben. Der Widerspruch "
              "hat keine aufschiebende Wirkung.\nEr ist innerhalb eines Monats bei der Behörde einzulegen.\n")
        nein = (f"Bescheid\n\n— Vermerk: Beratung —\n{klage}\n",              # nur Anmerkung, keine Überschrift
                f"Bescheid\n\n— Vermerk —\nDie Rechtsbehelfsbelehrung fehlt. {klage}\n",   # Satz, keine Überschrift
                "Bescheid\n\nRechtsbehelfsbelehrung\nWiderspruch ist bei der Behörde einzulegen.\n",   # ohne Frist
                "Bescheid\n\nRechtsbehelfsbelehrung\nWiderspruch ist innerhalb eines Monats zulässig.\n",  # ohne Stelle
                f"Bescheid\nRechtsbehelfsbelehrung: siehe Rückseite\n\n— Vermerk —\n{klage}\n",  # Absatz endet
                f"Bescheid\nIm Auftrag · Muster\n\n— Vermerk: Kanzlei —\nRechtsbehelfsbelehrung: {klage}\n",
                f"Bescheid\nIm Auftrag · Muster\nRechtsbehelfsbelehrung\n\n— Vermerk: Beratung —\n{klage}\n",
                f"Bescheid\nRechtsbehelfsbelehrung: nicht erteilt\n{klage}\n",
                "Bescheid\n\nRechtsbehelfsbelehrung\nEine Rechtsbehelfsbelehrung wurde nicht erteilt. Der Widerspruch "
                "ist daher bei der Behörde innerhalb eines Jahres einzulegen.\n",
                "Bescheid\n\nRechtsbehelfsbelehrung\nDer Einspruch ist beim Finanzamt innerhalb von zwei Wochen "
                "einzulegen.\n",                                                   # falsche Frist
                "Bescheid\n\nRechtsbehelfsbelehrung\nDer Einspruch ist innerhalb eines Monats zulässig. Bei Fragen "
                "rufen Sie uns an.\n")                                             # keine Stelle
        for d in ja:
            self.assertTrue(K.belehrung_unter_ueberschrift(d), d)
        for d in nein:
            self.assertFalse(K.belehrung_unter_ueberschrift(d), d)
        # Überschrift ohne vollständige Belehrung, Auslese „fehlt“: Wert bleibt, aber nie sicher
        a = NACH_ID["F001"]
        ohne_frist = dict(a, dokument=re.sub(r"Rechtsbehelfsbelehrung\n(?:.+\n)+", "Rechtsbehelfsbelehrung\nSiehe Rückseite.\n",
                                             a["dokument"], count=1))
        self.assertNotEqual(ohne_frist["dokument"], a["dokument"])
        z = _v3(ohne_frist, rechtsbehelfsbelehrung="fehlt")
        self.assertEqual(z["felder"]["rechtsbehelfsbelehrung"], "fehlt")
        self.assertTrue(z["rechnung"]["zweifel"])

    def test_datum_muss_im_dokument_stehen(self):
        # Befund qwen3:8b (F035): genanntes Fristende „berichtigt“ statt abgeschrieben
        a = NACH_ID["F035"]
        z = _v3(a, genanntes_fristende="20.11.2025")
        self.assertEqual(_regeln(z), ["D1"])
        self.assertEqual(z["antwort_json"]["antwortart"], "rueckfrage")
        self.assertEqual(K.nachfrage_feld(z["rechnung"]), "genanntes_fristende")
        self.assertIn("genanntes_fristende", z["rechnung"]["unlesbar"])
        self.assertEqual(K.datumsangaben("am 1. Juli 2019, 2.7.19 und 2019-07-03; Betrag 2.890,64 EUR"),
                         {"2019-07-01": 1, "2019-07-02": 1, "2019-07-03": 1})

    def test_ein_einmal_genanntes_datum_belegt_nur_ein_ereignis(self):
        a = NACH_ID["F002"]      # Rückfrage-Aufgabe: Zugang aus dem Datum des Schreibens wäre geraten
        datum = K.als_modellausgabe(K.orakel_felder(a)[0])["datum_schreiben"]
        z = _v3(a, datum_zugang=datum)
        self.assertEqual(_regeln(z), ["D2"])
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        self.assertEqual(z["felder"]["datum_schreiben"], K.orakel_felder(a)[0]["datum_schreiben"])
        a = NACH_ID["F003"]      # Zugang und Beschäftigungsbeginn, ein Datum: der Zugang wird nachgefragt
        zugang = K.als_modellausgabe(K.orakel_felder(a)[0])["datum_zugang"]
        roh = K.als_modellausgabe(K.orakel_felder(a)[0]) | {"beschaeftigungsbeginn": zugang}
        z = _v3(a, beschaeftigungsbeginn=zugang)
        self.assertEqual([e["feld"] for e in z["gegenproben"]], ["datum_zugang"])
        self.assertEqual(K.nachfrage_feld(z["rechnung"]), "datum_zugang")
        z = K.verarbeite(a, json.dumps(roh), "v3",
                         nachfrage=("datum_zugang", json.dumps(K.orakel_nachfrage(a, "datum_zugang"))))
        self.assertEqual([e["feld"] for e in z["gegenproben"]], ["datum_zugang", "beschaeftigungsbeginn"])
        self.assertEqual(z["felder"]["datum_zugang"], K.orakel_felder(a)[0]["datum_zugang"])   # Nachfrage geht vor
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))      # Beginn fehlt: Rückfrage (Sollwert)
        a = NACH_ID["F046"]      # Zugang und genanntes Fristende, ein Datum: das Fristende bleibt
        roh = K.als_modellausgabe(K.orakel_felder(a)[0])
        z = _v3(a, datum_zugang=roh["genanntes_fristende"])
        self.assertEqual([e["feld"] for e in z["gegenproben"]], ["datum_zugang"])
        self.assertEqual(z["felder"]["genanntes_fristende"], K.orakel_felder(a)[0]["genanntes_fristende"])
        z = K.verarbeite(a, json.dumps(roh | {"datum_zugang": roh["genanntes_fristende"]}), "v3",
                         nachfrage=("datum_zugang", json.dumps(K.orakel_nachfrage(a, "datum_zugang"))))
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        a = NACH_ID["F002"]      # die Nachfrage geht nie dem Datum des Schreibens vor (auch mit gültiger Fundstelle)
        roh = K.als_modellausgabe(K.orakel_felder(a)[0])
        kopf = _zeile_mit(a, roh["datum_schreiben"])
        z = K.verarbeite(a, json.dumps(roh), "v3", nachfrage=("datum_zugang", json.dumps(
            {"fundstelle": kopf, "datum_zugang": roh["datum_schreiben"]})))
        self.assertEqual(_regeln(z), ["D2"])
        self.assertEqual((z["felder"]["datum_schreiben"], z["felder"]["datum_zugang"]),
                         (K.orakel_felder(a)[0]["datum_schreiben"], None))
        self.assertTrue(K.ist_exakt(a, z["antwort_json"]))
        a = NACH_ID["F001"]      # Datum des Bescheids und Absendetag: zweimal im Dokument, beides belegt
        z = _v3(a, datum_schreiben=K.als_modellausgabe(K.orakel_felder(a)[0])["datum_aufgabe_post"])
        self.assertEqual(_regeln(z), [])
        self.assertEqual(z["antwort_json"]["sicherheit"], K.SICHER)

    def test_zeitfolge_bei_pruefaufgaben(self):
        a = NACH_ID["F016"]
        f, _ = K.orakel_felder(a)
        f["genanntes_fristende"] = "2025-08-01"     # vor dem Zugang
        e, zweifel = K.pruefe_zeitfolge(f, "pruefen")
        self.assertEqual([x["regel"] for x in e], ["Z"])
        self.assertTrue(zweifel)
        self.assertEqual(K.pruefe_zeitfolge(f, "berechnen"), ([], []))
        g = K.gegenpruefe(f, a["dokument"], a["frage"], "pruefen")    # das Datum steht nicht im Dokument: D1 zuerst
        self.assertEqual(([x["regel"] for x in g["gegenproben"]], g["annahmen"]), (["D1"], []))

    def test_verfahren_gericht_bestimmt_den_rechtsweg_sonderfall_zweifel(self):
        # Gegenprüfer: Das Gericht bestimmt den Rechtsweg, nicht das Verfahrensgesetz. Ausbildungsförderung ist nach
        # § 68 SGB I Teil des SGB (also SGB X), der Rechtsweg führt aber zum Verwaltungsgericht. Der Rechner kennt nur
        # den Regelfall; der Widerspruch der Quellen senkt deshalb die Sicherheit.
        dok = ("Widerspruchsbescheid\nIhr Widerspruch gegen den Bescheid über Ausbildungsförderung nach dem BAföG "
               "wird zurückgewiesen.\n\nRechtsbehelfsbelehrung\nGegen den Bescheid in der Gestalt dieses "
               "Widerspruchsbescheids kann innerhalb eines Monats nach Zustellung Klage beim Verwaltungsgericht "
               "erhoben werden.\n")
        f = _felder(schreiben="widerspruchsbescheid", verfahren="SGB X")
        e, annahmen, zweifel = K.pruefe_recht(f, dok, "", "berechnen")
        self.assertEqual(f["verfahren"], "VwVfG")                  # Regelfall des Rechners: klage_vwgo
        self.assertIn("V", [x["regel"] for x in e])
        self.assertIn("Verwaltungsgericht", e[0]["grund"])
        self.assertTrue(any("widersprechen sich" in z for z in zweifel), zweifel)
        self.assertIn("§ 68 SGB I", K.REGELN["V"]["norm"])
        self.assertIn("Rechtsweg", K.REGELN["V"]["text"])
        # ohne Sonderfall-Hinweis: kein Zweifel
        f = _felder(schreiben="widerspruchsbescheid", verfahren="VwVfG")
        self.assertEqual(K.pruefe_recht(f, dok.replace("Ausbildungsförderung nach dem BAföG", "eine Gebühr"), "",
                                        "berechnen")[2], [])

    def test_d2_grenze_ereignis_am_tag_des_schreibens(self):
        # Gegenprüfer: D2 ist an echten Dokumenten ungeprüft. Ein Zugang am Tag des Schreibens, dessen Datum der Text
        # nicht wiederholt, gilt als nicht belegt. Folge ist eine Rückfrage mit 0,6, nie ein sicheres Ergebnis.
        dok = ("Muster Feinwerk GmbH · Am Werk 1, 10115 Berlin (Berlin)\n\nBerlin, 05.03.2027\n\n"
               "Kündigung des Arbeitsverhältnisses\nWir kündigen das Arbeitsverhältnis ordentlich.\n\n"
               "Das Original wurde am heutigen Tag persönlich übergeben.\nZuständig ist das Arbeitsgericht Berlin.")
        a = {"id": "T001", "typ": "berechnen", "dokument": dok,
             "frage": "Bis wann muss die Kündigungsschutzklage beim Arbeitsgericht eingehen?"}
        roh = _roh(schreiben="kuendigung_arbeitsverhaeltnis", art="kschg_klage", bundesland="Berlin",
                   datum_schreiben="05.03.2027", datum_zugang="05.03.2027", kuendigende_partei="arbeitgeber")
        z = K.verarbeite(a, json.dumps(roh), "v3")
        self.assertEqual(_regeln(z), ["D2"])
        self.assertEqual((z["antwort_json"]["antwortart"], z["antwort_json"]["sicherheit"]),
                         ("rueckfrage", K.RUECKFRAGE_FELD))
        antwort = {"fundstelle": "Das Original wurde am heutigen Tag persönlich übergeben.",
                   "datum_zugang": "05.03.2027"}
        z = K.verarbeite(a, json.dumps(roh), "v3", nachfrage=("datum_zugang", json.dumps(antwort)))
        self.assertEqual(_regeln(z), ["D2", "N"])                 # Datum steht nicht in der Fundstelle
        self.assertEqual((z["antwort_json"]["antwortart"], z["antwort_json"]["sicherheit"]),
                         ("rueckfrage", K.RUECKFRAGE_FELD))

    def test_ohne_gegenprobe_wie_gelesen(self):
        a = NACH_ID["F049"]
        roh = K.als_modellausgabe(K.orakel_felder(a)[0]) | {"rechtsbehelfsbelehrung": "vorhanden"}
        z = K.verarbeite(a, json.dumps(roh, ensure_ascii=False), "v3", gegenprobe=False)
        self.assertEqual(z["gegenproben"], [])
        self.assertFalse(K.ist_exakt(a, z["antwort_json"]))


class _StubV3:
    """Modell-Stub für v3: erste Auslese = wahre Felder mit absichtlichen Änderungen; Nachfrage = ``nachfrage``
    (Standard: der wahre Wert des gefragten Felds mit seiner Zeile als Fundstelle, wie K.orakel_nachfrage)."""

    def __init__(self, falsch: dict | None = None, nachfrage=None, fehler_bei_nachfrage=None):
        self.falsch = falsch or {}
        self.nachfrage = nachfrage
        self.fehler_bei_nachfrage = fehler_bei_nachfrage
        self.aufrufe = []

    @staticmethod
    def feld_der_nachfrage(a, nachrichten) -> str:
        return next(f for f in PK.NACHFRAGEN if PK.nachfrage_nachrichten(a, f) == nachrichten)

    def __call__(self, host, modell, nachrichten, *, think, timeout, optionen, format_="json", keep_alive="10m"):
        a = _aufgabe_aus_nachricht(nachrichten)
        wahr = K.als_modellausgabe(K.orakel_felder(a)[0])
        if nachrichten[0]["content"] == PK.NACHFRAGE_SYSTEM:
            feld = self.feld_der_nachfrage(a, nachrichten)
            self.aufrufe.append(("nachfrage", a["id"], feld, format_))
            if self.fehler_bei_nachfrage:
                raise self.fehler_bei_nachfrage
            if self.nachfrage is not None:
                inhalt = self.nachfrage(a, feld, wahr)
            else:      # wie das Orakel: wahrer Wert, Fundstelle = Zeile des Dokuments, in der er steht
                inhalt = K.orakel_nachfrage(a, feld)
            return {"message": {"content": json.dumps(inhalt, ensure_ascii=False)}, "eval_count": 20,
                    "eval_duration": 1_000_000_000, "total_duration": 1_500_000_000}
        self.aufrufe.append(("auslese", a["id"], None, format_))
        roh = dict(wahr)
        for feld, wert in self.falsch.get(a["id"], {}).items():
            roh[feld] = wert(wahr) if callable(wert) else wert
        return {"message": {"content": json.dumps(roh, ensure_ascii=False)}, "eval_count": 60,
                "eval_duration": 2_000_000_000, "total_duration": 3_000_000_000}


def _zeilen(tmp, name) -> dict:
    datei = Path(tmp) / f"2026-10-15-{K.RO.dateiname(name)}.jsonl"
    return {(z["id"], z["lauf"]): z for z in map(json.loads, datei.read_text("utf-8").splitlines())}


class NachfrageV3(unittest.TestCase):
    def _lauf(self, stub, ids, *extra, laeufe=1):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            rc = K.main(["--modelle", "stub:1b", "--laeufe", str(laeufe), "--ids", *ids, "--ausgabe-dir", tmp,
                         "--datum", "2026-10-15", *extra], chat_fn=stub)
            self.assertEqual(rc, 0)
            namen = [p.name for p in Path(tmp).glob("*.jsonl")]
            self.assertEqual(len(namen), 1)
            name = json.loads(Path(tmp, namen[0]).read_text("utf-8").splitlines()[0])["modell"]
            return name, _zeilen(tmp, name), _bewerte(tmp, laeufe)[name]

    def test_null_dann_datum_auf_nachfrage(self):
        # Stub liest beim ersten Mal den Zugang nicht (null) und liefert ihn auf die Nachfrage
        stub = _StubV3({"F020": {"datum_zugang": None}})
        name, zeilen, rang = self._lauf(stub, ["F020"])
        self.assertEqual(name, "stub:1b+rechner-v3")
        z = zeilen[("F020", 1)]
        self.assertEqual([x[0] for x in stub.aufrufe], ["auslese", "nachfrage"])
        self.assertEqual(stub.aufrufe[1][2:], ("datum_zugang", PK.nachfrage_schema("datum_zugang")))
        self.assertEqual(z["aufrufe"], 2)
        self.assertEqual((z["nachfrage"]["feld"], z["nachfrage"]["uebernommen"]), ("datum_zugang", ["datum_zugang"]))
        self.assertIn("dauer_s", z["nachfrage"])
        self.assertEqual((z["nachfrage"]["eval_count"], z["eval_count_alle"]), (20, 80))
        self.assertGreaterEqual(z["dauer_s"], z["nachfrage"]["dauer_s"])
        self.assertIsNone(z["felder_auslese"]["datum_zugang"])
        self.assertEqual(z["felder"]["datum_zugang"], NACH_ID["F020"]["parameter"]["argumente"]["zugang"])
        self.assertTrue(K.ist_exakt(NACH_ID["F020"], z["antwort_json"]))
        self.assertEqual(z["antwort_json"]["sicherheit"], K.MIT_ANNAHME)       # erst auf Nachfrage gelesen
        self.assertIn("datum_zugang erst auf Nachfrage gelesen", z["rechnung"]["annahmen"])
        self.assertEqual(rang["pro_aufgabe"]["F020"], "1/1")

    def test_nachfrage_ohne_wert_bleibt_rueckfrage(self):
        stub = _StubV3({"F020": {"datum_zugang": None}}, nachfrage=lambda a, f, w: {"fundstelle": None, f: None})
        _, zeilen, rang = self._lauf(stub, ["F020"])
        z = zeilen[("F020", 1)]
        self.assertEqual((z["aufrufe"], z["nachfrage"]["uebernommen"]), (2, []))
        self.assertEqual(z["antwort_json"]["antwortart"], "rueckfrage")
        self.assertEqual(rang["pro_aufgabe"]["F020"], "0/1")

    def test_geratenes_datum_auf_nachfrage_wird_verworfen(self):
        # Rückfrage-Aufgabe: Das Modell nennt auf Nachfrage das Datum des Schreibens als Zugang (D2)
        stub = _StubV3(nachfrage=lambda a, f, w: {"fundstelle": _zeile_mit(a, w["datum_schreiben"]),
                                                  f: w["datum_schreiben"]})
        _, zeilen, rang = self._lauf(stub, ["F002"])
        z = zeilen[("F002", 1)]
        self.assertEqual((z["nachfrage"]["feld"], z["nachfrage"]["uebernommen"]), ("datum_zugang", []))
        self.assertIn("D2", [e["regel"] for e in z["gegenproben"]])
        self.assertEqual(rang["pro_aufgabe"]["F002"], "1/1")

    def test_hoechstens_eine_nachfrage_je_aufgabe(self):
        stub = _StubV3({"F031": {"datum_zugang": None, "ueberlassung": None}})
        _, zeilen, rang = self._lauf(stub, ["F031"], laeufe=2)
        self.assertEqual([x[:3] for x in stub.aufrufe],
                         [("auslese", "F031", None), ("nachfrage", "F031", "datum_zugang")] * 2)
        for lauf in (1, 2):
            z = zeilen[("F031", lauf)]
            self.assertEqual(z["aufrufe"], 2)
            self.assertEqual(z["rechnung"]["fehlend"], ["ueberlassung"])
            self.assertEqual(z["antwort_json"]["antwortart"], "rueckfrage")
        self.assertEqual(rang["pro_aufgabe"]["F031"], "0/2")

    def test_zustellart_und_tag_in_einer_nachfrage(self):
        stub = _StubV3({"F001": {"zustellart": None, "datum_aufgabe_post": None}})
        _, zeilen, _ = self._lauf(stub, ["F001"])
        z = zeilen[("F001", 1)]
        self.assertEqual(z["nachfrage"]["feld"], "zustellart")
        self.assertEqual(sorted(z["nachfrage"]["uebernommen"]), ["datum_aufgabe_post", "zustellart"])
        self.assertTrue(K.ist_exakt(NACH_ID["F001"], z["antwort_json"]))

    def test_ohne_nachfrage_v2_und_json(self):
        falsch = {"F020": {"datum_zugang": None}}
        stub = _StubV3(falsch)
        name, zeilen, _ = self._lauf(stub, ["F020"], "--ohne-nachfrage")
        self.assertEqual((name, len(stub.aufrufe)), ("stub:1b+rechner-v3-ohne-nachfrage", 1))
        self.assertEqual((zeilen[("F020", 1)]["aufrufe"], zeilen[("F020", 1)]["nachfrage"]), (1, None))
        stub = _StubV3(falsch)
        name, zeilen, _ = self._lauf(stub, ["F020"], "--prompt-version", "v2")
        self.assertEqual((name, len(stub.aufrufe)), ("stub:1b+rechner", 1))
        self.assertNotIn("nachfrage", zeilen[("F020", 1)])
        stub = _StubV3(falsch)
        name, zeilen, _ = self._lauf(stub, ["F020"], "--format", "json")
        self.assertEqual(name, "stub:1b+rechner-v3-json")
        self.assertEqual([x[3] for x in stub.aufrufe], ["json", "json"])
        self.assertTrue(K.ist_exakt(NACH_ID["F020"], zeilen[("F020", 1)]["antwort_json"]))
        stub = _StubV3({"F049": {"rechtsbehelfsbelehrung": "vorhanden"}})
        name, zeilen, _ = self._lauf(stub, ["F049"], "--ohne-gegenprobe")
        self.assertEqual(name, "stub:1b+rechner-v3-ohne-gegenprobe")
        self.assertFalse(K.ist_exakt(NACH_ID["F049"], zeilen[("F049", 1)]["antwort_json"]))

    def test_nachfrage_braucht_fundstelle_regel_n(self):
        # Befund Gegenprüfer: Die Fundstelle wurde nie geprüft; ein geratenes Datum aus dem Dokument kam durch.
        werte, info = K.lies_nachfrage("datum_zugang", '{"fundstelle": null, "datum_zugang": "03.02.2027"}', "x")
        self.assertEqual((werte, info["verworfen"][0]["grund"]), ({}, "keine Fundstelle angegeben"))
        self.assertEqual(K.lies_nachfrage("datum_zugang", '{"fundstelle": null, "datum_zugang": "03.02.2027"}')[0],
                         {"datum_zugang": "2027-02-03"})           # ohne Dokument (ohne Gegenprobe): wie gelesen
        for i, feld in (("F002", "datum_zugang"), ("F003", "beschaeftigungsbeginn")):   # Rückfrage-Aufgaben
            a = NACH_ID[i]
            wahr = K.als_modellausgabe(K.orakel_felder(a)[0])
            geraten = next(d for d in sorted(K.datumsangaben(a["dokument"])) if d != K.orakel_felder(a)[0][
                "datum_schreiben"])
            gd = K.ds(geraten)
            andere = next(z.strip() for z in a["dokument"].splitlines() if z.strip() and gd not in z and
                          not K.datumsangaben(z))
            for fund, grund in ((None, "keine Fundstelle angegeben"),
                                ("Das steht so nirgends im Schreiben", "Fundstelle steht nicht wörtlich im Dokument"),
                                (gd, "Fundstelle enthält nur ein Datum"),
                                (andere, "Datum steht nicht in der Fundstelle")):
                z = K.verarbeite(a, json.dumps(wahr), "v3", nachfrage=(feld, json.dumps({"fundstelle": fund,
                                                                                         feld: gd})))
                self.assertEqual(z["antwort_json"]["antwortart"], "rueckfrage", (i, fund))
                n = [e for e in z["gegenproben"] if e["regel"] == "N"]
                self.assertEqual([(e["feld"], e["gelesen"], e["grund"]) for e in n], [(feld, geraten, grund)],
                                 (i, fund))
                z = K.verarbeite(a, json.dumps(wahr), "v3", gegenprobe=False,
                                 nachfrage=(feld, json.dumps({"fundstelle": fund, feld: gd})))
                self.assertNotEqual(z["antwort_json"]["antwortart"], "rueckfrage", (i, fund))   # ohne Regel N
        # tragende Fundstelle: Groß/Klein, Leerraum, Anführungszeichen und Auslassungen sind egal
        a = NACH_ID["F020"]
        zugang = K.als_modellausgabe(K.orakel_felder(a)[0])["datum_zugang"]
        zeile = _zeile_mit(a, zugang)
        worte = zeile.split()
        fund = "„" + " ".join(worte[:3]).upper() + "  … " + " ".join(worte[3:]) + "“"
        self.assertIsNone(K.fundstelle_mangel(fund, a["dokument"]), fund)
        werte, info = K.lies_nachfrage("datum_zugang", json.dumps({"fundstelle": fund, "datum_zugang": zugang}),
                                       a["dokument"])
        self.assertEqual((werte, info["verworfen"]), ({"datum_zugang": K.orakel_felder(a)[0]["datum_zugang"]}, []))

    def test_regel_p_wer_kuendigt(self):
        # Seed 20261016 F049 und fremd_probe D: Mieterin als Vermieterin gelesen
        self.assertEqual(K.partei_aus_dokument("hiermit kündige ich das Mietverhältnis über meine Wohnung"), "mieter")
        self.assertEqual(K.partei_aus_dokument("Ich bin seit 2021 Mieterin der Wohnung"), "mieter")
        self.assertEqual(K.partei_aus_dokument("wir kündigen Ihnen wegen Eigenbedarf"), "vermieter")
        self.assertIsNone(K.partei_aus_dokument("Kündigung zum nächstmöglichen Termin"))
        # Vorlagen v2, Entwicklungssatz F016: Betreff „Kündigung meines Mietvertrags“
        self.assertEqual(K.partei_aus_dokument("Kündigung meines Mietvertrags · Wohnung Birkenweg 118"), "mieter")
        self.assertIsNone(K.partei_aus_dokument("Kündigung meines Mietvertrags … wegen Eigenbedarfs"))  # widersprüchlich
        self.assertIsNone(K.partei_aus_dokument("meine Wohnung … Eigenbedarf"))          # widersprüchlich: Auslese bleibt
        f = {"schreiben": "kuendigung_mietverhaeltnis", "art": "kuendigung_miete", "kuendigende_partei": "vermieter"}
        eintraege, annahmen, _ = K.pruefe_recht(f, "kündige ich meine Wohnung", "", "berechnen")
        self.assertEqual((f["kuendigende_partei"], eintraege[0]["regel"]), ("mieter", "P"))
        self.assertTrue(annahmen)

    def test_d1_datum_nur_im_kopf_einer_anmerkung_dritter(self):
        # Seed 20261024 F012: Zustelldatum aus „— Vermerk: Sozialberatung …, 10.04.2025 —“
        dok = "Datum: 03.04.2025\nAb-Vermerk: ________\n— Vermerk: Sozialberatung Seebrügge e. V., 10.04.2025 —"
        f = {"datum_schreiben": "2025-04-03", "datum_zustellung": "2025-04-10"}
        eintraege, weg = K.pruefe_daten(f, dok)
        self.assertEqual(weg, ["datum_zustellung"])
        self.assertIsNone(f["datum_zustellung"])
        self.assertTrue(K.nur_in_anmerkung_dritter(dok, "2025-04-10"))
        self.assertFalse(K.nur_in_anmerkung_dritter(dok + "\nZugestellt am 10.04.2025", "2025-04-10"))

    def test_fundstelle_muss_zum_postdatum_passen(self):
        # Seed 20261016, F006: Datum eines Beratungsvermerks als „Aufgabe zur Post“ übernommen
        dok = ("Datum: 06.03.2026\n(Ein Vermerk über die Aufgabe zur Post liegt der Akte nicht bei.)\n"
               "— Vermerk: Erwerbslosenberatung Treenefeld, 11.03.2026 —\n"
               "Postausgangsvermerk: zur Post gegeben am 09.03.2026")
        fund = "— Vermerk: Erwerbslosenberatung Treenefeld, 11.03.2026 —"
        self.assertEqual(K.fundstelle_mangel(fund, dok, "datum_aufgabe_post"),
                         "Fundstelle passt nicht zu datum_aufgabe_post")
        # Seed 20261024 F012: Kopf einer Anmerkung Dritter trägt auch Zustellung und Zugang nicht
        self.assertIn("Anmerkung Dritter", K.fundstelle_mangel(fund, dok, "datum_zugang"))
        self.assertIn("Anmerkung Dritter", K.fundstelle_mangel(fund, dok, "datum_zustellung"))
        self.assertIsNone(K.fundstelle_mangel(fund, dok, "genanntes_fristende"))   # andere Felder unverändert
        self.assertIsNone(K.fundstelle_mangel("Hinweis der Beratungsstelle: Brief erhalten am 11.03.2026",
                                              dok + "\nHinweis der Beratungsstelle: Brief erhalten am 11.03.2026",
                                              "datum_zugang"))
        self.assertIsNone(K.fundstelle_mangel("Postausgangsvermerk: zur Post gegeben am 09.03.2026", dok,
                                              "datum_aufgabe_post"))
        werte, info = K.lies_nachfrage("datum_aufgabe_post", json.dumps(
            {"fundstelle": fund, "datum_aufgabe_post": "11.03.2026"}), dok)
        self.assertEqual(werte, {})

    def test_fundstelle_ersetzt_wenn_genau_eine_postzeile_das_datum_traegt(self):
        # Vorlagen v2, Seed 20261024, F016: richtiges Datum, aber die Postfach-Zeile als Fundstelle zitiert
        dok = ("[Stempel: Ab-Vermerk: am 30.03.2026 mit einfacher Post abgesandt · Yıl]\n\nFinanzamt Moselbrunn\n"
               "Finanzamt Moselbrunn · Postfach 7846 · 54053 Moselbrunn\nDatum: 27.03.2026\n"
               "Die Nachzahlung ist bis 26.04.2026 zu entrichten.")
        fund = "Finanzamt Moselbrunn · Postfach 7846 · 54053 Moselbrunn"
        werte, info = K.lies_nachfrage("datum_aufgabe_post", json.dumps(
            {"fundstelle": fund, "datum_aufgabe_post": "30.03.2026"}), dok)
        self.assertEqual(werte, {"datum_aufgabe_post": "2026-03-30"})
        self.assertEqual(info["fundstelle_ersetzt"][0]["grund"], "Datum steht nicht in der Fundstelle")
        self.assertTrue(info["fundstelle_ersetzt"][0]["zeile"].startswith("[Stempel: Ab-Vermerk"))
        # Datum des Bescheids steht in keiner Post-Zeile: bleibt verworfen
        werte, info = K.lies_nachfrage("datum_aufgabe_post", json.dumps(
            {"fundstelle": fund, "datum_aufgabe_post": "27.03.2026"}), dok)
        self.assertEqual((werte, info["verworfen"][0]["wert"]), ({}, "2026-03-27"))
        # zwei Post-Zeilen mit dem Datum: nicht eindeutig, verworfen
        zwei = dok + "\nPostausgang: 30.03.2026 (einfacher Brief)"
        self.assertIsNone(K.ersatz_fundstelle(zwei, "datum_aufgabe_post", "2026-03-30"))
        # andere Felder ohne Pflichtwort: kein Ersatz
        self.assertIsNone(K.ersatz_fundstelle(dok, "datum_zugang", "2026-03-30"))

    def test_fehler_in_der_nachfrage_ist_fehler_der_zeile(self):
        stub = _StubV3({"F020": {"datum_zugang": None}}, fehler_bei_nachfrage=socket.timeout("timed out"))
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            argv = ["--modelle", "stub:1b", "--laeufe", "1", "--ids", "F020", "--ausgabe-dir", tmp, "--datum",
                    "2026-10-15"]
            K.main(argv, chat_fn=stub)
            z = _zeilen(tmp, "stub:1b+rechner-v3")[("F020", 1)]
            self.assertIn("Zeitüberschreitung", z["fehler"])
            stub.fehler_bei_nachfrage = None           # Fortsetzen fragt die Aufgabe erneut ab
            K.main(argv, chat_fn=stub)
            self.assertEqual([x[0] for x in stub.aufrufe], ["auslese", "nachfrage", "auslese", "nachfrage"])
            rang = _bewerte(tmp, 1)["stub:1b+rechner-v3"]
            self.assertEqual(rang["pro_aufgabe"]["F020"], "1/1")


class StubModellV3(unittest.TestCase):
    """Die Lesefehler der v2-Läufe (öffentliche Aufgaben) als Stub; v3 fängt die mit Beleg im Dokument ab."""

    FALSCH = {
        "F020": {"datum_zugang": None},                          # Zugang nicht gelesen -> Nachfrage
        "F035": {"genanntes_fristende": "20.11.2025"},           # berichtigt statt abgeschrieben -> D1, Nachfrage
        "F050": {"verfahren": "AO"},                             # Widerspruch, also nicht AO -> V
        "F011": {"verfahren": "SGB X"},                          # Verwaltungsgericht -> V
        "F049": {"rechtsbehelfsbelehrung": "vorhanden"},         # keine Belehrung im Dokument -> B
        "F027": {"schreiben": "widerspruchsbescheid"},           # Belehrung nennt Widerspruch -> S
        "F002": {"datum_zugang": lambda w: w["datum_schreiben"]},  # nur Datum des Schreibens -> D2, Nachfrage
        "F013": {"verfahren": "SGB X", "art": "widerspruch_sgb2"},  # kein Beleg: bleibt (Datum hier gleich)
        "F031": {"datum_zugang": None, "ueberlassung": None},    # zwei Felder fehlen, nur eine Nachfrage
    }

    def test_v3_faengt_belegte_fehler_ab(self):
        stub = _StubV3(self.FALSCH)
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            K.main(["--modelle", "stub:1b", "--ausgabe-dir", tmp, "--datum", "2026-10-15"], chat_fn=stub)
            rang = _bewerte(tmp)
            zeilen = _zeilen(tmp, "stub:1b+rechner-v3")
            r = rang["stub:1b+rechner-v3"]
            self.assertEqual(r["bereiche"]["gesamt"]["exakt_alle_laeufe"], 49)
            for i, ergebnis in r["pro_aufgabe"].items():
                self.assertEqual(ergebnis, "0/3" if i == "F031" else "3/3", i)
            self.assertEqual(zeilen[("F013", 1)]["felder"]["verfahren"], "SGB X")   # falsch gelesen, nicht geraten
            # Nachfrage genau bei den Aufgaben, denen nach Auslese und Gegenprobe ein nötiges Feld fehlt
            mit = {i for (i, _), z in zeilen.items() if z["aufrufe"] == 2}
            self.assertEqual(mit, {"F002", "F003", "F020", "F031", "F035", "F043"})
            self.assertEqual(len(stub.aufrufe), 150 + 3 * len(mit))
            self.assertTrue(all(z["aufrufe"] in (1, 2) and z["prompt_version"] == PK.V3.version
                                for z in zeilen.values()))
            for i in ("F035", "F050", "F011", "F049", "F027", "F020"):
                self.assertEqual(zeilen[(i, 1)]["antwort_json"]["sicherheit"], K.MIT_ANNAHME, i)
            md = bewerten.markdown(rang, 3)
            self.assertIn("+rechner-v3“: geschärfter Auslese-Prompt", md)

            alle = fehleranalyse.lade_kette([Path(tmp)])["stub:1b+rechner-v3"]
            an = fehleranalyse.analysiere(NACH_ID, alle)
            an_auslese = fehleranalyse.analysiere(NACH_ID, alle, quelle="auslese")
            self.assertEqual(set(an["felder"]["verfahren"]["aufgaben"]), {"F013"})
            self.assertEqual(set(an_auslese["felder"]["verfahren"]["aufgaben"]), {"F011", "F013", "F050"})
            self.assertEqual(an["nachfragen"]["gestellt"], 18)
            self.assertEqual(an["nachfragen"]["je_feld"]["datum_zugang"], [9, 6])   # F002 bleibt leer (richtig)
            self.assertEqual(set(an["gegenproben"]), {"B", "D1", "D2", "S", "V"})
            md = fehleranalyse.markdown({"stub:1b+rechner-v3": an})
            self.assertIn("Nachfragen: 18", md)


class Holdout(unittest.TestCase):
    """Holdout-Satz: eigener Ausgabeordner und eigene Rangliste; der echte Satz wird hier nie gelesen."""

    def _satz(self, wurzel: Path, ids=("F001", "F004", "F020")) -> Path:
        (wurzel / "holdout").mkdir()
        pfad = wurzel / "holdout" / "aufgaben_seed1.jsonl"
        pfad.write_text("".join(json.dumps(NACH_ID[i], ensure_ascii=False) + "\n" for i in ids), "utf-8")
        return pfad

    def test_holdout_eigener_ordner_und_rangliste(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            wurzel = Path(tmp)
            self._satz(wurzel)
            erg = wurzel / "ergebnisse"
            with mock.patch.object(K, "HOLDOUT_DIR", wurzel / "holdout"), mock.patch.object(K, "ERGEBNISSE", erg), \
                    mock.patch("bewerten.NUR_POSITIVLISTE", True):
                self.assertEqual(K.main(["--holdout", "--orakel", "--laeufe", "1", "--datum", "2026-10-15"]), 0)
                self.assertEqual(K.main(["--holdout", "--modelle", "stub:1b", "--laeufe", "1", "--datum",
                                         "2026-10-15"], chat_fn=_StubV3()), 0)
            ziel = erg / "holdout"
            self.assertEqual(sorted(p.name for p in erg.iterdir()), ["holdout"])
            self.assertEqual(sorted(p.name for p in ziel.iterdir()),
                             ["2026-10-15-orakel+rechner-v3.jsonl", "2026-10-15-stub-1b+rechner-v3.jsonl",
                              "rangliste.json", "rangliste.md"])
            rang = json.loads((ziel / "rangliste.json").read_text("utf-8"))["modelle"]
            for name in ("orakel+rechner-v3", "stub:1b+rechner-v3"):
                g = rang[name]["bereiche"]["gesamt"]
                self.assertEqual((g["aufgaben"], g["exakt_alle_laeufe"]), (3, 3), name)

    def test_holdout_braucht_genau_eine_datei(self):
        with tempfile.TemporaryDirectory() as tmp:
            leer = Path(tmp) / "holdout"
            leer.mkdir()
            with mock.patch.object(K, "HOLDOUT_DIR", leer):
                with self.assertRaises(SystemExit):
                    K.holdout_datei()
                (leer / "a.jsonl").write_text("", "utf-8")
                self.assertEqual(K.holdout_datei(), leer / "a.jsonl")
                (leer / "b.jsonl").write_text("", "utf-8")
                with self.assertRaises(SystemExit):
                    K.holdout_datei()
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            K.main(["--holdout", "--aufgaben", "x.jsonl", "--orakel"])

    def test_gleiche_ids_anderer_satz_bricht_ab(self):
        # Befund Gegenprüfer: Seed v1 und Holdout haben dieselben IDs. Fortsetzen, Bewerten und Fehleranalyse dürfen
        # Zeilen des einen Satzes nie als Zeilen des anderen zählen.
        anders = {i: dict(NACH_ID[i], dokument=NACH_ID[i]["dokument"] + "\nNachtrag.") for i in ("F001", "F004")}
        self.assertNotEqual(bewerten.aufgabe_kennung(anders["F001"]), bewerten.aufgabe_kennung(NACH_ID["F001"]))
        with tempfile.TemporaryDirectory() as tmp, mock.patch("builtins.print"):
            wurzel = Path(tmp)
            satz = wurzel / "seedx.jsonl"
            satz.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in anders.values()), "utf-8")
            erg = wurzel / "erg"
            argv = ["--orakel", "--laeufe", "1", "--datum", "2026-10-15", "--ausgabe-dir", str(erg), "--ids",
                    "F001", "F004"]
            self.assertEqual(K.main(argv), 0)                        # Seed v1
            zeilen = [json.loads(z) for z in (erg / "2026-10-15-orakel+rechner-v3.jsonl").read_text("utf-8")
                      .splitlines()]
            self.assertEqual({z["aufgabe_kennung"] for z in zeilen},
                             {bewerten.aufgabe_kennung(NACH_ID[i]) for i in ("F001", "F004")})
            with self.assertRaises(SystemExit) as cm:                # anderer Satz, gleiche Datei: Abbruch
                K.main(argv + ["--aufgaben", str(satz)])
            self.assertIn("anderen Aufgabensatzes", str(cm.exception))
            # Bewerten und Fehleranalyse gegen den falschen Satz: Abbruch statt stiller Fehlbewertung
            gelesen = bewerten.lade_ergebnisse([erg])
            with self.assertRaises(ValueError):
                bewerten.bewerte(anders, gelesen, 1)
            # bewerten.main setzt NUR_POSITIVLISTE global; patch stellt den alten Wert danach wieder her
            with mock.patch("sys.stderr", io.StringIO()), mock.patch.object(bewerten, "NUR_POSITIVLISTE", True):
                self.assertEqual(bewerten.main(["--aufgaben", str(satz), "--ergebnisse", str(erg), "--laeufe", "1",
                                                "--ausgabe-dir", str(wurzel / "r"), "--nur-positivliste"]), 2)
                self.assertEqual(fehleranalyse.main(["--aufgaben", str(satz), "--ergebnisse", str(erg),
                                                     "--laeufe", "1"]), 2)
            with self.assertRaises(ValueError):
                fehleranalyse.analysiere(anders, fehleranalyse.lade_kette([erg])["orakel+rechner-v3"], 1)
            self.assertEqual(_bewerte(erg, 1)["orakel+rechner-v3"]["pro_aufgabe"]["F001"], "1/1")   # richtiger Satz
            # ältere Zeilen ohne Kennung: nur für aufgaben.jsonl als erledigt zählen
            alt = erg / "alt.jsonl"
            alt.write_text(json.dumps({"modell": "m", "id": "F001", "lauf": 1}) + "\n", "utf-8")
            self.assertEqual(K.schon_da(alt, [NACH_ID["F001"]]), {("F001", 1)})
            with self.assertRaises(SystemExit):
                K.schon_da(alt, [anders["F001"]], standard=False)

    def test_ausgabeordner_je_aufgabensatz(self):
        self.assertEqual(K.standard_ausgabe(K.STANDARD_AUFGABEN), K.ERGEBNISSE)
        self.assertEqual(K.standard_ausgabe(K.HOLDOUT_DIR / "aufgaben_seed9.jsonl"), K.ERGEBNISSE / "holdout")
        self.assertEqual(K.standard_ausgabe(Path("/tmp/x/seed7.jsonl")), K.ERGEBNISSE / "seed7")
        # nicht rekursiv: Unterordner (holdout, seed7) fließen nie in die Hauptrangliste
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "holdout").mkdir()
            (Path(tmp) / "holdout" / "x.jsonl").write_text(json.dumps({"modell": "m", "id": "F001", "lauf": 1}),
                                                          "utf-8")
            self.assertEqual(bewerten.lade_ergebnisse([Path(tmp)]), {})




class Nachrechnen(unittest.TestCase):
    """benchmark/fristen/nachrechnen.py: gespeicherte Auslesen mit dem heutigen Code neu rechnen."""

    def _zeile(self, a, lauf, **aenderungen):
        roh = K.als_modellausgabe(K.orakel_felder(a)[0])
        roh.update(aenderungen)
        text = json.dumps(roh, ensure_ascii=False)
        teil = K.verarbeite(a, text, "v3")
        return {"modell": "test+rechner-v3", "id": a["id"], "lauf": lauf, "quelle": "kette",
                "prompt_version": "fristen-kette-auslese-v3", "aufgabe_kennung": bewerten.aufgabe_kennung(a),
                "auslese": text, "nachfrage": None, "antwort": teil["antwort"],
                "antwort_json": teil["antwort_json"]}

    def test_gespeichert_gegen_neu_und_verworfene_zeilen(self):
        import nachrechnen
        a, b = NACH_ID["F001"], NACH_ID["F004"]
        zeilen = [self._zeile(a, 1), self._zeile(b, 1)]
        zeilen[1]["antwort_json"] = {"antwortart": "befund", "fristende": "1999-01-01", "normen": [],
                                     "sicherheit": 0.9}           # gespeicherte Antwort falsch, Auslese richtig
        r = nachrechnen.nachrechne({"F001": a, "F004": b}, zeilen)
        self.assertEqual((r["alt"], r["zeilen"], r["exakt_zeilen"], r["bestanden"]), ("gespeichert", 2, [1, 2], [1, 2]))
        self.assertEqual((r["vergleich"]["nur_a"], r["vergleich"]["nur_b"]), ([], ["F004"]))
        self.assertEqual((r["nachfrage_anders"], r["belastbar"]["bestanden"]), ([], [1, 2]))
        self.assertEqual(r["sicher_falsch"], [1, 0])
        zeilen[0]["aufgabe_kennung"] = "anderer-satz"
        del zeilen[1]["aufgabe_kennung"]
        r = nachrechnen.nachrechne({"F001": a, "F004": b}, zeilen)
        self.assertEqual((r["verworfen"]["fremd"], r["verworfen"]["ohne_kennung"], r["zeilen"]), (["F001"], 1, 0))
        self.assertEqual(nachrechnen.nachrechne({"F001": a, "F004": b}, zeilen, ohne_kennung=True)["zeilen"], 1)

    def test_basis_nachfrage_und_ablation(self):
        import nachrechnen
        a, c = NACH_ID["F001"], NACH_ID["F002"]
        zeilen = [self._zeile(a, 1, rechtsbehelfsbelehrung="fehlt"), self._zeile(c, 1)]
        basis = [dict(nachrechnen.nachrechne_zeile(a, zeilen[0]), exakt=False, sicherheit=0.6, regeln=["B"]),
                 nachrechnen.nachrechne_zeile(c, zeilen[1])]
        r = nachrechnen.nachrechne({"F001": a, "F002": c}, zeilen, basis)
        self.assertEqual(r["alt"], "basis")
        # F002 ist eine Rückfrage-Aufgabe: der Code will eine Nachfrage, die Zeile hat keine -> markiert
        self.assertEqual(r["nachfrage_anders"], ["F002"])
        self.assertEqual(r["belastbar"]["aufgaben"], 1)
        self.assertEqual([(g["id"], g["exakt"]) for g in r["geaendert"]], [("F001", [False, True])])
        # Ablation ohne Gegenprobe: Regel B greift beim Nachrechnen nicht
        z = dict(zeilen[0], modell="test+rechner-v3-ohne-gegenprobe")
        self.assertEqual(nachrechnen.nachrechne_zeile(a, z)["regeln"], [])
        self.assertIn("B", nachrechnen.nachrechne_zeile(a, zeilen[0])["regeln"])


if __name__ == "__main__":
    unittest.main()
