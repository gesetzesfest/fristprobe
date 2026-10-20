"""Tests für Generator, Prompt, Bewertung und die Läufer (Ollama wird nachgebaut)."""

import io
import json
import re
import socket
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

WURZEL = Path(__file__).resolve().parents[1]
FRISTEN = WURZEL / "benchmark" / "fristen"
for p in (str(WURZEL), str(FRISTEN), str(WURZEL / "benchmark")):
    if p not in sys.path:
        sys.path.insert(0, p)

import bewerten  # noqa: E402
import generator  # noqa: E402
import opus_auftrag  # noqa: E402
import prompt as P  # noqa: E402
import run_antworten  # noqa: E402
import run_ollama  # noqa: E402
import statistik  # noqa: E402
import tempo  # noqa: E402
from pruefki.fristen import rechner as R  # noqa: E402
from pruefki.fristen.feiertage import LAENDER  # noqa: E402
from pruefki.fristen.normen import positivliste, schluessel, treffer  # noqa: E402

AUFGABEN = generator.erzeuge()
BELEGE = json.loads((WURZEL / "recht" / "belege.json").read_text("utf-8"))
REGELN = {r["id"]: r for g in BELEGE for r in g["regeln"]}


class Generator(unittest.TestCase):
    def test_reproduzierbar_und_gleich_der_datei(self):
        self.assertEqual(generator.erzeuge(), AUFGABEN)
        self.assertEqual(generator.lade(), AUFGABEN, "aufgaben.jsonl ist nicht aktuell: generator.py ausführen")

    def test_anzahl_ids_split_typ(self):
        self.assertEqual([a["id"] for a in AUFGABEN], [f"F{i:03d}" for i in range(1, 51)])
        self.assertEqual(sum(a["split"] == "oeffentlich" for a in AUFGABEN), 35)
        self.assertEqual(sum(a["split"] == "privat" for a in AUFGABEN), 15)
        self.assertEqual(sum(a["typ"] == "berechnen" for a in AUFGABEN), 30)
        self.assertEqual(sum(a["typ"] == "pruefen" for a in AUFGABEN), 20)

    def test_pruefaufgaben_verteilung_und_fallen(self):
        pr = [a for a in AUFGABEN if a["typ"] == "pruefen"]
        kein = [a for a in pr if a["sollwert"]["antwortart"] == "kein_befund"]
        self.assertTrue(0.30 <= len(kein) / len(pr) <= 0.40)
        self.assertGreaterEqual(sum(1 for a in kein if a["falle"]), 2)
        self.assertGreaterEqual(sum(a["sollwert"]["antwortart"] == "rueckfrage" for a in pr), 1)
        self.assertGreaterEqual(sum(a["sollwert"]["antwortart"] == "befund" for a in pr), 1)

    def test_alle_laender_und_jahre(self):
        self.assertEqual({a["land"] for a in AUFGABEN}, set(LAENDER))
        for a in AUFGABEN:
            args = a["parameter"]["argumente"]
            ereignis = (args.get("aufgabe_post") or args.get("zustellung") or args.get("zugang")
                        or a["parameter"].get("zusatz", {}).get("bescheid_datum")
                        or a["parameter"].get("zusatz", {}).get("schreiben_vom"))
            self.assertTrue("2025-01-01" <= ereignis <= "2027-12-31", a["id"])

    def test_sollwert_nur_aus_dem_rechner(self):
        for a in AUFGABEN:
            p, s = a["parameter"], a["sollwert"]
            if s["antwortart"] == "rueckfrage":
                with self.assertRaises(ValueError, msg=a["id"]):
                    R.berechne(p["funktion"], p["argumente"])
                self.assertIsNone(s["fristende"])
                continue
            e = R.berechne(p["funktion"], p["argumente"])
            self.assertEqual(e.datum.isoformat(), s["fristende"], a["id"])
            self.assertFalse(e.strittig, a["id"])
            self.assertFalse(e.unsicher, a["id"])
            self.assertEqual(e.rechenweg, a["rechenweg"], a["id"])

    def test_genanntes_datum_im_dokument(self):
        for a in AUFGABEN:
            if a["typ"] != "pruefen":
                continue
            g = date.fromisoformat(a["parameter"]["genannt"])
            self.assertIn(g.strftime("%d.%m.%Y"), a["dokument"], a["id"])
            art = a["sollwert"]["antwortart"]
            if art == "befund":
                self.assertNotEqual(a["parameter"]["genannt"], a["sollwert"]["fristende"], a["id"])
            if art == "kein_befund":
                self.assertEqual(a["parameter"]["genannt"], a["sollwert"]["fristende"], a["id"])

    def test_sollwert_steht_nicht_im_dokument_bei_berechnen(self):
        for a in AUFGABEN:
            if a["typ"] == "berechnen":
                d = date.fromisoformat(a["sollwert"]["fristende"])
                self.assertNotIn(d.strftime("%d.%m.%Y"), a["dokument"], a["id"])

    def test_dokument_laenge_und_felder(self):
        felder = {"id", "typ", "art", "split", "land", "falle", "dokument", "frage", "parameter", "sollwert",
                  "rechenweg"}
        for a in AUFGABEN:
            self.assertTrue(felder <= set(a), a["id"])
            self.assertTrue(8 <= len(a["dokument"].split("\n")) <= 25, a["id"])
            self.assertEqual(set(a["sollwert"]), {"antwortart", "fristende", "normen_pflicht", "normen_ok",
                                                  "teilpunkt_daten"})

    def test_keine_strittigen_regeln_im_rechenweg(self):
        for a in AUFGABEN:
            for satz in a["rechenweg"]:
                ids = re.findall(r"[A-Z]{1,2}-\d{2}", satz.split("]")[0])
                self.assertTrue(ids, satz)
                for rid in ids:
                    self.assertIn(rid, REGELN, satz)
                    self.assertFalse(REGELN[rid]["strittig"], (a["id"], rid))

    def test_normen_im_sollwert_auf_positivliste(self):
        pos = positivliste()
        for a in AUFGABEN:
            for p in a["sollwert"]["normen_pflicht"]:
                for alt in (p if isinstance(p, list) else [p]):
                    self.assertTrue(schluessel(alt) and schluessel(alt) <= pos, (a["id"], alt))
            for n in a["sollwert"]["normen_ok"]:
                self.assertTrue(schluessel(n) <= pos, (a["id"], n))

    def test_personen_einmalig(self):
        erste_zeilen = [z for a in AUFGABEN for z in a["dokument"].split("\n") if z.startswith(("Frau ", "Herrn "))]
        self.assertGreaterEqual(len(set(erste_zeilen)), 45)

    def test_injektion_in_zwei_aufgaben(self):
        self.assertEqual(sum("injektion" in a["falle"] for a in AUFGABEN), 2)

    def test_verschiebungsnormen_je_fristart(self):
        def alle(a):
            return [x for p in a["sollwert"]["normen_pflicht"] for x in (p if isinstance(p, list) else [p])]
        for a in AUFGABEN:
            if a["art"] == "kschg_klage" and a["sollwert"]["antwortart"] != "rueckfrage":
                e = R.berechne(a["parameter"]["funktion"], a["parameter"]["argumente"])
                if e.details["verschoben"]:
                    # § 222 Abs. 2 ZPO und § 193 BGB gleichwertig (Rechtsnatur von § 4 KSchG umstritten)
                    self.assertIn(["§ 222 Abs. 2 ZPO", "§ 193 BGB"], a["sollwert"]["normen_pflicht"], a["id"])
            # gerichtliche Klagefristen: kein VwVfG, kein SGB X als Verschiebungsnorm
            if a["parameter"]["argumente"].get("art") in ("klage_vwgo", "klage_sgg"):
                self.assertFalse([n for n in alle(a) if "VwVfG" in n or "§ 26" in n], a["id"])

    def test_befund_teilpunkt_ohne_genanntes_datum(self):
        for a in AUFGABEN:
            if a["sollwert"]["antwortart"] == "befund":
                self.assertNotIn(a["parameter"]["genannt"], a["sollwert"]["teilpunkt_daten"], a["id"])

    def test_fallen_labels_erklaeren_das_genannte_datum(self):
        modelle = {label: modell for label, modell, _ in generator.KONKURRENZ_RB}
        for a in AUFGABEN:
            if a["sollwert"]["antwortart"] != "befund" or a["parameter"]["funktion"] != "rechtsbehelf":
                continue
            args = {k: (date.fromisoformat(v) if k in ("aufgabe_post", "zustellung") and v else v)
                    for k, v in a["parameter"]["argumente"].items()}
            f = generator.Fall("rechtsbehelf", args, R.rechtsbehelf(**args))
            genannt = date.fromisoformat(a["parameter"]["genannt"])
            for label in a["falle"]:
                if label in modelle:
                    self.assertEqual(modelle[label](f, a["land"]), genannt, (a["id"], label))
            # kein weiteres passendes Fehlermodell erzeugt dasselbe Datum, ohne genannt zu sein
            for label, modell, passt in generator.KONKURRENZ_RB:
                if label not in a["falle"] and passt(f):
                    self.assertNotEqual(modell(f, a["land"]), genannt, (a["id"], label))


