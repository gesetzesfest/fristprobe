"""Tests für Feiertage und Fristenrechner.

Alle Sollwerte sind von Hand nachgerechnet (Kalender 2022 und 2025 bis 2028).
Im Kommentar steht jeweils der Rechenweg. Die Klasse Originaldaten nimmt die
Daten aus Urteilen (nicht aus den Rechenbeispielen in recht/belege.json). Die
Klasse Gegenprobe vergleicht mit einer zweiten, unabhängig geschriebenen
Implementierung: eigene Osterformel (Gauß) und eigene Feiertagsliste, Abzählen
statt Monatsarithmetik, Fristen ab Tagesbeginn mit Überlauf statt Kappung.
"""

import re
import unittest
from datetime import date, timedelta

from pruefki.fristen import rechner as r
from pruefki.fristen.feiertage import (LAENDER, buss_und_bettag, feiertage, ist_feiertag, ist_werktag,
                                       naechster_werktag, ostersonntag)

D = date


class Ostern(unittest.TestCase):
    def test_ostern_2025_bis_2028(self):
        self.assertEqual(ostersonntag(2025), D(2025, 4, 20))
        self.assertEqual(ostersonntag(2026), D(2026, 4, 5))
        self.assertEqual(ostersonntag(2027), D(2027, 3, 28))
        self.assertEqual(ostersonntag(2028), D(2028, 4, 16))

    def test_bewegliche_feiertage_2026(self):
        # Ostern 05.04.2026: Karfreitag 03.04., Ostermontag 06.04., Himmelfahrt +39 = 14.05., Pfingstmontag +50 = 25.05.
        f = feiertage(2026, "HH")
        self.assertEqual(f[D(2026, 4, 3)], "Karfreitag")
        self.assertEqual(f[D(2026, 4, 6)], "Ostermontag")
        self.assertEqual(f[D(2026, 5, 14)], "Christi Himmelfahrt")
        self.assertEqual(f[D(2026, 5, 25)], "Pfingstmontag")


class Landesfeiertage(unittest.TestCase):
    def test_reformationstag_sachsen_ja_bayern_nein(self):
        self.assertTrue(ist_feiertag(D(2025, 10, 31), "SN"))
        self.assertFalse(ist_feiertag(D(2025, 10, 31), "BY"))

    def test_reformationstag_nord_seit_2018(self):
        for land in ("HB", "HH", "NI", "SH"):
            self.assertTrue(ist_feiertag(D(2025, 10, 31), land), land)

    def test_fronleichnam_nrw_ja_niedersachsen_nein(self):
        # Ostern 20.04.2025 + 60 Tage = Do 19.06.2025
        self.assertEqual(feiertage(2025, "NW")[D(2025, 6, 19)], "Fronleichnam")
        self.assertNotIn(D(2025, 6, 19), feiertage(2025, "NI"))

    def test_buss_und_bettag_nur_sachsen(self):
        # Mittwoch vor dem 23.11.2025 (Sonntag) ist der 19.11.2025
        self.assertEqual(buss_und_bettag(2025), D(2025, 11, 19))
        self.assertTrue(ist_feiertag(D(2025, 11, 19), "SN"))
        self.assertFalse(ist_feiertag(D(2025, 11, 19), "TH"))

    def test_frauentag_berlin_und_mv_nicht_hamburg(self):
        self.assertTrue(ist_feiertag(D(2027, 3, 8), "BE"))
        self.assertTrue(ist_feiertag(D(2027, 3, 8), "MV"))
        self.assertFalse(ist_feiertag(D(2027, 3, 8), "HH"))

    def test_weltkindertag_thueringen(self):
        self.assertTrue(ist_feiertag(D(2027, 9, 20), "TH"))
        self.assertFalse(ist_feiertag(D(2027, 9, 20), "SN"))

    def test_allerheiligen_und_heilige_drei_koenige(self):
        self.assertTrue(ist_feiertag(D(2027, 11, 1), "BW"))
        self.assertFalse(ist_feiertag(D(2027, 11, 1), "SN"))
        self.assertTrue(ist_feiertag(D(2026, 1, 6), "ST"))
        self.assertFalse(ist_feiertag(D(2026, 1, 6), "SN"))

    def test_mariae_himmelfahrt_saarland_bayern_nur_gemeinde(self):
        self.assertTrue(ist_feiertag(D(2025, 8, 15), "SL"))
        self.assertFalse(ist_feiertag(D(2025, 8, 15), "BY"))
        self.assertTrue(ist_feiertag(D(2025, 8, 15), "BY", gemeinde="mariae_himmelfahrt"))
        self.assertTrue(ist_feiertag(D(2025, 6, 19), "SN", gemeinde=True))  # Fronleichnam sorbische Gemeinden

    def test_berlin_einmaliger_feiertag_2025(self):
        self.assertTrue(ist_feiertag(D(2025, 5, 8), "BE"))
        self.assertFalse(ist_feiertag(D(2026, 5, 8), "BE"))
        self.assertFalse(ist_feiertag(D(2025, 5, 8), "BB"))

    def test_berlin_einmaliger_feiertag_17_juni_2028(self):
        # GVBl. Berlin 2024 S. 460, Art. 1 Nr. 2 und Art. 3: nur 17.06.2028 (Samstag)
        self.assertTrue(ist_feiertag(D(2028, 6, 17), "BE"))
        self.assertFalse(ist_feiertag(D(2027, 6, 17), "BE"))
        self.assertFalse(ist_feiertag(D(2028, 6, 17), "BB"))
        # zählt nicht als Werktag nach § 573c BGB (Samstag sonst Werktag)
        self.assertFalse(ist_werktag(D(2028, 6, 17), "BE"))
        self.assertTrue(ist_werktag(D(2028, 6, 17), "BB"))
        self.assertEqual(len(feiertage(2028, "BE")), 11)

    def test_oster_und_pfingstsonntag_nur_brandenburg(self):
        # § 2 Abs. 1 FTG BB nennt sie; § 1 Abs. 1 HFeiertagsG nennt nur „die Sonntage“
        self.assertEqual(feiertage(2026, "BB")[D(2026, 4, 5)], "Ostersonntag")
        self.assertNotIn(D(2026, 4, 5), feiertage(2026, "HE"))
        self.assertNotIn(D(2026, 5, 24), feiertage(2026, "HE"))
        self.assertFalse(ist_werktag(D(2026, 4, 5), "HE"))

    def test_anzahl_feiertage_2025(self):
        # SN: 9 bundesweit + Reformationstag + Buß- und Bettag = 11
        self.assertEqual(len(feiertage(2025, "SN")), 11)
        # BY: 9 + Hl. Drei Könige + Fronleichnam + Allerheiligen = 12; mit Gemeinde-Teilfeiertagen 14
        self.assertEqual(len(feiertage(2025, "BY")), 12)
        self.assertEqual(len(feiertage(2025, "BY", gemeinde=True)), 14)
        # BE: 9 + Frauentag + 08.05.2025 einmalig = 11
        self.assertEqual(len(feiertage(2025, "BE")), 11)

    def test_alle_laender_alle_jahre(self):
        for jahr in range(2020, 2031):
            for land in LAENDER:
                self.assertGreaterEqual(len(feiertage(jahr, land)), 9)

    def test_ausserhalb_der_spanne_und_unbekanntes_land(self):
        with self.assertRaises(ValueError):
            feiertage(2031, "BY")
        with self.assertRaises(ValueError):
            feiertage(2025, "XX")


