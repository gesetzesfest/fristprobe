"""Probe mit erfundenen Briefen in fremdem Stil (nicht aus generator.py): Wie gut verallgemeinert die Kette?

Sollwerte nur per Code: von Hand gesetzte Felder -> kette.normalisiere -> kette.rechne. Alle Personen, Orte,
Behörden und Aktenzeichen sind erfunden.

  python3 benchmark/fristen/fremd_probe.py [modell] [host]

Stand 16.10.2026, qwen3:8b: 4/4 (vor Regel P 3/4: D Mieterin als Vermieterin gelesen).
"""
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(WURZEL), str(WURZEL / "benchmark" / "fristen")]
import kette as K  # noqa: E402
import pruefe as PR  # noqa: E402

BRIEFE = [
 ("A_familienkasse", "berechnen", "Bis zu welchem Tag (einschließlich) kann spätestens Einspruch eingelegt werden?",
  """FAMILIENKASSE BAYERN-MITTE
Kindergeldstelle · Postfach 4410 · 85049 Ingolfing

Frau
Mira Oberholzer
Am Kalkofen 7a
85101 Lenting-Süd

Kindergeldnummer 215FK448817 — bitte stets angeben

Bescheid über die Aufhebung der Festsetzung von Kindergeld

die Festsetzung des Kindergeldes für Ihr Kind Jonas wird ab Januar 2026 aufgehoben, weil die Ausbildung beendet ist.
Überzahlt sind 518,00 Euro. Die Zahlungsaufforderung folgt gesondert.

Rechtsbehelfsbelehrung: Gegen diesen Bescheid ist der Einspruch zulässig. Er ist bei der oben genannten Familienkasse
schriftlich oder elektronisch einzureichen oder dort zur Niederschrift zu erklären. Die Frist für die Einlegung des
Einspruchs beträgt einen Monat. Sie beginnt mit Ablauf des Tages, an dem Ihnen dieser Bescheid bekannt gegeben worden ist.

Mit freundlichen Grüßen — Ihre Familienkasse
Ingolfing, den zweiten März zweitausendsechsundzwanzig
-----------------------------------------------------
Interner Versandhinweis (Fußzeile): Abgesandt am Dienstag, 3. März 2026, als gewöhnlicher Brief im Inland.""",
  dict(schreiben="bescheid", verfahren="AO", bundesland="Bayern", art="einspruch_ao", datum_schreiben="2026-03-02",
       zustellart="einfacher_brief", datum_aufgabe_post="2026-03-03", rechtsbehelfsbelehrung="vorhanden")),
 ("B_kuendigung_uebergabe", "berechnen",
  "Die gekündigte Person will Kündigungsschutzklage erheben. Bis zu welchem Tag (einschließlich) muss die Klage spätestens beim Arbeitsgericht eingehen?",
  """Brauhaus Wetterauer Löwe GmbH & Co. KG · Personalabteilung · Lindenstraße 3 · 61169 Friedbergen (Hessen)

Herrn Tomasz Wieczorek, persönlich/vertraulich

Friedbergen, 12.02.2026

Kündigung Ihres Arbeitsverhältnisses

Sehr geehrter Herr Wieczorek,
wir kündigen das mit Ihnen bestehende Arbeitsverhältnis ordentlich und fristgerecht zum nächstmöglichen Zeitpunkt.
Der Betriebsrat wurde angehört.
gez. Annegret Faulhaber, Geschäftsführerin

>>> Empfangsbestätigung: Original heute im Büro der Personalabteilung persönlich erhalten.
Datum der Übergabe: Freitag, 13.02.2026 — Unterschrift T. Wieczorek""",
  dict(schreiben="kuendigung_arbeitsverhaeltnis", bundesland="Hessen", art="kschg_klage", datum_schreiben="2026-02-12",
       zustellart="persoenliche_uebergabe", datum_zugang="2026-02-13", kuendigende_partei="arbeitgeber")),
 ("C_widerspruchsbescheid_pzu", "berechnen",
  "Bis zu welchem Tag (einschließlich) muss die Klage spätestens beim Sozialgericht eingegangen sein?",
  """Deutsche Rentenversicherung Westfalen-Nordmark · Widerspruchsstelle · 48xxx Hammwerden (Nordrhein-Westfalen)
Aktenzeichen 64 120575 W 077 · Datum 22.05.2026

W I D E R S P R U C H S B E S C H E I D
Der Widerspruch vom 03.02.2026 gegen den Bescheid vom 14.01.2026 wird zurückgewiesen. Kosten sind nicht zu erstatten.

Rechtsbehelfsbelehrung
Gegen diesen Widerspruchsbescheid kann innerhalb eines Monats nach seiner Bekanntgabe Klage beim Sozialgericht
Hammwerden erhoben werden.

[Stempel auf der Rückseite der Zustellungsurkunde, Kopie:]
Zugestellt durch Einlegen in den Briefkasten am 27.05.2026 — Postzustellungsurkunde Nr. 7731-0042""",
  dict(schreiben="widerspruchsbescheid", verfahren="SGB X", bundesland="Nordrhein-Westfalen", art="klage_sgg",
       datum_schreiben="2026-05-22", zustellart="zustellungsurkunde", datum_zustellung="2026-05-27",
       rechtsbehelfsbelehrung="vorhanden")),
 ("D_mieter_ostern", "berechnen", "Mit Ablauf welches Tages endet das Mietverhältnis durch diese Kündigung?",
  """Liebe Frau Kessler-Ohm,

hiermit kündige ich, Paulina Brandvogt, meine Wohnung in der Eichendorffstraße 19 (2. OG links) in 39104 Elbstadt
(Sachsen-Anhalt) fristgerecht. Normaler Wohnraum, im Vertrag steht nichts Besonderes zur Kündigung.
Ich bin seit 2021 Mieterin.

Viele Grüße
Paulina Brandvogt (handschriftlich unterschrieben), geschrieben am 31.03.2026

---- Eingangsstempel der Vermieterin: EINGEGANGEN 02. APR. 2026 ----""",
  dict(schreiben="kuendigung_mietverhaeltnis", bundesland="Sachsen-Anhalt", art="kuendigung_miete",
       datum_schreiben="2026-03-31", datum_zugang="2026-04-02", kuendigende_partei="mieter", ueberlassung="2021-01-01")),
]

modell = sys.argv[1] if len(sys.argv) > 1 else "qwen3:8b"
host = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:11434"
treffer = 0
for name, typ, frage, text, felder in BRIEFE:
    felder, _h = K.normalisiere(felder)
    soll = (K.rechne(felder, typ, frage).get("antwort") or {})
    teil = PR.pruefe(text, frage, typ, modell, host)
    ist = teil.get("antwort_json") or {}
    ok = (ist.get("antwortart"), ist.get("fristende")) == (soll.get("antwortart"), soll.get("fristende"))
    treffer += ok
    abw = {k: (felder.get(k), (teil.get("felder") or {}).get(k)) for k in set(felder) | set(teil.get("felder") or {})
           if (teil.get("felder") or {}).get(k) != felder.get(k) and (felder.get(k) or (teil.get("felder") or {}).get(k))}
    print(f"{name}: soll {soll.get('antwortart')} {soll.get('fristende')} | ist {ist.get('antwortart')} {ist.get('fristende')}"
          f" | {'OK' if ok else 'FALSCH'} | Sicherheit {ist.get('sicherheit')} | Nachfrage {teil.get('nachgefragt')}")
    if abw:
        print("   Felder abweichend (soll, ist):", json.dumps(abw, ensure_ascii=False))
print(f"{treffer}/{len(BRIEFE)} exakt")