@unittest.skipUnless((FRISTEN / "vorlagen2.py").exists(), "Vorlagen v2 sind nicht öffentlich")
class VorlagenZwei(unittest.TestCase):
    """Vorlagen v2: gleiche Fälle und Sollwerte wie v1, nur andere Schreiben (vorlagen2.py)."""

    SEEDS = (generator.SEED, 20261024, 20261025, 20261026, 20261027)

    @classmethod
    def setUpClass(cls):
        cls.paare = {s: (generator.erzeuge(s), generator.erzeuge(s, 2)) for s in cls.SEEDS}

    def test_faelle_und_sollwerte_wie_v1(self):
        gleich = ["id", "typ", "art", "split", "land", "falle", "frage", "parameter", "sollwert", "rechenweg"]
        for seed, (v1, v2) in self.paare.items():
            self.assertEqual([[a.get(k) for k in gleich] for a in v1], [[a.get(k) for k in gleich] for a in v2],
                             seed)
            self.assertTrue(all(a["dokument"] != b["dokument"] for a, b in zip(v1, v2)), seed)
            self.assertEqual({a["version"] for a in v2}, {"fristen-v1+vorlagen2"})

    def test_dateien_aktuell(self):
        for seed in self.SEEDS:
            pfad = FRISTEN / "vorlagen2" / f"aufgaben_seed{seed}.jsonl"
            self.assertEqual(generator.lade(pfad), self.paare[seed][1], f"{pfad.name} neu erzeugen")

    def test_tatsachen_im_dokument(self):
        for seed, (_, v2) in self.paare.items():
            for a in v2:
                doc, args = a["dokument"], a["parameter"]["argumente"]
                wo = f"{seed} {a['id']}"
                for k in ("aufgabe_post", "zustellung", "zugang", "ueberlassung", "beginn"):
                    if args.get(k):
                        self.assertIn(date.fromisoformat(args[k]).strftime("%d.%m.%Y"), doc, wo + " " + k)
                self.assertIn(LAENDER[a["land"]], doc, wo)
                if args.get("zustellart") == "pzu":
                    self.assertIn("Postzustellungsurkunde", doc, wo)
                if args.get("zustellart") == "brief" and args.get("aufgabe_post"):
                    self.assertRegex(doc, r"einfache[rn]? (Brief|Post)", wo)
                if args.get("rbb") is False:
                    schreiben = doc.split("\n— Vermerk:")[0]  # der Vermerk einer dritten Stelle kommt danach
                    self.assertNotRegex(schreiben, r"Belehrung|Rechtsbehelf|Widerspruch (erhoben|einlegen)", wo)
                if a["typ"] == "berechnen":
                    d = date.fromisoformat(a["sollwert"]["fristende"])
                    self.assertNotIn(d.strftime("%d.%m.%Y"), doc, wo)
                else:
                    g = date.fromisoformat(a["parameter"]["genannt"])
                    self.assertEqual(doc.count(g.strftime("%d.%m.%Y")), 1, wo)
                self.assertTrue(8 <= len(doc.split("\n")) <= 45, wo)