class Werktag(unittest.TestCase):
    def test_samstag(self):
        self.assertTrue(ist_werktag(D(2025, 1, 4), "BE"))
        self.assertFalse(ist_werktag(D(2025, 1, 4), "BE", samstag_ist_werktag=False))

    def test_sonntag_und_neujahr(self):
        self.assertFalse(ist_werktag(D(2025, 1, 5), "BE"))
        self.assertFalse(ist_werktag(D(2025, 1, 1), "BE"))

    def test_naechster_werktag_ueber_ostern(self):
        # Fr 03.04.2026 Karfreitag, Sa 04., So 05., Mo 06. Ostermontag -> Di 07.04.2026
        self.assertEqual(naechster_werktag(D(2026, 4, 3), "NI"), D(2026, 4, 7))


class Bekanntgabe(unittest.TestCase):
    def test_ao_vierter_tag_werktag(self):
        # Mo 03.02.2025 + 4 = Fr 07.02.2025
        e = r.bekanntgabe_fiktion(D(2025, 2, 3), "AO", "BY")
        self.assertEqual(e.datum, D(2025, 2, 7))

    def test_ao_vierter_tag_samstag_verschiebt(self):
        # Di 04.02.2025 + 4 = Sa 08.02.2025 -> § 108 Abs. 3 AO -> Mo 10.02.2025
        e = r.bekanntgabe_fiktion(D(2025, 2, 4), "AO", "BY")
        self.assertEqual(e.datum, D(2025, 2, 10))
        self.assertEqual(e.roh_datum, D(2025, 2, 8))
        self.assertIn("§ 108 Abs. 3 AO", e.normen)

    def test_sgbx_vierter_tag_samstag_bleibt(self):
        # SGB X verschiebt den Fiktionstag nicht (B-04)
        e = r.bekanntgabe_fiktion(D(2025, 2, 4), "SGB X", "BY")
        self.assertEqual(e.datum, D(2025, 2, 8))
        self.assertFalse(e.strittig)

    def test_vwvfg_wochenende_ist_strittig(self):
        e = r.bekanntgabe_fiktion(D(2025, 2, 4), "VwVfG", "BY")
        self.assertTrue(e.strittig)
        e2 = r.bekanntgabe_fiktion(D(2025, 2, 3), "VwVfG", "BY")
        self.assertFalse(e2.strittig)
        self.assertEqual(e2.datum, D(2025, 2, 7))

    def test_ao_uebergang_dreitagesregel(self):
        # A-08: Aufgabe 31.12.2024 -> noch drei Tage -> 03.01.2025 (Fr)
        e = r.bekanntgabe_fiktion(D(2024, 12, 31), "AO", "NW")
        self.assertEqual(e.datum, D(2025, 1, 3))
        self.assertEqual(e.details["tage"], 3)

    def test_ao_fiktionstag_reformationstag_sh_vs_by(self):
        # Mo 27.10.2025 + 4 = Fr 31.10.2025: in SH Reformationstag -> Mo 03.11.2025, in BY Werktag
        self.assertEqual(r.bekanntgabe_fiktion(D(2025, 10, 27), "AO", "SH").datum, D(2025, 11, 3))
        self.assertEqual(r.bekanntgabe_fiktion(D(2025, 10, 27), "AO", "BY").datum, D(2025, 10, 31))

    def test_fehlendes_aufgabedatum(self):
        with self.assertRaises(ValueError):
            r.bekanntgabe_fiktion(None, "AO", "BY")

    def test_ao_fiktion_ostersonntag_brandenburg_ohne_unsicherheit(self):
        # Mi 01.04.2026 + 4 = So 05.04.2026 (Ostersonntag), Mo 06.04. Ostermontag -> Di 07.04.2026; wie in BE
        for land in ("BB", "BE", "HE"):
            e = r.bekanntgabe_fiktion(D(2026, 4, 1), "AO", land)
            self.assertEqual(e.datum, D(2026, 4, 7), land)
            self.assertEqual(e.unsicher, [], land)

    def test_ao_fiktion_landesfeiertag_am_sonntag_ohne_unsicherheit(self):
        # Mi 28.10.2026 + 4 = So 01.11.2026 (in NW Allerheiligen) -> Mo 02.11.2026; ein Sonntag verschiebt überall
        e = r.bekanntgabe_fiktion(D(2026, 10, 28), "AO", "NW")
        self.assertEqual(e.datum, D(2026, 11, 2))
        self.assertEqual(e.unsicher, [])

    def test_ao_fiktion_landesfeiertag_werktag_bleibt_unsicher(self):
        # Mo 27.10.2025 + 4 = Fr 31.10.2025 Reformationstag in SH (G-03)
        self.assertTrue(r.bekanntgabe_fiktion(D(2025, 10, 27), "AO", "SH").unsicher)

    def test_sgbx_rechenweg_nennt_bsg(self):
        e = r.bekanntgabe_fiktion(D(2025, 2, 4), "SGB X", "BY")
        self.assertTrue(any(s.startswith("[B-04]") and "B 14 AS 12/09 R" in s for s in e.rechenweg))


class FristEnde(unittest.TestCase):
    def test_monatsende_31_januar(self):
        # 31.01.2025 + 1 Monat: 31.02. fehlt -> 28.02.2025 (§ 188 Abs. 3 BGB)
        e = r.frist_ende(D(2025, 1, 31), 1, "monate", "BE", False)
        self.assertEqual(e.datum, D(2025, 2, 28))
        self.assertIn("§ 188 Abs. 3 BGB", e.normen)

    def test_schaltjahr_2028(self):
        self.assertEqual(r.frist_ende(D(2028, 1, 31), 1, "monate", "BE", False).datum, D(2028, 2, 29))
        self.assertEqual(r.frist_ende(D(2028, 1, 29), 1, "monate", "BE", False).datum, D(2028, 2, 29))
        self.assertEqual(r.frist_ende(D(2027, 1, 30), 1, "monate", "BE", False).datum, D(2027, 2, 28))

    def test_31_oktober_plus_monat_sonntag(self):
        # 31.10.2025 + 1 Monat = So 30.11.2025 -> Mo 01.12.2025 (§ 222 Abs. 2 ZPO)
        e = r.frist_ende(D(2025, 10, 31), 1, "monate", "NW", True, regime="ZPO")
        self.assertEqual(e.roh_datum, D(2025, 11, 30))
        self.assertEqual(e.datum, D(2025, 12, 1))

    def test_monatsfrist_ohne_verschiebung(self):
        # 18.06.2025 + 1 Monat = Fr 18.07.2025
        self.assertEqual(r.frist_ende(D(2025, 6, 18), 1, "monate", "BW", True, regime="AO").datum, D(2025, 7, 18))

    def test_jahreswechsel_neujahr(self):
        # 01.12.2025 + 1 Monat = Do 01.01.2026 Neujahr -> Fr 02.01.2026
        e = r.frist_ende(D(2025, 12, 1), 1, "monate", "MV", True, regime="VwGO")
        self.assertEqual(e.datum, D(2026, 1, 2))

    def test_jahreswechsel_ohne_feiertag(self):
        self.assertEqual(r.frist_ende(D(2025, 12, 15), 1, "monate", "MV", True).datum, D(2026, 1, 15))

    def test_wochenfrist(self):
        # Mi 22.10.2025 + 3 Wochen = Mi 12.11.2025
        self.assertEqual(r.frist_ende(D(2025, 10, 22), 3, "wochen", "HE", True, regime="ZPO").datum,
                         D(2025, 11, 12))

    def test_tagesfrist(self):
        # Fr 07.03.2025 + 10 Tage = Mo 17.03.2025
        self.assertEqual(r.frist_ende(D(2025, 3, 7), 10, "tage", "HE", True).datum, D(2025, 3, 17))

    def test_tagesbeginn_sechs_monate(self):
        # Beginn 03.02.2025 zählt mit: Ende mit Ablauf 02.08.2025 (Sa, keine Verschiebung)
        e = r.frist_ende(D(2025, 2, 3), 6, "monate", "HE", False, beginn_mitzaehlen=True, regel_ohne_verschiebung="FR-14")
        self.assertEqual(e.datum, D(2025, 8, 2))

    def test_jahresfrist_ab_29_februar_unsicher(self):
        e = r.frist_ende(D(2028, 2, 29), 1, "jahre", "HE", False)
        self.assertEqual(e.datum, D(2029, 2, 28))
        self.assertTrue(e.unsicher)

    def test_fristende_samstag_frauentag_berlin(self):
        # 08.02.2025 + 1 Monat = Sa 08.03.2025 -> Mo 10.03.2025 (BE und HH)
        self.assertEqual(r.frist_ende(D(2025, 2, 8), 1, "monate", "BE", True).datum, D(2025, 3, 10))
        self.assertEqual(r.frist_ende(D(2025, 2, 8), 1, "monate", "HH", True).datum, D(2025, 3, 10))

    def test_frauentag_2027_montag(self):
        # 08.02.2027 + 1 Monat = Mo 08.03.2027: BE/MV Feiertag -> Di 09.03.2027, HH bleibt
        for land, soll in (("BE", D(2027, 3, 9)), ("MV", D(2027, 3, 9)), ("HH", D(2027, 3, 8))):
            self.assertEqual(r.frist_ende(D(2027, 2, 8), 1, "monate", land, True, regime="SGG").datum, soll, land)

    def test_fronleichnam_nrw_vs_niedersachsen(self):
        # 19.05.2025 + 1 Monat = Do 19.06.2025 Fronleichnam: NW -> Fr 20.06.2025, NI bleibt
        self.assertEqual(r.frist_ende(D(2025, 5, 19), 1, "monate", "NW", True, regime="VwGO").datum, D(2025, 6, 20))
        self.assertEqual(r.frist_ende(D(2025, 5, 19), 1, "monate", "NI", True, regime="VwGO").datum, D(2025, 6, 19))

    def test_buss_und_bettag_fristende(self):
        # So 19.10.2025 + 1 Monat = Mi 19.11.2025: SN -> Do 20.11.2025, TH bleibt
        self.assertEqual(r.frist_ende(D(2025, 10, 19), 1, "monate", "SN", True, regime="AO").datum, D(2025, 11, 20))
        self.assertEqual(r.frist_ende(D(2025, 10, 19), 1, "monate", "TH", True, regime="AO").datum, D(2025, 11, 19))

    def test_weltkindertag_fristende(self):
        # 20.08.2027 + 1 Monat = Mo 20.09.2027: TH -> Di 21.09.2027, SN bleibt
        self.assertEqual(r.frist_ende(D(2027, 8, 20), 1, "monate", "TH", True, regime="SGG").datum, D(2027, 9, 21))
        self.assertEqual(r.frist_ende(D(2027, 8, 20), 1, "monate", "SN", True, regime="SGG").datum, D(2027, 9, 20))

    def test_karfreitag_bis_ostermontag(self):
        # 03.03.2026 + 1 Monat = Fr 03.04.2026 Karfreitag -> Di 07.04.2026
        self.assertEqual(r.frist_ende(D(2026, 3, 3), 1, "monate", "RP", True, regime="SGG").datum, D(2026, 4, 7))

    def test_pfingsten_wie_bag_2_azr_156_24(self):
        # Zugang Sa 14.05.2022 + 3 Wochen = Sa 04.06.2022, Pfingstsonntag, Pfingstmontag -> Di 07.06.2022
        self.assertEqual(r.kschg_klage(D(2022, 5, 14), "NW").datum, D(2022, 6, 7))

    def test_fristbeginn_samstag_wird_nicht_verschoben(self):
        # Zustellung Sa 05.07.2025: Fristbeginn So 06.07.2025, Ende Di 05.08.2025 (FR-12)
        e = r.frist_ende(D(2025, 7, 5), 1, "monate", "BB", True, regime="VwGO")
        self.assertEqual(e.details["fristbeginn"], D(2025, 7, 6))
        self.assertEqual(e.datum, D(2025, 8, 5))
        self.assertTrue(any(s.startswith("[FR-12]") for s in e.rechenweg))