class Normen(unittest.TestCase):
    def test_gleichwertige_schreibweisen(self):
        self.assertEqual(schluessel("§ 84 Abs. 1 SGG"), schluessel("§84 SGG"))
        self.assertEqual(schluessel("§ 26 SGB 10"), schluessel("§ 26 Abs. 3 SGB X"))
        self.assertEqual(schluessel("§§ 187, 188 BGB"), {("187", "BGB"), ("188", "BGB")})
        self.assertEqual(schluessel("§ 57 Abs. 2 VwGO i. V. m. § 222 ZPO"), {("57", "VWGO"), ("222", "ZPO")})

    def test_alternativen_und_erfindung(self):
        genannt = schluessel("§ 26 Abs. 3 SGB X")
        self.assertTrue(treffer(["§ 64 Abs. 3 SGG", "§ 26 Abs. 3 SGB X"], genannt))
        self.assertTrue(treffer(["§ 222 Abs. 2 ZPO", "§ 193 BGB"], schluessel("§ 193 BGB")))
        self.assertFalse(treffer("§ 222 Abs. 2 ZPO", schluessel("§ 193 BGB")))
        self.assertNotIn(("999", "SGG"), positivliste())
        self.assertIn(("573c", "BGB"), positivliste())

    def test_unbekannte_kuerzel_werden_erkannt(self):
        # Erfundene Gesetze aus echten Modellantworten vom 14.10. rutschten vorher ganz durch.
        self.assertEqual(schluessel("§ 148 Abs. 2 BAO"), {("148", "BAO")})
        self.assertEqual(schluessel("§ 241 ZGB"), {("241", "ZGB")})
        self.assertEqual(schluessel("§ 3 EntgFG"), {("3", "ENTGFG")})
        self.assertEqual(schluessel("§ 41 Abs. 2 des VwVfG"), {("41", "VWVFG")})
        self.assertEqual(schluessel("§ 193 BGB (Sonn- und Feiertage)"), {("193", "BGB")})

    def test_nicht_pruefbares_bleibt_unerkannt(self):
        self.assertEqual(schluessel("Art. 6 DSGVO"), set())      # EU-Recht
        self.assertEqual(schluessel("§ 41 LVwVfG"), set())       # Landesrecht
        self.assertEqual(schluessel("§ 84 SGB"), set())          # Buch fehlt: unvollständig, nicht erfunden
        self.assertEqual(schluessel("Fristende laut KSchG"), set())  # Kürzel ohne Paragraph