class Rechtsbehelf(unittest.TestCase):
    def test_widerspruch_sgb2_fiktion_sonntag(self):
        # Mi 14.05.2025 + 4 = So 18.05.2025 (keine Verschiebung) + 1 Monat = Mi 18.06.2025
        e = r.rechtsbehelf("widerspruch_sgb2", "TH", aufgabe_post=D(2025, 5, 14))
        self.assertEqual(e.details["bekanntgabe"], D(2025, 5, 18))
        self.assertEqual(e.datum, D(2025, 6, 18))

    def test_einspruch_ao_fiktion_sonntag_dann_fronleichnam(self):
        # Mi 14.05.2025 + 4 = So 18.05. -> Mo 19.05.2025; + 1 Monat = Do 19.06.2025 Fronleichnam in BY -> Fr 20.06.
        self.assertEqual(r.rechtsbehelf("einspruch_ao", "BY", aufgabe_post=D(2025, 5, 14)).datum, D(2025, 6, 20))
        self.assertEqual(r.rechtsbehelf("einspruch_ao", "NI", aufgabe_post=D(2025, 5, 14)).datum, D(2025, 6, 19))

    def test_widerspruch_vwvfg_pzu_monatsende(self):
        # Zustellung Fr 31.01.2025 -> Fr 28.02.2025
        e = r.rechtsbehelf("widerspruch_vwvfg", "RP", zustellart="pzu", zustellung=D(2025, 1, 31))
        self.assertEqual(e.datum, D(2025, 2, 28))

    def test_klage_vwgo_nur_mit_zustellung(self):
        with self.assertRaises(ValueError):
            r.rechtsbehelf("klage_vwgo", "NI", aufgabe_post=D(2025, 3, 3))

    def test_klage_sgg_zustellung_samstag(self):
        # Zustellung Sa 30.08.2025 -> Di 30.09.2025
        e = r.rechtsbehelf("klage_sgg", "MV", zustellart="pzu", zustellung=D(2025, 8, 30))
        self.assertEqual(e.datum, D(2025, 9, 30))

    def test_jahresfrist_ohne_rbb_vwgo(self):
        # Zustellung Mi 12.03.2025 -> ein Jahr -> Do 12.03.2026
        e = r.rechtsbehelf("widerspruch_vwvfg", "BB", zustellart="pzu", zustellung=D(2025, 3, 12), rbb=False)
        self.assertEqual(e.datum, D(2026, 3, 12))
        self.assertIn("§ 58 Abs. 2 VwGO", e.normen)

    def test_jahresfrist_ohne_rbb_ao_mit_verschiebung_unsicher(self):
        # Mo 03.02.2025 + 4 = Fr 07.02.2025; + 1 Jahr = Sa 07.02.2026 -> Mo 09.02.2026 (als unsicher markiert)
        e = r.rechtsbehelf("einspruch_ao", "SL", aufgabe_post=D(2025, 2, 3), rbb=False)
        self.assertEqual(e.datum, D(2026, 2, 9))
        self.assertTrue(e.unsicher)

    def test_widerspruch_sgb2_neujahr(self):
        # Do 27.11.2025 + 4 = Mo 01.12.2025; + 1 Monat = Do 01.01.2026 -> Fr 02.01.2026
        self.assertEqual(r.rechtsbehelf("widerspruch_sgb2", "HB", aufgabe_post=D(2025, 11, 27)).datum,
                         D(2026, 1, 2))

    def test_klage_fgo_ostermontag(self):
        # Mo 02.03.2026 + 4 = Fr 06.03.2026; + 1 Monat = Mo 06.04.2026 Ostermontag -> Di 07.04.2026
        e = r.rechtsbehelf("klage_fgo", "BY", aufgabe_post=D(2026, 3, 2))
        self.assertEqual(e.details["bekanntgabe"], D(2026, 3, 6))
        self.assertEqual(e.datum, D(2026, 4, 7))
        for n in ("§ 47 Abs. 1 FGO", "§ 54 Abs. 2 FGO", "§ 222 Abs. 2 ZPO"):
            self.assertIn(n, e.normen)
        self.assertFalse(e.unsicher)

    def test_sgg_jahresfrist_ohne_rbb(self):
        # PZU Do 12.06.2025, § 66 Abs. 2 SGG: ein Jahr -> Fr 12.06.2026 (HH, Werktag)
        e = r.rechtsbehelf("widerspruch_sgb2", "HH", zustellart="pzu", zustellung=D(2025, 6, 12), rbb=False)
        self.assertEqual(e.datum, D(2026, 6, 12))
        self.assertIn("§ 66 Abs. 2 SGG", e.normen)
        self.assertFalse(e.unsicher)
        # PZU Sa 13.06.2026: Ende So 13.06.2027 -> Mo 14.06.2027, Verschiebung der Jahresfrist unsicher
        e = r.rechtsbehelf("klage_sgg", "HH", zustellart="pzu", zustellung=D(2026, 6, 13), rbb=False)
        self.assertEqual(e.datum, D(2027, 6, 14))
        self.assertTrue(e.unsicher)

    def test_drei_tage_fehlermodell(self):
        # Fehlermodell mit alter Fassung: Mo 03.02.2025 + 3 = Do 06.02. -> + 1 Monat = Do 06.03.2025
        e = r.rechtsbehelf("widerspruch_sgb2", "HB", aufgabe_post=D(2025, 2, 3), fiktion_fassung="bis2024")
        self.assertEqual(e.datum, D(2025, 3, 6))


class KSchG(unittest.TestCase):
    def test_reformationstag_sachsen_vs_bayern(self):
        # Fr 10.10.2025 + 21 Tage = Fr 31.10.2025: SN Reformationstag -> Mo 03.11.2025; BY bleibt
        self.assertEqual(r.kschg_klage(D(2025, 10, 10), "SN").datum, D(2025, 11, 3))
        self.assertEqual(r.kschg_klage(D(2025, 10, 10), "BY").datum, D(2025, 10, 31))

    def test_mittwoch_bis_mittwoch(self):
        self.assertEqual(r.kschg_klage(D(2025, 10, 22), "HE").datum, D(2025, 11, 12))

    def test_zweiter_weihnachtstag(self):
        # Fr 05.12.2025 + 21 = Fr 26.12.2025 -> Sa, So -> Mo 29.12.2025
        self.assertEqual(r.kschg_klage(D(2025, 12, 5), "BW").datum, D(2025, 12, 29))

    def test_gemeinde_feiertag_im_rechenweg(self):
        # Fr 18.07.2025 + 21 = Fr 08.08.2025 Augsburger Friedensfest -> Mo 11.08.2025
        e = r.kschg_klage(D(2025, 7, 18), "BY", gemeinde="friedensfest")
        self.assertEqual(e.datum, D(2025, 8, 11))
        satz = next(s for s in e.rechenweg if s.startswith("[KS-03]"))
        self.assertIn("übersprungen: Fr 08.08.2025 Augsburger Hohes Friedensfest", satz)
        self.assertNotIn("Werktag,", satz.split("übersprungen:")[1])