class Statistik(unittest.TestCase):
    def test_wilson_und_mcnemar_bekannte_werte(self):
        lo, hi = statistik.wilson(49, 50)
        self.assertAlmostEqual(lo, 0.895, places=3)
        self.assertAlmostEqual(hi, 0.9965, places=3)
        self.assertAlmostEqual(statistik.mcnemar_exakt(5, 1), 14 / 64)     # qwen3:8b+v3 gegen Opus, Seed v1
        self.assertAlmostEqual(statistik.mcnemar_exakt(10, 1), 24 / 2048)
        self.assertEqual(statistik.mcnemar_exakt(0, 0), 1.0)
        self.assertEqual(statistik.mcnemar_exakt(3, 3), 1.0)

    def test_bootstrap_reproduzierbar_und_gleich_null(self):
        ids = [f"F{i:03d}" for i in range(1, 51)]
        a = set(ids[:45])
        self.assertEqual(statistik.bootstrap_differenz(a, a, ids), (0.0, 0.0))
        self.assertEqual(statistik.bootstrap_differenz(a, set(ids[:40]), ids),
                         statistik.bootstrap_differenz(a, set(ids[:40]), ids))

    def test_vergleich_in_rangliste(self):
        aufgaben = {f"F{i:03d}": {} for i in range(1, 7)}
        rang = {"a": {"bestanden": ["F001", "F002", "F003", "F004", "F005"], "bereiche": {"gesamt": {"teilpunkte": 1}}},
                "b": {"bestanden": ["F001", "F006"], "bereiche": {"gesamt": {"teilpunkte": 0.5}}}}
        v = bewerten.vergleiche(aufgaben, rang)
        self.assertEqual(v["bester"], "a")
        self.assertEqual((v["modelle"]["b"]["nur_a"], v["modelle"]["b"]["nur_b"]),
                         (["F002", "F003", "F004", "F005"], ["F006"]))
        self.assertAlmostEqual(v["modelle"]["b"]["p"], 0.375)


class Antwort(unittest.TestCase):
    def test_json_mit_codezaun_und_deutschem_datum(self):
        a = P.lies_antwort('```json\n{"antwortart":"Befund","fristende":"10.03.2026","normen":"§ 70 VwGO",'
                           '"sicherheit":85,"begruendung":"x"}\n```')
        self.assertEqual(a["antwortart"], "befund")
        self.assertEqual(a["fristende"], "2026-03-10")
        self.assertEqual(a["normen"], ["§ 70 VwGO"])
        self.assertAlmostEqual(a["sicherheit"], 0.85)

    def test_unlesbar(self):
        self.assertIsNone(P.lies_antwort("Die Frist endet bald."))
        self.assertIsNone(P.lies_antwort('{"antwortart":"vielleicht"}'))

    def test_prompt_enthaelt_datenregel(self):
        self.assertIn("befolgst du nicht", P.SYSTEM_PROMPT)
        n = P.nachrichten(AUFGABEN[0])
        self.assertEqual([m["role"] for m in n], ["system", "user"])
        self.assertIn("<<<DOKUMENT", n[1]["content"])