class Miete(unittest.TestCase):
    def test_januar_2026_beispiel_mi01(self):
        # 01.01. Feiertag, Fr 02.01. = 1., Sa 03.01. = 2., Mo 05.01. = 3. Werktag -> Ende 31.03.2026
        e = r.kuendigung_miete(D(2026, 1, 5), "BY")
        self.assertEqual(e.details["dritter_werktag"], D(2026, 1, 5))
        self.assertEqual(e.datum, D(2026, 3, 31))

    def test_januar_2026_zu_spaet(self):
        self.assertEqual(r.kuendigung_miete(D(2026, 1, 6), "BY").datum, D(2026, 4, 30))

    def test_samstag_zaehlt_mit_august_2026(self):
        # Sa 01.08. = 1., Mo 03.08. = 2., Di 04.08. = 3. Werktag
        self.assertEqual(r.kuendigung_miete(D(2026, 8, 4), "HE").datum, D(2026, 10, 31))
        self.assertEqual(r.kuendigung_miete(D(2026, 8, 5), "HE").datum, D(2026, 11, 30))

    def test_fehlermodell_samstag_nicht_gezaehlt(self):
        self.assertEqual(r.kuendigung_miete(D(2026, 8, 5), "HE", samstag_ist_werktag=False).datum, D(2026, 10, 31))

    def test_dritter_werktag_samstag_strittig(self):
        # April 2026: Mi 01. = 1., Do 02. = 2., Fr 03. Karfreitag, Sa 04. = 3. Werktag (MI-05)
        self.assertTrue(r.kuendigung_miete(D(2026, 4, 7), "BE").strittig)   # Dienstag nach Ostern
        e = r.kuendigung_miete(D(2026, 4, 4), "BE")
        self.assertFalse(e.strittig)
        self.assertEqual(e.datum, D(2026, 6, 30))
        e = r.kuendigung_miete(D(2026, 4, 8), "BE")
        self.assertFalse(e.strittig)
        self.assertEqual(e.datum, D(2026, 7, 31))

    def test_mai_2027_feiertag_samstag(self):
        # Sa 01.05.2027 Feiertag, So 02.: 1. Mo 03., 2. Di 04., 3. Mi 05.05. -> 31.07.2027
        self.assertEqual(r.kuendigung_miete(D(2027, 5, 5), "NW").datum, D(2027, 7, 31))

    def test_allerheiligen_bw_vs_sachsen(self):
        # Mo 01.11.2027: BW Allerheiligen -> 3. Werktag Do 04.11.; SN -> Mi 03.11. (dann Schaltjahr-Ende)
        self.assertEqual(r.kuendigung_miete(D(2027, 11, 4), "BW").datum, D(2028, 1, 31))
        self.assertEqual(r.kuendigung_miete(D(2027, 11, 4), "SN").datum, D(2028, 2, 29))

    def test_mietende_samstag_nicht_verschoben(self):
        # BE Nov 2025: Sa 01. = 1., Mo 03. = 2., Di 04. = 3.; Zugang 03.11. -> Ende Sa 31.01.2026
        e = r.kuendigung_miete(D(2025, 11, 3), "BE")
        self.assertEqual(e.datum, D(2026, 1, 31))
        self.assertTrue(any(s.startswith("[FR-13]") for s in e.rechenweg))

    def test_vermieter_neun_jahre(self):
        # Überlassung 01.04.2016, Zugang Mo 02.02.2026: 9 volle Jahre -> 9 Monate -> 31.10.2026
        e = r.kuendigung_miete(D(2026, 2, 2), "SH", partei="vermieter", ueberlassung=D(2016, 4, 1))
        self.assertEqual(e.details["frist_monate"], 9)
        self.assertEqual(e.datum, D(2026, 10, 31))

    def test_vermieter_fuenf_jahre(self):
        # Überlassung 15.06.2020, Zugang Di 03.03.2026: 5 Jahre -> 6 Monate -> 31.08.2026
        e = r.kuendigung_miete(D(2026, 3, 3), "SL", partei="vermieter", ueberlassung=D(2020, 6, 15))
        self.assertEqual(e.datum, D(2026, 8, 31))

    def test_spaetester_zugang(self):
        self.assertEqual(r.spaetester_zugang_miete(D(2026, 3, 31), "BY").datum, D(2026, 1, 5))

    def test_spaetester_zugang_vermieter(self):
        # Überlassung 01.04.2016, Mietende 31.10.2026: 9 Monate, 3. Werktag Februar 2026 in HE = Mi 04.02.2026
        e = r.spaetester_zugang_miete(D(2026, 10, 31), "HE", partei="vermieter", ueberlassung=D(2016, 4, 1))
        self.assertEqual(e.datum, D(2026, 2, 4))
        self.assertFalse(e.unsicher)

    def test_spaetester_zugang_vermieter_staffelwechsel(self):
        # Überlassung 04.02.2021: fünf Jahre enden mit Ablauf Di 03.02.2026. Zugang am 03.02. -> 4 Jahre,
        # 3 Monate, Ende 30.04.2026; ab 04.02. 6 Monate (31.07.2026). Jahrestag im Zugangsmonat -> unsicher.
        e = r.spaetester_zugang_miete(D(2026, 4, 30), "HE", partei="vermieter", ueberlassung=D(2021, 2, 4))
        self.assertEqual(e.datum, D(2026, 2, 3))
        self.assertTrue(e.unsicher)
        self.assertEqual(r.kuendigung_miete(D(2026, 2, 3), "HE", partei="vermieter",
                                            ueberlassung=D(2021, 2, 4)).datum, D(2026, 4, 30))
        self.assertEqual(r.kuendigung_miete(D(2026, 2, 4), "HE", partei="vermieter",
                                            ueberlassung=D(2021, 2, 4)).datum, D(2026, 7, 31))

    def test_vermieter_ueberlassung_29_februar(self):
        # Überlassung 29.02.2020, Zugang Fr 28.02.2025: erst 4 volle Jahre (Ablauf 28.02.2025) -> 3 Monate.
        # 3. Werktag Feb 2025 in BE: Sa 01., Mo 03., Di 04. -> zu spät -> Ende 31.05.2025; als unsicher markiert.
        e = r.kuendigung_miete(D(2025, 2, 28), "BE", partei="vermieter", ueberlassung=D(2020, 2, 29))
        self.assertEqual(e.details["frist_monate"], 3)
        self.assertEqual(e.datum, D(2025, 5, 31))
        self.assertTrue(e.unsicher)

    def test_zugang_fehlt(self):
        with self.assertRaises(ValueError):
            r.kuendigung_miete(None, "BY")


class Arbeit(unittest.TestCase):
    def test_vier_wochen_zum_15(self):
        # 18.10.2025 + 28 = 15.11.2025 -> Termin 15.11.; 19.10. -> 16.11. -> 30.11.2025
        self.assertEqual(r.kuendigung_arbeit(D(2025, 10, 18), 0, False).datum, D(2025, 11, 15))
        self.assertEqual(r.kuendigung_arbeit(D(2025, 10, 19), 0, False).datum, D(2025, 11, 30))

    def test_ar04_beispiele(self):
        self.assertEqual(r.kuendigung_arbeit(D(2025, 11, 30), 3, False).datum, D(2025, 12, 31))
        self.assertEqual(r.kuendigung_arbeit(D(2025, 12, 1), 2, False).datum, D(2026, 1, 31))
        self.assertEqual(r.kuendigung_arbeit(D(2025, 1, 31), 4, False).datum, D(2025, 2, 28))

    def test_schaltjahr_2028(self):
        # 31.12.2027 + 2 Monate = 29.02.2028; 30.11.2027 + 3 Monate = 29.02.2028 (gekappt)
        self.assertEqual(r.kuendigung_arbeit(D(2027, 12, 31), 6, False).datum, D(2028, 2, 29))
        self.assertEqual(r.kuendigung_arbeit(D(2027, 11, 30), 9, False).datum, D(2028, 2, 29))

    def test_probezeit_zwei_wochen(self):
        # Mo 30.06.2025 + 14 = Mo 14.07.2025 (wie BAG 6 AZR 519/07)
        self.assertEqual(r.kuendigung_arbeit(D(2025, 6, 30), None, True).datum, D(2025, 7, 14))

    def test_probezeitende(self):
        # Beginn 03.02.2025, sechs Monate -> Ende 02.08.2025; Zugang 02.08. noch in der Probezeit
        e = r.kuendigung_arbeit(D(2025, 8, 2), None, True, beginn=D(2025, 2, 3))
        self.assertEqual(e.details["probezeit_ende"], D(2025, 8, 2))
        self.assertEqual(e.datum, D(2025, 8, 16))
        # Zugang Mo 04.08.2025: nach der Probezeit -> 4 Wochen: 01.09. -> Termin 15.09.2025
        self.assertEqual(r.kuendigung_arbeit(D(2025, 8, 4), None, True, beginn=D(2025, 2, 3)).datum, D(2025, 9, 15))

    def test_zwanzig_jahre(self):
        # 15.03.2026 + 7 Monate = 15.10.2026 -> 31.10.2026
        self.assertEqual(r.kuendigung_arbeit(D(2026, 3, 15), 22, False).datum, D(2026, 10, 31))

    def test_arbeitnehmer_immer_vier_wochen(self):
        # Mo 03.11.2025 + 28 = 01.12.2025 -> 15.12.2025
        self.assertEqual(r.kuendigung_arbeit(D(2025, 11, 3), 15, False, partei="arbeitnehmer").datum,
                         D(2025, 12, 15))

    def test_zwei_jahre_grenze(self):
        # Beginn 15.05.2023: am 14.05.2025 erst 1 Jahr -> 11.06. -> 15.06.2025; am 15.05.2025 2 Jahre -> 30.06.2025
        self.assertEqual(r.kuendigung_arbeit(D(2025, 5, 14), None, False, beginn=D(2023, 5, 15)).datum,
                         D(2025, 6, 15))
        self.assertEqual(r.kuendigung_arbeit(D(2025, 5, 15), None, False, beginn=D(2023, 5, 15)).datum,
                         D(2025, 6, 30))

    def test_jahre_seit(self):
        self.assertEqual(r.jahre_seit(D(2019, 9, 1), D(2024, 8, 31)), 4)
        self.assertEqual(r.jahre_seit(D(2019, 9, 1), D(2024, 9, 1)), 5)

    def test_jahre_seit_29_februar(self):
        # Beginn 29.02.2020: fünf Jahre enden mit Ablauf 28.02.2025 (§ 188 Abs. 3 BGB, wie beim Lebensalter)
        self.assertEqual(r.jahre_seit(D(2020, 2, 29), D(2025, 2, 28)), 4)
        self.assertEqual(r.jahre_seit(D(2020, 2, 29), D(2025, 3, 1)), 5)
        self.assertEqual(r.jahre_seit(D(2020, 2, 29), D(2024, 2, 29)), 4)
        # gleiche Rechnung wie frist_ende ab Tagesbeginn: 2 Jahre ab 29.02.2024 enden mit Ablauf 28.02.2026
        self.assertEqual(r.frist_ende(D(2024, 2, 29), 2, "jahre", "BE", False, beginn_mitzaehlen=True).datum,
                         D(2026, 2, 28))
        self.assertEqual(r.jahre_seit(D(2024, 2, 29), D(2026, 2, 28)), 1)
        self.assertEqual(r.jahre_seit(D(2024, 2, 29), D(2026, 3, 1)), 2)

    def test_622_beginn_29_februar(self):
        # Zugang 28.02.2025: 4 Jahre -> 1 Monat -> 28.03.2025 -> 31.03.2025 (unsicher, weil Stufe 5 Jahre am Rand)
        e = r.kuendigung_arbeit(D(2025, 2, 28), None, False, beginn=D(2020, 2, 29))
        self.assertEqual(e.details["jahre"], 4)
        self.assertEqual(e.datum, D(2025, 3, 31))
        self.assertTrue(e.unsicher)
        # Zugang Mo 03.03.2025: 5 Jahre -> 2 Monate -> 03.05.2025 -> 31.05.2025
        e = r.kuendigung_arbeit(D(2025, 3, 3), None, False, beginn=D(2020, 2, 29))
        self.assertEqual(e.datum, D(2025, 5, 31))
        self.assertFalse(e.unsicher)

    def test_622_stufen_10_12_15(self):
        # 15.03.2026 + 4/5/6 Monate = 15.07./15.08./15.09.2026 -> Monatsende
        self.assertEqual(r.kuendigung_arbeit(D(2026, 3, 15), 10, False).datum, D(2026, 7, 31))
        self.assertEqual(r.kuendigung_arbeit(D(2026, 3, 15), 12, False).datum, D(2026, 8, 31))
        self.assertEqual(r.kuendigung_arbeit(D(2026, 3, 15), 15, False).datum, D(2026, 9, 30))
        self.assertEqual(r.kuendigung_arbeit(D(2026, 3, 15), 19, False).datum, D(2026, 9, 30))

    def test_622_stufe_aus_dem_beginn(self):
        # Beginn 01.04.2014: zwölf Jahre enden mit Ablauf 31.03.2026.
        # Zugang Di 31.03.2026: 11 Jahre -> 4 Monate -> 31.07.2026; Zugang Mi 01.04.2026: 12 Jahre -> 5 Monate
        # -> 01.09.2026 -> 30.09.2026
        self.assertEqual(r.kuendigung_arbeit(D(2026, 3, 31), None, False, beginn=D(2014, 4, 1)).datum,
                         D(2026, 7, 31))
        self.assertEqual(r.kuendigung_arbeit(D(2026, 4, 1), None, False, beginn=D(2014, 4, 1)).datum,
                         D(2026, 9, 30))

    def test_probezeitende_fehlender_tag(self):
        # Beginn Di 31.03.2026: der 31.09. fehlt -> Ende mit Ablauf Mi 30.09.2026 (§ 188 Abs. 3 BGB).
        # Zugang Mi 30.09.2026 liegt noch in der Probezeit: + 14 Tage = Mi 14.10.2026. Als unsicher markiert.
        e = r.kuendigung_arbeit(D(2026, 9, 30), None, True, beginn=D(2026, 3, 31))
        self.assertEqual(e.details["probezeit_ende"], D(2026, 9, 30))
        self.assertEqual(e.datum, D(2026, 10, 14))
        self.assertIn("§ 188 Abs. 3 BGB", e.normen)
        self.assertTrue(e.unsicher)
        for beginn, ende in ((D(2025, 8, 31), D(2026, 2, 28)), (D(2025, 8, 30), D(2026, 2, 28)),
                             (D(2025, 8, 29), D(2026, 2, 28)), (D(2025, 8, 28), D(2026, 2, 27)),
                             (D(2027, 8, 31), D(2028, 2, 29)), (D(2027, 8, 30), D(2028, 2, 29))):
            e = r.kuendigung_arbeit(beginn + timedelta(days=10), None, True, beginn=beginn)
            self.assertEqual(e.details["probezeit_ende"], ende, beginn)
        # Beginn 31.08.2025, Zugang Sa 28.02.2026: noch Probezeit -> Sa 14.03.2026
        self.assertEqual(r.kuendigung_arbeit(D(2026, 2, 28), None, True, beginn=D(2025, 8, 31)).datum,
                         D(2026, 3, 14))