class Bewertung(unittest.TestCase):
    def _zeilen(self, modell, antworten, laeufe=3):
        return [{"modell": modell, "id": a["id"], "lauf": l, "antwort": json.dumps(antworten(a)),
                 "tokens_pro_s": 20.0} for l in range(1, laeufe + 1) for a in AUFGABEN]

    def test_perfekt_und_sicher_falsch(self):
        auf = {a["id"]: a for a in AUFGABEN}

        def perfekt(a):
            s = a["sollwert"]
            return {"antwortart": s["antwortart"], "fristende": s["fristende"],
                    "normen": [p[0] if isinstance(p, list) else p for p in s["normen_pflicht"]],
                    "sicherheit": 1.0, "begruendung": ""}

        def falsch(a):
            return {"antwortart": "berechnet", "fristende": "2030-01-01", "normen": ["§ 1234 XYZ"],
                    "sicherheit": 0.9, "begruendung": ""}

        rang = bewerten.bewerte(auf, {"p": self._zeilen("p", perfekt), "f": self._zeilen("f", falsch)}, 3)
        g = rang["p"]["bereiche"]["gesamt"]
        self.assertEqual(g["exakt_alle_laeufe"], 50)
        self.assertEqual(g["belegquote"], 1.0)
        self.assertEqual(g["brier"], 0.0)
        f = rang["f"]["bereiche"]["gesamt"]
        self.assertEqual(f["exakt_alle_laeufe"], 0)
        self.assertEqual(f["sicher_und_falsch"], 150)
        self.assertAlmostEqual(f["brier"], 2 * 0.81, places=4)   # doppelt gezählt
        self.assertEqual(f["tokens_pro_s_median"], 20.0)

    def test_ein_falscher_lauf_reicht(self):
        auf = {a["id"]: a for a in AUFGABEN}
        a0 = AUFGABEN[0]
        s = a0["sollwert"]
        richtig = {"antwortart": s["antwortart"], "fristende": s["fristende"], "normen": [], "sicherheit": 0.5}
        zeilen = [{"modell": "m", "id": a0["id"], "lauf": 1, "antwort": json.dumps(richtig)},
                  {"modell": "m", "id": a0["id"], "lauf": 2, "antwort": json.dumps(richtig)},
                  {"modell": "m", "id": a0["id"], "lauf": 3, "antwort": "kaputt"}]
        rang = bewerten.bewerte(auf, {"m": zeilen}, 3)
        self.assertEqual(rang["m"]["bereiche"]["gesamt"]["exakt_alle_laeufe"], 0)
        self.assertEqual(rang["m"]["pro_aufgabe"][a0["id"]], "2/3")

    def test_teilpunkte(self):
        a = next(x for x in AUFGABEN if x["typ"] == "berechnen" and x["sollwert"]["teilpunkt_daten"])
        z = {"antwort": json.dumps({"antwortart": "berechnet", "fristende": a["sollwert"]["teilpunkt_daten"][0],
                                    "normen": [], "sicherheit": 0.4})}
        self.assertEqual(bewerten.bewerte_antwort(a, z)["teilpunkte"], 0.5)

    def test_beispieldatei(self):
        with tempfile.TemporaryDirectory() as tmp:
            erg = Path(tmp) / "erg"
            run_antworten.einlesen([FRISTEN / "beispiel" / "antworten.jsonl"], {a["id"]: a for a in AUFGABEN},
                                   "2026-10-14", erg)
            rang = bewerten.bewerte({a["id"]: a for a in AUFGABEN}, bewerten.lade_ergebnisse([erg]), 3)
            self.assertEqual(rang["beispiel-perfekt"]["bereiche"]["gesamt"]["exakt_alle_laeufe"], 50)
            self.assertEqual(rang["beispiel-kaputt"]["bereiche"]["gesamt"]["exakt_alle_laeufe"], 0)
            self.assertGreater(rang["beispiel-naiv"]["bereiche"]["gesamt"]["erfindungsquote"], 0)


class OpusAuftrag(unittest.TestCase):
    def test_kein_sollwert_in_den_auftraegen(self):
        for z in opus_auftrag.zeilen(AUFGABEN):
            self.assertEqual(set(z), {"id", "system", "user"})
            self.assertNotIn("sollwert", z["user"])
            self.assertNotIn("rechenweg", z["user"])


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class OllamaNachgebaut(unittest.TestCase):
    """run_ollama.py und tempo.py gegen einen nachgebauten Ollama-Server."""

    def setUp(self):
        self.anfragen = []

    def _urlopen(self, req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        body = json.loads(req.data) if not isinstance(req, str) and req.data else None
        self.anfragen.append((url, body))
        if url.endswith("/api/tags"):
            return _Antwort(json.dumps({"models": [{"name": "fake:1b", "model": "fake:1b"},
                                                   {"name": "qwen3:4b", "model": "qwen3:4b"}]}).encode())
        if url.endswith("/api/ps"):
            return _Antwort(b'{"models": []}')
        if url.endswith("/api/chat"):
            if "F002" in body["messages"][1]["content"]:
                raise socket.timeout("timed out")
            inhalt = json.dumps({"antwortart": "berechnet", "fristende": "2026-01-01", "normen": ["§ 84 SGG"],
                                 "sicherheit": 0.7, "begruendung": "test"})
            return _Antwort(json.dumps({"message": {"content": inhalt}, "eval_count": 100,
                                        "eval_duration": 4_000_000_000, "load_duration": 1_000_000_000,
                                        "prompt_eval_count": 800, "prompt_eval_duration": 500_000_000}).encode())
        if url.endswith("/api/generate"):
            return _Antwort(json.dumps({"response": "x", "eval_count": 256, "eval_duration": 8_000_000_000,
                                        "load_duration": 2_000_000_000, "prompt_eval_count": 40,
                                        "prompt_eval_duration": 200_000_000}).encode())
        raise AssertionError(url)

    def test_run_ollama_schreibt_zeilen_und_laeuft_bei_fehlern_weiter(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", self._urlopen), \
                mock.patch("builtins.print"):
            rc = run_ollama.main(["--modelle", "fake:1b", "qwen3:4b", "fehlt:7b", "--laeufe", "1", "--ids", "F001",
                                  "F002", "F003", "--ausgabe-dir", tmp, "--datum", "2026-10-14"])
            self.assertEqual(rc, 0)
            text = (Path(tmp) / "2026-10-14-fake-1b.jsonl").read_text("utf-8")
            zeilen = [json.loads(z) for z in text.splitlines() if z.strip()]
            self.assertEqual(len(zeilen), 3)
            ok = [z for z in zeilen if not z["fehler"]]
            self.assertEqual(len(ok), 2)
            self.assertEqual(ok[0]["tokens_pro_s"], 25.0)
            self.assertEqual(ok[0]["antwort_json"]["fristende"], "2026-01-01")
            self.assertIn("Zeitüberschreitung", next(z for z in zeilen if z["fehler"])["fehler"])
            chats = [b for u, b in self.anfragen if u.endswith("/api/chat")]
            self.assertTrue(all(b["stream"] is False and b["format"] == "json" for b in chats))
            self.assertNotIn("think", next(b for b in chats if b["model"] == "fake:1b"))
            self.assertIs(next(b for b in chats if b["model"] == "qwen3:4b")["think"], False)
            # Fortsetzen: erfolgreiche Zeilen werden nicht erneut abgefragt
            vorher = len(self.anfragen)
            run_ollama.main(["--modelle", "fake:1b", "--laeufe", "1", "--ids", "F001", "F003",
                             "--ausgabe-dir", tmp, "--datum", "2026-10-14"])
            self.assertFalse([u for u, b in self.anfragen[vorher:] if u.endswith("/api/chat")])

    def test_tempo_ohne_dauerlast(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("urllib.request.urlopen", self._urlopen), \
                mock.patch("builtins.print"):
            rc = tempo.main(["--modelle", "qwen3:4b", "--minuten", "0", "--ausgabe", str(Path(tmp) / "t")])
            self.assertEqual(rc, 0)
            daten = json.loads((Path(tmp) / "t.json").read_text("utf-8"))
            self.assertEqual(daten[0]["kalt"]["token_s"], 32.0)
            self.assertEqual(daten[0]["warm_token_s"], 32.0)
            self.assertIn("| qwen3:4b |", (Path(tmp) / "t.md").read_text("utf-8"))
            entlade = [b for u, b in self.anfragen if u.endswith("/api/generate") and b.get("keep_alive") == 0]
            self.assertEqual(len(entlade), 2)

    def test_server_nicht_erreichbar(self):
        def weg(*a, **k):
            import urllib.error
            raise urllib.error.URLError("Connection refused")
        with mock.patch("urllib.request.urlopen", weg), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(run_ollama.main(["--laeufe", "1"]), 2)
            self.assertEqual(tempo.main(["--minuten", "0"]), 2)


if __name__ == "__main__":
    unittest.main()