class Spanne(unittest.TestCase):
    """Feiertagstabelle 2020 bis 2030: Abbruch nur, wenn Feiertage das Datum bestimmen könnten."""

    def test_nur_hinweis_ausserhalb_der_spanne(self):
        # 15.06.2030 + 7 Monate = 15.01.2031 -> 31.01.2031 (Termin wird nie verschoben)
        self.assertEqual(r.kuendigung_arbeit(D(2030, 6, 15), 20, False, land="BE").datum, D(2031, 1, 31))
        self.assertEqual(r.kuendigung_arbeit(D(2030, 6, 15), 20, False).datum, D(2031, 1, 31))
        # Dez. 2030 BE: Mo 02., Di 03., Mi 04. -> rechtzeitig -> Fr 28.02.2031
        self.assertEqual(r.kuendigung_miete(D(2030, 12, 3), "BE").datum, D(2031, 2, 28))

    def test_abbruch_wenn_feiertage_das_datum_bestimmen(self):
        with self.assertRaises(ValueError):
            r.bekanntgabe_fiktion(D(2030, 12, 29), "AO", "BE")
        with self.assertRaises(ValueError):
            r.rechtsbehelf("widerspruch_vwvfg", "BE", zustellart="pzu", zustellung=D(2030, 12, 15))


class Originaldaten(unittest.TestCase):
    """Daten aus Urteilen (Fundstellen in recht/belege.json). Vor 2020 nur Fälle ohne Verschiebung,
    weil die Feiertagstabelle erst 2020 beginnt."""

    def test_bag_2_azr_483_14(self):
        # Zugang Mi 24.10.2012, Klage am Mi 14.11.2012 noch rechtzeitig (kein Feiertag, keine Verschiebung)
        self.assertEqual(r.frist_ende(D(2012, 10, 24), 3, "wochen", "NW", False, regime="ArbGG").datum,
                         D(2012, 11, 14))

    def test_bag_6_azr_519_07(self):
        # Probezeitkündigung, Zugang Fr 30.06.2006, Ende Fr 14.07.2006
        self.assertEqual(r.kuendigung_arbeit(D(2006, 6, 30), None, True).datum, D(2006, 7, 14))

    def test_bag_2_azr_382_01(self):
        # Probezeit ab 03.02.2000, sechs Monate: Ende mit Ablauf 02.08.2000; Zugang 03.08.2000 danach
        e = r.kuendigung_arbeit(D(2000, 8, 3), None, True, beginn=D(2000, 2, 3))
        self.assertEqual(e.details["probezeit_ende"], D(2000, 8, 2))
        self.assertNotEqual(e.details.get("frist"), "2 Wochen")

    def test_bag_2_azr_1057_12(self):
        # Wartezeit ab 15.05.2010 (Starttag zählt), sechs Monate enden mit Ablauf 14.11.2010
        self.assertEqual(r.frist_ende(D(2010, 5, 15), 6, "monate", "NW", False, beginn_mitzaehlen=True).datum,
                         D(2010, 11, 14))

    def test_bfh_vi_r_18_22(self):
        # Bekanntgabe 18.06.2018, Einspruchsfrist bis Ablauf Mi 18.07.2018
        self.assertEqual(r.frist_ende(D(2018, 6, 18), 1, "monate", "NW", False, regime="AO").datum,
                         D(2018, 7, 18))


class Rechenweg(unittest.TestCase):
    ID = re.compile(r"^\[([A-Z]{1,2}-\d{2})(?:, ([A-Z]{1,2}-\d{2}))*\]")

    def test_jeder_satz_hat_gueltige_regel_id(self):
        import json
        from pathlib import Path
        belege = json.loads((Path(__file__).resolve().parents[1] / "recht" / "belege.json").read_text("utf-8"))
        ids = {regel["id"] for g in belege for regel in g["regeln"]}
        faelle = [
            r.rechtsbehelf("einspruch_ao", "SH", aufgabe_post=D(2025, 10, 27)),
            r.rechtsbehelf("widerspruch_sgb2", "TH", aufgabe_post=D(2025, 5, 14)),
            r.rechtsbehelf("klage_vwgo", "NW", zustellart="pzu", zustellung=D(2025, 5, 19)),
            r.rechtsbehelf("widerspruch_vwvfg", "BB", zustellart="pzu", zustellung=D(2025, 3, 12), rbb=False),
            r.kschg_klage(D(2025, 10, 10), "SN"),
            r.kuendigung_miete(D(2026, 8, 5), "HE"),
            r.kuendigung_miete(D(2026, 2, 2), "SH", partei="vermieter", ueberlassung=D(2016, 4, 1)),
            r.kuendigung_arbeit(D(2027, 12, 31), 6, False, land="NI"),
            r.kuendigung_arbeit(D(2025, 8, 4), None, True, beginn=D(2025, 2, 3)),
            r.kuendigung_arbeit(D(2026, 9, 30), None, True, beginn=D(2026, 3, 31)),
            r.rechtsbehelf("klage_fgo", "BY", aufgabe_post=D(2026, 3, 2)),
            r.spaetester_zugang_miete(D(2026, 4, 30), "HE", partei="vermieter", ueberlassung=D(2021, 2, 4)),
        ]
        for e in faelle:
            self.assertTrue(e.rechenweg)
            for satz in e.rechenweg:
                m = self.ID.match(satz)
                self.assertIsNotNone(m, satz)
                for rid in re.findall(r"[A-Z]{1,2}-\d{2}", m.group(0)):
                    self.assertIn(rid, ids, satz)


def _ostern_gauss(x: int) -> date:
    """Gaußsche Osterformel in der ergänzten Form (Lichtenberg), unabhängig von feiertage.ostersonntag."""
    k = x // 100
    m = 15 + (3 * k + 3) // 4 - (8 * k + 13) // 25
    s = 2 - (3 * k + 3) // 4
    a = x % 19
    d = (19 * a + m) % 30
    r_ = (d + a // 11) // 29
    og = 21 + d - r_
    sz = 7 - (x + x // 4 + s) % 7
    oe = 7 - (og - sz) % 7
    return date(x, 3, 1) + timedelta(days=og + oe - 1)


# eigene Feiertagsliste, unabhängig von feiertage.py getippt (Stand der Landesgesetze 2026)
_LANDESREGELN = {
    "hl3k": ("BW", "BY", "ST"), "fronleichnam": ("BW", "BY", "HE", "NW", "RP", "SL"), "mariae": ("SL",),
    "allerheiligen": ("BW", "BY", "NW", "RP", "SL"), "busstag": ("SN",), "oster_pfingstsonntag": ("BB",),
    "reformation_alt": ("BB", "MV", "SN", "ST", "TH"), "reformation_neu": ("HB", "HH", "NI", "SH"),
}


def _feiertage_unabhaengig(j: int, land: str) -> set:
    o = _ostern_gauss(j)
    t = {date(j, 1, 1), o - timedelta(days=2), o + timedelta(days=1), date(j, 5, 1), o + timedelta(days=39),
         o + timedelta(days=50), date(j, 10, 3), date(j, 12, 25), date(j, 12, 26)}
    if land in _LANDESREGELN["hl3k"]:
        t.add(date(j, 1, 6))
    if (land == "BE" and j >= 2019) or (land == "MV" and j >= 2023):
        t.add(date(j, 3, 8))
    if land in _LANDESREGELN["oster_pfingstsonntag"]:
        t |= {o, o + timedelta(days=49)}
    if land in _LANDESREGELN["fronleichnam"]:
        t.add(o + timedelta(days=60))
    if land in _LANDESREGELN["mariae"]:
        t.add(date(j, 8, 15))
    if land == "TH" and j >= 2019:
        t.add(date(j, 9, 20))
    if land in _LANDESREGELN["reformation_alt"] or (land in _LANDESREGELN["reformation_neu"] and j >= 2018):
        t.add(date(j, 10, 31))
    if land in _LANDESREGELN["allerheiligen"]:
        t.add(date(j, 11, 1))
    if land in _LANDESREGELN["busstag"]:
        b = date(j, 11, 16)
        t.add(b + timedelta(days=(2 - b.weekday()) % 7))
    t |= {x for x in (date(2020, 5, 8), date(2025, 5, 8), date(2028, 6, 17)) if land == "BE" and x.year == j}
    return t


def _tagesbeginn_ueberlauf(anfang: date, monate: int) -> date:
    """Frist ab Tagesbeginn: Tag vor dem Tag gleicher Zahl; fehlt er, läuft man in den Folgemonat über und
    nimmt den Tag davor (= Monatsletzter). Ohne Kappung per min() wie im Rechner."""
    m = anfang.month - 1 + monate
    zielmonat = m % 12 + 1
    x = date(anfang.year + m // 12, zielmonat, 1)
    while x.month == zielmonat and x.day < anfang.day:
        x += timedelta(days=1)
    return x - timedelta(days=1)


class Gegenprobe(unittest.TestCase):
    """Zweite, unabhängige Implementierung: Tag für Tag abzählen statt Monatsarithmetik."""

    @staticmethod
    def _monatsfrist_abzaehlen(ereignis: date, monate: int) -> date:
        # Ende = letzter Tag d mit: (Monate zwischen ereignis und d) < monate, wobei ein Monat
        # erst mit Erreichen der gleichen Tageszahl (oder dem Monatsletzten, wenn es sie nicht gibt) vollendet ist.
        d = ereignis
        while True:
            n = d + timedelta(days=1)
            mon = (n.year - ereignis.year) * 12 + n.month - ereignis.month
            letzter = (date(n.year + (n.month == 12), n.month % 12 + 1, 1) - timedelta(days=1)).day
            tag = min(ereignis.day, letzter)
            voll = mon > monate or (mon == monate and n.day > tag)
            if voll:
                return d
            d = n

    @staticmethod
    def _termin_622_abzaehlen(zugang: date, m: int) -> date:
        # Kandidaten-Termine: jeder Monatsletzte (m >= 1) bzw. jeder 15. und Monatsletzte (m == 0).
        # Termin = der früheste Kandidat T, für den zwischen Zugang und T mindestens die Frist liegt.
        d = zugang
        while True:
            d += timedelta(days=1)
            monatsletzter = (d + timedelta(days=1)).day == 1
            if m == 0:
                if (d.day == 15 or monatsletzter) and (d - zugang).days >= 28:
                    return d
            elif monatsletzter and Gegenprobe._monatsfrist_abzaehlen(zugang, m) <= d:
                return d

    def test_monatsfrist_gegen_abzaehlen(self):
        d = D(2025, 1, 1)
        while d <= D(2027, 12, 31):
            for n in (1, 2, 3):
                self.assertEqual(r.frist_ende(d, n, "monate", "BE", False).datum, self._monatsfrist_abzaehlen(d, n),
                                 (d, n))
            d += timedelta(days=1)

    def test_ar01_ar04_gegen_abzaehlen(self):
        d = D(2025, 1, 1)
        while d <= D(2027, 12, 31):
            for jahre, m in ((0, 0), (2, 1), (5, 2), (8, 3), (20, 7)):
                self.assertEqual(r.kuendigung_arbeit(d, jahre, False).datum, self._termin_622_abzaehlen(d, m),
                                 (d, jahre))
            d += timedelta(days=1)

    def test_feiertagstabelle_gegen_eigene_liste(self):
        for j in range(2020, 2031):
            for land in LAENDER:
                self.assertEqual(set(feiertage(j, land)), _feiertage_unabhaengig(j, land), (j, land))
        for j in range(2020, 2031):
            self.assertEqual(ostersonntag(j), _ostern_gauss(j), j)

    def test_verschiebung_alle_laender(self):
        cache = {}
        d = D(2025, 1, 1)
        while d <= D(2027, 12, 31):
            roh = self._monatsfrist_abzaehlen(d, 1)
            for land in LAENDER:
                ende = roh
                while ende.weekday() >= 5 or ende in cache.setdefault((ende.year, land),
                                                                      _feiertage_unabhaengig(ende.year, land)):
                    ende += timedelta(days=1)
                self.assertEqual(r.frist_ende(d, 1, "monate", land, True).datum, ende, (d, land))
            d += timedelta(days=1)

    def test_tagesbeginn_gegen_ueberlauf(self):
        d = D(2020, 1, 1)
        while d <= D(2027, 12, 31):
            for n in (1, 2, 3, 6, 12):
                self.assertEqual(r.frist_ende(d, n, "monate", "BE", False, beginn_mitzaehlen=True).datum,
                                 _tagesbeginn_ueberlauf(d, n), (d, n))
            d += timedelta(days=1)

    def test_probezeitende_gegen_ueberlauf(self):
        b = D(2020, 1, 1)
        while b <= D(2027, 6, 30):
            e = r.kuendigung_arbeit(b + timedelta(days=10), None, True, beginn=b)
            self.assertEqual(e.details["probezeit_ende"], _tagesbeginn_ueberlauf(b, 6), b)
            b += timedelta(days=1)

    def test_jahre_seit_und_622_aus_dem_beginn(self):
        def jahre_unabhaengig(beginn, stichtag):
            n = 0
            while _tagesbeginn_ueberlauf(beginn, 12 * (n + 1)) < stichtag:
                n += 1
            return n

        def staffel(j):
            return next((m for g, m in ((20, 7), (15, 6), (12, 5), (10, 4), (8, 3), (5, 2), (2, 1)) if j >= g), 0)

        beginne = [D(2005, 1, 1) + timedelta(days=i) for i in range(0, 731, 3)] + \
                  [D(2004, 2, 29), D(2008, 2, 29), D(2012, 2, 29), D(2016, 2, 29), D(2020, 2, 29)]
        for b in beginne:
            for grenze in (1, 2, 5, 8, 10, 12, 15, 20):
                if b.year + grenze > 2029:
                    continue
                jt = _tagesbeginn_ueberlauf(b, 12 * grenze) + timedelta(days=1)  # erster Tag nach dem Jahr
                for z in (jt - timedelta(days=1), jt, jt + timedelta(days=1)):
                    soll_jahre = jahre_unabhaengig(b, z)
                    self.assertEqual(r.jahre_seit(b, z), soll_jahre, (b, z))
                    m = staffel(soll_jahre)
                    if m == 0:
                        soll = self._termin_622_abzaehlen(z, 0)
                    else:
                        fe = self._monatsfrist_abzaehlen(z, m)
                        soll = date(fe.year + (fe.month == 12), fe.month % 12 + 1, 1) - timedelta(days=1)
                    self.assertEqual(r.kuendigung_arbeit(z, None, False, beginn=b).datum, soll, (b, z))


if __name__ == "__main__":
    unittest.main()
