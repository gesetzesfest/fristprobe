"""Fristenrechner: reine Funktionen mit Rechenweg.

Jede Funktion gibt ein ``Ergebnis`` zurück: Datum, Normenliste und
Rechenweg (Liste von Sätzen, jeder beginnt mit der Regel-ID aus
recht/belege.json in eckigen Klammern). Strittige Konstellationen werden
mit ``strittig=True`` markiert und dürfen nicht als Sollwert dienen.

Konvention zum Feiertagsort: ``land`` ist das Land, in dem Behörde bzw.
Gericht sitzt. Der Benchmark legt Wohnort, Behörde und Gericht immer in
dasselbe Land (G-02 und G-03 sind strittig, G-01 und KS-04 nicht).

Feiertagstabelle (2020 bis 2030): Eine Rechnung bricht mit ValueError ab, wenn
Feiertage außerhalb der Spanne das Datum bestimmen könnten (Verschiebung,
Bekanntgabefiktion, Werktage im Zugangsmonat). Reine Hinweise im Rechenweg
(Wochentag oder Feiertag am Ereignistag, Kündigungstermin, Mietende) nennen
außerhalb der Spanne nur Samstag und Sonntag.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from .feiertage import LAENDER, fmt, in_spanne, ist_werktag, naechster_werktag, tagesart

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")

STICHTAG_VIER_TAGE = date(2025, 1, 1)  # A-01, A-08, A-09

# Strittige Regeln aus recht/belege.json (dürfen keinen Sollwert tragen)
STRITTIGE_REGELN = frozenset({"MI-05", "MI-08", "A-11", "B-03", "B-05", "G-02", "G-03"})


@dataclass
class Ergebnis:
    datum: date | None
    normen: list[str]
    rechenweg: list[str]
    roh_datum: date | None = None          # Fristende vor einer Verschiebung
    strittig: bool = False
    unsicher: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def als_dict(self) -> dict:
        def iso(v):
            if isinstance(v, date):
                return v.isoformat()
            if isinstance(v, dict):
                return {k: iso(x) for k, x in v.items()}
            if isinstance(v, (list, tuple)):
                return [iso(x) for x in v]
            return v
        return {
            "datum": iso(self.datum),
            "normen": list(self.normen),
            "rechenweg": list(self.rechenweg),
            "roh_datum": iso(self.roh_datum),
            "strittig": self.strittig,
            "unsicher": list(self.unsicher),
            "details": iso(self.details),
        }


# ---------------------------------------------------------------- Hilfen

def _eindeutig(xs) -> list[str]:
    out: list[str] = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def _letzter_tag(jahr: int, monat: int) -> int:
    return calendar.monthrange(jahr, monat)[1]


def monatsletzter(d: date) -> date:
    return date(d.year, d.month, _letzter_tag(d.year, d.month))


def plus_monate(d: date, n: int) -> tuple[date, bool]:
    """d plus n Monate mit gleicher Tageszahl; fehlt der Tag, letzter Tag des Monats.

    Rückgabe (Datum, gekappt), gekappt=True wenn § 188 Abs. 3 BGB griff.
    """
    m = d.month - 1 + n
    jahr, monat = d.year + m // 12, m % 12 + 1
    lt = _letzter_tag(jahr, monat)
    if d.day > lt:
        return date(jahr, monat, lt), True
    return date(jahr, monat, d.day), False


def _datum(x) -> date | None:
    if x is None or isinstance(x, date):
        return x
    return date.fromisoformat(str(x))


def _land(land: str) -> str:
    land = str(land).upper()
    if land not in LAENDER:
        raise ValueError(f"Unbekanntes Land {land!r}")
    return land


def _dauer(n: int, einheit: str, dativ: bool = True) -> str:
    """'einem Monat', 'drei Wochen' (Dativ) oder 'ein Monat', 'zwei Monate' (Nominativ)."""
    worte = {2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs", 7: "sieben", 9: "neun", 12: "zwölf"}
    einzahl = {"tage": "Tag", "wochen": "Woche", "monate": "Monat", "jahre": "Jahr"}[einheit]
    if dativ:
        mehrzahl = {"tage": "Tagen", "wochen": "Wochen", "monate": "Monaten", "jahre": "Jahren"}[einheit]
    else:
        mehrzahl = {"tage": "Tage", "wochen": "Wochen", "monate": "Monate", "jahre": "Jahre"}[einheit]
    if n == 1:
        if einheit == "wochen":
            return "einer Woche" if dativ else "eine Woche"
        return f"einem {einzahl}" if dativ else f"ein {einzahl}"
    return f"{worte.get(n, n)} {mehrzahl}"


def _jahre_text(n: int) -> str:
    return "1 volles Jahr" if n == 1 else f"{n} volle Jahre"


def _uebersprungen(von: date, bis: date, land: str, gemeinde=None) -> str:
    tage = []
    d = von
    while d < bis:
        tage.append(f"{fmt(d)} {tagesart(d, land, gemeinde)}")
        d += timedelta(days=1)
    return ", ".join(tage)


def _hinweis_art(d: date, land: str, gemeinde=None) -> str:
    """tagesart nur für Hinweise im Rechenweg: außerhalb der Feiertagstabelle nur Samstag/Sonntag."""
    if in_spanne(d):
        return tagesart(d, land, gemeinde)
    return {5: "Samstag", 6: "Sonntag"}.get(d.weekday(), "Werktag")


def _ende_tagesbeginn(anfang: date, monate: int) -> tuple[date, bool]:
    """Ende einer Frist ab Tagesbeginn (§ 187 Abs. 2, § 188 Abs. 2 Alt. 2 BGB) von ``monate`` Monaten.

    Ende mit Ablauf des Tages vor dem Tag, der dem Anfangstag in der Zahl entspricht; fehlt dieser
    Tag im Endmonat, Ende mit Ablauf des Monatsletzten (§ 188 Abs. 3 BGB). Rückgabe (Datum, gekappt).
    """
    ziel, gekappt = plus_monate(anfang, monate)
    return (ziel if gekappt else ziel - timedelta(days=1)), gekappt


# ------------------------------------------------- Regime der Fristberechnung

REGIME = {
    "BGB": {"beginn": ("FR-02", ["§ 187 Abs. 1 BGB"]),
            "verschiebung": ("FR-11", ["§ 193 BGB"])},
    "ZPO": {"beginn": ("FR-02", ["§ 222 Abs. 1 ZPO", "§ 187 Abs. 1 BGB"]),
            "verschiebung": ("KS-03", ["§ 222 Abs. 2 ZPO"])},
    "ArbGG": {"beginn": ("KS-02", ["§ 46 Abs. 2 ArbGG", "§ 222 Abs. 1 ZPO", "§ 187 Abs. 1 BGB"]),
              "verschiebung": ("KS-03", ["§ 222 Abs. 2 ZPO"])},
    "VwGO": {"beginn": ("F-01", ["§ 57 Abs. 2 VwGO", "§ 222 Abs. 1 ZPO", "§ 187 Abs. 1 BGB"]),
             "verschiebung": ("F-03", ["§ 57 Abs. 2 VwGO", "§ 222 Abs. 2 ZPO"])},
    "FGO": {"beginn": ("F-01", ["§ 54 Abs. 2 FGO", "§ 222 Abs. 1 ZPO", "§ 187 Abs. 1 BGB"]),
            "verschiebung": ("F-03", ["§ 54 Abs. 2 FGO", "§ 222 Abs. 2 ZPO"])},
    "SGG": {"beginn": ("F-01", ["§ 64 Abs. 1 SGG"]),
            "verschiebung": ("F-04", ["§ 64 Abs. 3 SGG"])},
    "AO": {"beginn": ("F-01", ["§ 108 Abs. 1 AO", "§ 187 Abs. 1 BGB"]),
           "verschiebung": ("F-05", ["§ 108 Abs. 3 AO"])},
    "VwVfG": {"beginn": ("F-01", ["§ 31 Abs. 1 VwVfG", "§ 187 Abs. 1 BGB"]),
              "verschiebung": ("F-06", ["§ 31 Abs. 3 VwVfG"])},
    "SGB X": {"beginn": ("F-01", ["§ 26 Abs. 1 SGB X", "§ 187 Abs. 1 BGB"]),
              "verschiebung": ("F-06", ["§ 26 Abs. 3 SGB X"])},
}

EINHEITEN = ("tage", "wochen", "monate", "jahre")


def frist_ende(beginn_ereignis: date, laenge: int, einheit: str, land: str, verschieben: bool,
               *, regime: str = "BGB", beginn_mitzaehlen: bool = False,
               regel_ohne_verschiebung: str = "FR-13", gemeinde=None) -> Ergebnis:
    """Fristende nach §§ 187, 188 (193) BGB bzw. § 222 ZPO und den Verweisnormen.

    beginn_ereignis: Ereignistag (Zugang, Zustellung, Bekanntgabe) bei
        § 187 Abs. 1, oder Anfangstag bei beginn_mitzaehlen=True (§ 187 Abs. 2).
    verschieben: Fristende auf den nächsten Werktag (kein Sa/So/Feiertag im
        Land) verschieben, wie § 193 BGB, § 222 Abs. 2 ZPO, § 64 Abs. 3 SGG,
        § 108 Abs. 3 AO, § 31 Abs. 3 VwVfG. Nicht für Kündigungsfristen (FR-13).
    """
    e = _datum(beginn_ereignis)
    land = _land(land)
    if einheit not in EINHEITEN:
        raise ValueError(f"einheit muss eine von {EINHEITEN} sein")
    if laenge < 1:
        raise ValueError("laenge muss mindestens 1 sein")
    if regime not in REGIME:
        raise ValueError(f"Unbekanntes Regime {regime!r}")
    r = REGIME[regime]
    weg: list[str] = []
    normen: list[str] = []
    unsicher: list[str] = []
    sgg = regime == "SGG"

    # Fristbeginn
    if beginn_mitzaehlen:
        anfang = e
        weg.append(f"[FR-03] Der Anfangstag {fmt(e)} zählt mit (§ 187 Abs. 2 BGB).")
        normen.append("§ 187 Abs. 2 BGB")
    else:
        anfang = e + timedelta(days=1)
        rid, bnormen = r["beginn"]
        weg.append(f"[{rid}] Der Ereignistag {fmt(e)} zählt nicht mit ({', '.join(bnormen)}); "
                   f"die Frist läuft ab {fmt(anfang)}, 0:00 Uhr.")
        normen += bnormen
        art = _hinweis_art(e, land, gemeinde)
        if art != "Werktag":
            weg.append(f"[FR-12] Dass der Ereignistag ein {art} ist, verschiebt den Fristbeginn nicht.")

    # rechnerisches Fristende
    ende_regel = "F-02" if sgg else "FR-05"
    if einheit == "tage":
        if beginn_mitzaehlen:
            ende = e + timedelta(days=laenge - 1)
        else:
            ende = e + timedelta(days=laenge)
        weg.append(f"[{'F-02' if sgg else 'FR-04'}] Tagesfrist von {laenge} Tagen: letzter Tag {fmt(ende)}.")
        normen.append("§ 64 Abs. 2 SGG" if sgg else "§ 188 Abs. 1 BGB")
    elif einheit == "wochen":
        if beginn_mitzaehlen:
            ende = e + timedelta(days=7 * laenge - 1)
            weg.append(f"[{ende_regel}] Frist von {_dauer(laenge, einheit)} ab Tagesbeginn: Ende am Vortag des "
                       f"entsprechenden Wochentags, {fmt(ende)}.")
        else:
            ende = e + timedelta(days=7 * laenge)
            weg.append(f"[{ende_regel}] Frist von {_dauer(laenge, einheit)}: Ende am gleichen Wochentag "
                       f"{_dauer(laenge, einheit)} später ({7 * laenge} Tage), {fmt(ende)}.")
        normen.append("§ 64 Abs. 2 SGG" if sgg else "§ 188 Abs. 2 BGB")
    else:
        monate = laenge if einheit == "monate" else 12 * laenge
        wort = _dauer(laenge, einheit)
        ziel, gekappt = plus_monate(e, monate)
        if beginn_mitzaehlen:
            ende, gekappt = _ende_tagesbeginn(e, monate)
            if gekappt:
                unsicher.append("Tagesbeginn-Frist mit fehlendem Anfangstag im Endmonat (§ 188 Abs. 3 BGB) "
                                "ist nicht belegt.")
            weg.append(f"[{ende_regel}] Frist von {wort} ab Tagesbeginn: Ende mit Ablauf des Tages vor dem "
                       f"entsprechenden Tag, {fmt(ende)}.")
        else:
            ende = ziel
            if gekappt:
                weg.append(f"[{ende_regel}] Frist von {wort}: maßgeblich wäre der {e.day}. "
                           f"{MONATE[ziel.month - 1]} {ziel.year}.")
            else:
                weg.append(f"[{ende_regel}] Frist von {wort}: Ende am Tag mit derselben Zahl, {fmt(ende)}.")
        normen.append("§ 64 Abs. 2 SGG" if sgg else "§ 188 Abs. 2 BGB")
        if gekappt:
            rid = "F-02" if sgg else "FR-06"
            weg.append(f"[{rid}] Diesen Tag gibt es im {MONATE[ziel.month - 1]} {ziel.year} nicht; die Frist "
                       f"endet mit Ablauf des letzten Tages dieses Monats, {fmt(ende)}"
                       f" ({'§ 64 Abs. 2 SGG' if sgg else '§ 188 Abs. 3 BGB'}).")
            if not sgg:
                normen.append("§ 188 Abs. 3 BGB")
            if einheit == "jahre":
                unsicher.append("Jahresfrist ab dem 29.02.: Anwendung von § 188 Abs. 3 BGB nicht gesondert belegt "
                                "(FR-06, F-02).")

    # Verschiebung
    roh = ende
    verschoben = False
    if verschieben:
        rid, vnormen = r["verschiebung"]
        if ist_werktag(ende, land, samstag_ist_werktag=False, gemeinde=gemeinde):
            weg.append(f"[{rid}] {fmt(ende)} ist in {LAENDER[land]} ein Werktag; keine Verschiebung.")
        else:
            neu = naechster_werktag(ende, land, samstag_ist_werktag=False, gemeinde=gemeinde)
            weg.append(f"[{rid}] Das rechnerische Fristende {fmt(ende)} ist ein {tagesart(ende, land, gemeinde)} "
                       f"(in {LAENDER[land]}); die Frist endet mit Ablauf des nächsten Werktags, {fmt(neu)} "
                       f"({', '.join(vnormen)}; übersprungen: {_uebersprungen(ende, neu, land, gemeinde)}).")
            normen += vnormen
            ende = neu
            verschoben = True
    else:
        art = _hinweis_art(ende, land, gemeinde)
        if art != "Werktag":
            weg.append(f"[{regel_ohne_verschiebung}] Das Fristende {fmt(ende)} ist ein {art}; "
                       f"es wird nicht auf den nächsten Werktag verschoben.")

    return Ergebnis(
        datum=ende, normen=_eindeutig(normen), rechenweg=weg, roh_datum=roh, unsicher=unsicher,
        details={"ereignis": e, "fristbeginn": anfang, "einheit": einheit, "laenge": laenge,
                 "land": land, "regime": regime, "verschoben": verschoben},
    )


# ------------------------------------------------------ Bekanntgabefiktion

VERFAHREN = {
    "VwVfG": {"norm": "§ 41 Abs. 2 S. 1 VwVfG", "regel": "A-03"},
    "SGB X": {"norm": "§ 37 Abs. 2 S. 1 SGB X", "regel": "A-05"},
    "AO": {"norm": "§ 122 Abs. 2 Nr. 1 AO", "regel": "A-06"},
}


def _verfahren(v: str) -> str:
    v2 = {"SGBX": "SGB X", "SGB10": "SGB X", "VWVFG": "VwVfG", "AO": "AO"}.get(str(v).replace(" ", "").upper())
    if v2 is None:
        raise ValueError(f"Unbekanntes Verfahren {v!r}; erlaubt: VwVfG, SGB X, AO")
    return v2


def bekanntgabe_fiktion(aufgabe_post: date, verfahren: str, land: str, *, fassung: str | None = None,
                        gemeinde=None) -> Ergebnis:
    """Fiktiver Bekanntgabetag eines einfachen Briefs (Inland).

    fassung: None = nach Aufgabedatum (ab 01.01.2025 vier Tage, davor drei),
             'ab2025' oder 'bis2024' erzwingt eine Fassung (nur für Fehlermodelle).
    Wochenende/Feiertag am Fiktionstag: AO verschiebt (B-01, B-02), SGB X nicht
    (B-04), VwVfG strittig (B-05) -> strittig=True, Datum ohne Verschiebung.
    """
    if aufgabe_post is None:
        raise ValueError("Der Tag der Aufgabe zur Post fehlt (A-10).")
    a = _datum(aufgabe_post)
    land = _land(land)
    v = _verfahren(verfahren)
    cfg = VERFAHREN[v]
    weg: list[str] = []
    unsicher: list[str] = []
    normen = [cfg["norm"]]
    strittig = False

    if fassung is None:
        fassung = "ab2025" if a >= STICHTAG_VIER_TAGE else "bis2024"
        if v == "AO":
            weg.append(f"[A-08] Aufgabe zur Post am {fmt(a)}: "
                       + ("nach dem 31.12.2024, also Vier-Tage-Fiktion (Art. 97 § 1 Abs. 15 EGAO)."
                          if fassung == "ab2025" else "bis 31.12.2024, also noch Drei-Tage-Fiktion."))
        else:
            weg.append(f"[A-09] Aufgabe zur Post am {fmt(a)}: "
                       + ("ab 01.01.2025, also Vier-Tage-Fiktion (PostModG)."
                          if fassung == "ab2025" else "bis 31.12.2024, also noch Drei-Tage-Fiktion."))
            if fassung == "bis2024":
                unsicher.append("Übergang VwVfG/SGB X ohne eigene Übergangsnorm (A-09, Arbeitsannahme).")
    elif fassung not in ("ab2025", "bis2024"):
        raise ValueError("fassung muss None, 'ab2025' oder 'bis2024' sein")

    n = 4 if fassung == "ab2025" else 3
    fiktion = a + timedelta(days=n)
    weg.append(f"[{cfg['regel']}] Ein einfacher Brief im Inland gilt am {'vierten' if n == 4 else 'dritten'} "
               f"Tag nach der Aufgabe zur Post als bekannt gegeben ({cfg['norm']}).")
    weg.append(f"[A-02] Gezählt werden Kalendertage, der Aufgabetag zählt nicht mit: "
               f"{fmt(a)} + {n} Tage = {fmt(fiktion)}.")

    bekanntgabe = fiktion
    art = tagesart(fiktion, land, gemeinde)
    if art != "Werktag":
        if v == "AO":
            bekanntgabe = naechster_werktag(fiktion, land, samstag_ist_werktag=False, gemeinde=gemeinde)
            weg.append(f"[B-01] Der Fiktionstag {fmt(fiktion)} ist ein {art}; nach § 108 Abs. 3 AO gilt der "
                       f"Bescheid erst am nächsten Werktag, {fmt(bekanntgabe)}, als bekannt gegeben.")
            weg.append("[B-02] Der Gesetzgeber lässt diese Verlängerung auch für die Vier-Tage-Fiktion gelten.")
            normen.append("§ 108 Abs. 3 AO")
            # Ein Samstag oder Sonntag verschiebt in jedem Land; die Ortsfrage (G-03) stellt sich nur bei
            # einem Landesfeiertag an einem Wochentag (auch wenn der Sonntag dort einen Feiertagsnamen trägt).
            if fiktion.weekday() < 5 and not _bundesweit(fiktion):
                unsicher.append("Landesfeiertag am Fiktionstag: maßgeblich ist nach Verwaltungsauffassung der Ort "
                                "des Empfängers (G-03); im Benchmark liegen Empfänger und Finanzamt im selben Land.")
        elif v == "SGB X":
            weg.append(f"[B-04] Der Fiktionstag {fmt(fiktion)} ist ein {art}; § 37 Abs. 2 SGB X regelt einen "
                       f"Zeitpunkt, keine Frist. Keine Verschiebung (BSG 06.05.2010 – B 14 AS 12/09 R).")
        else:
            strittig = True
            weg.append(f"[B-05] Der Fiktionstag {fmt(fiktion)} ist ein {art}; ob er sich verschiebt, ist im "
                       f"VwVfG strittig (überwiegend: keine Verschiebung).")
    return Ergebnis(datum=bekanntgabe, normen=_eindeutig(normen), rechenweg=weg, roh_datum=fiktion,
                    strittig=strittig, unsicher=unsicher,
                    details={"aufgabe_post": a, "fiktionstag": fiktion, "tage": n, "verfahren": v,
                             "land": land})


def _bundesweit(d: date) -> bool:
    """Ist d in allen 16 Ländern Feiertag?"""
    return all(tagesart(d, l) not in ("Werktag", "Samstag", "Sonntag") for l in LAENDER)


# --------------------------------------------------------- Rechtsbehelfe

RECHTSBEHELFE = {
    "widerspruch_vwvfg": {"name": "Widerspruch", "verfahren": "VwVfG", "regime": "VwGO",
                          "norm": "§ 70 Abs. 1 VwGO", "regel": "R-01", "bezug": "Bekanntgabe",
                          "rbb_norm": "§ 58 Abs. 2 VwGO", "rbb_regel": "E-01", "rbb_bezug": "Zustellung",
                          "ort": "Behörde"},
    "widerspruch_sgb2": {"name": "Widerspruch", "verfahren": "SGB X", "regime": "SGG",
                         "norm": "§ 84 Abs. 1 SGG", "regel": "R-03", "bezug": "Bekanntgabe",
                         "rbb_norm": "§ 66 Abs. 2 SGG", "rbb_regel": "E-02", "rbb_bezug": "Zustellung",
                         "ort": "Behörde"},
    "einspruch_ao": {"name": "Einspruch", "verfahren": "AO", "regime": "AO",
                     "norm": "§ 355 Abs. 1 AO", "regel": "R-05", "bezug": "Bekanntgabe",
                     "rbb_norm": "§ 356 Abs. 2 AO", "rbb_regel": "E-03", "rbb_bezug": "Bekanntgabe",
                     "ort": "Behörde"},
    "klage_vwgo": {"name": "Anfechtungsklage", "verfahren": "VwVfG", "regime": "VwGO",
                   "norm": "§ 74 Abs. 1 VwGO", "regel": "R-02", "bezug": "Zustellung",
                   "rbb_norm": "§ 58 Abs. 2 VwGO", "rbb_regel": "E-01", "rbb_bezug": "Zustellung",
                   "ort": "Gericht", "nur_zustellung": True},
    "klage_sgg": {"name": "Klage", "verfahren": "SGB X", "regime": "SGG",
                  "norm": "§ 87 Abs. 1 SGG", "regel": "R-04", "bezug": "Bekanntgabe",
                  "rbb_norm": "§ 66 Abs. 2 SGG", "rbb_regel": "E-02", "rbb_bezug": "Zustellung",
                  "ort": "Gericht", "zusatz_norm": "§ 87 Abs. 2 SGG"},
    "klage_fgo": {"name": "Klage", "verfahren": "AO", "regime": "FGO",
                  "norm": "§ 47 Abs. 1 FGO", "regel": "R-06", "bezug": "Bekanntgabe",
                  "rbb_norm": "§ 55 Abs. 2 FGO", "rbb_regel": "E-04", "rbb_bezug": "Bekanntgabe",
                  "ort": "Gericht"},
}
RECHTSBEHELFE["widerspruch_sgg"] = RECHTSBEHELFE["widerspruch_sgb2"]


def _rbb_ok(rbb) -> bool:
    if rbb in (True, "ja", "richtig", "ok"):
        return True
    if rbb in (False, "nein", "fehlt", "unrichtig", "falsch"):
        return False
    raise ValueError(f"rbb muss True/False oder 'ja'/'fehlt'/'unrichtig' sein, nicht {rbb!r}")


def rechtsbehelf(art: str, land: str, *, zustellart: str = "brief", aufgabe_post: date | None = None,
                 zustellung: date | None = None, rbb=True, fiktion_fassung: str | None = None,
                 gemeinde=None) -> Ergebnis:
    """Fristende eines Rechtsbehelfs gegen einen Bescheid.

    art: widerspruch_vwvfg | widerspruch_sgb2 | einspruch_ao | klage_vwgo | klage_sgg | klage_fgo
    zustellart: 'brief' (einfacher Brief, Bekanntgabefiktion, aufgabe_post nötig)
                'pzu' (Postzustellungsurkunde, zustellung nötig)
    rbb: Rechtsbehelfsbelehrung richtig (True) oder fehlt/unrichtig (False -> Jahresfrist)
    land: Sitz von Behörde bzw. Gericht (= Wohnort im Benchmark).
    """
    if art not in RECHTSBEHELFE:
        raise ValueError(f"Unbekannte Art {art!r}")
    cfg = RECHTSBEHELFE[art]
    land = _land(land)
    weg: list[str] = []
    normen: list[str] = []
    unsicher: list[str] = []
    strittig = False
    rbb_ok = _rbb_ok(rbb)

    if zustellart == "brief":
        if cfg.get("nur_zustellung"):
            raise ValueError("Der Widerspruchsbescheid ist zuzustellen (§ 73 Abs. 3 VwGO, C-05); "
                             "zustellart='pzu' verwenden.")
        if aufgabe_post is None:
            raise ValueError("Für zustellart='brief' ist aufgabe_post nötig (A-10).")
        bek_e = bekanntgabe_fiktion(aufgabe_post, cfg["verfahren"], land, fassung=fiktion_fassung,
                                    gemeinde=gemeinde)
        weg += bek_e.rechenweg
        normen += bek_e.normen
        unsicher += bek_e.unsicher
        strittig = strittig or bek_e.strittig
        bekanntgabe = bek_e.datum
        fiktionstag = bek_e.roh_datum
        if art == "klage_sgg":
            weg.insert(0, "[C-05] Der Widerspruchsbescheid wurde nicht förmlich zugestellt; es gilt die "
                          "Bekanntgabefiktion des § 37 SGB X (§ 85 Abs. 3 SGG).")
    elif zustellart == "pzu":
        if zustellung is None:
            raise ValueError("Für zustellart='pzu' ist zustellung nötig.")
        bekanntgabe = _datum(zustellung)
        fiktionstag = None
        if art == "klage_vwgo":
            weg.append("[C-05] Der Widerspruchsbescheid ist zuzustellen (§ 73 Abs. 3 VwGO).")
            normen.append("§ 73 Abs. 3 VwGO")
        elif art == "klage_sgg":
            weg.append("[C-05] Die Behörde hat den Widerspruchsbescheid förmlich zugestellt (§ 85 Abs. 3 SGG).")
            normen.append("§ 85 Abs. 3 SGG")
        else:
            weg.append("[C-04] Die Behörde hat die förmliche Zustellung gewählt; es gilt das VwZG.")
        weg.append(f"[C-01] Zustellung mit Postzustellungsurkunde am {fmt(bekanntgabe)}: keine "
                   f"Bekanntgabefiktion, maßgeblich ist der Tag laut Urkunde (§ 3 VwZG).")
        normen.append("§ 3 VwZG")
    else:
        raise ValueError("zustellart muss 'brief' oder 'pzu' sein")

    if rbb_ok:
        weg.append(f"[{cfg['regel']}] {cfg['name']} innerhalb eines Monats nach {cfg['bezug']} ({cfg['norm']}).")
        normen.append(cfg["norm"])
        if cfg.get("zusatz_norm"):
            normen.append(cfg["zusatz_norm"])
        laenge, einheit = 1, "monate"
    else:
        weg.append(f"[{cfg['rbb_regel']}] Die Rechtsbehelfsbelehrung fehlt oder ist unrichtig: der "
                   f"{cfg['name']} ist innerhalb eines Jahres seit {cfg['rbb_bezug']} zulässig ({cfg['rbb_norm']}).")
        normen.append(cfg["rbb_norm"])
        laenge, einheit = 1, "jahre"
        if cfg["rbb_bezug"] == "Zustellung" and zustellart == "brief":
            unsicher.append("Jahresfrist 'seit Zustellung' bei einfacher Bekanntgabe per Brief: Anknüpfung an "
                            "die Bekanntgabe ist nicht belegt (E-01, E-02).")

    fe = frist_ende(bekanntgabe, laenge, einheit, land, True, regime=cfg["regime"], gemeinde=gemeinde)
    weg += fe.rechenweg
    normen += fe.normen
    unsicher += fe.unsicher
    if not rbb_ok and fe.details["verschoben"]:
        unsicher.append("Verschiebung des Endes der Jahresfrist auf den nächsten Werktag ist in den Belegen "
                        "nicht eigens geprüft.")
    if cfg["ort"] == "Gericht":
        weg.append(f"[G-01] Maßgeblich sind die Feiertage am Sitz des Gerichts ({LAENDER[land]}).")
    else:
        weg.append(f"[{REGIME[cfg['regime']]['verschiebung'][0]}] Feiertage nach dem Recht von "
                   f"{LAENDER[land]} (Behördensitz und Wohnort im selben Land).")

    return Ergebnis(
        datum=fe.datum, normen=_eindeutig(normen), rechenweg=weg, roh_datum=fe.roh_datum,
        strittig=strittig, unsicher=_eindeutig(unsicher),
        details={"art": art, "land": land, "zustellart": zustellart, "bekanntgabe": bekanntgabe,
                 "fiktionstag": fiktionstag, "fristbeginn": fe.details["fristbeginn"],
                 "rbb": rbb_ok, "verschoben": fe.details["verschoben"]},
    )


# ------------------------------------------------------------- KSchG-Klage

def kschg_klage(zugang: date, land: str, gemeinde=None) -> Ergebnis:
    """Klagefrist nach § 4 Satz 1 KSchG: drei Wochen ab Zugang, Ende ggf. nach § 222 Abs. 2 ZPO verschoben.

    land: Sitz des Arbeitsgerichts (KS-04).
    """
    if zugang is None:
        raise ValueError("Der Zugangstag der Kündigung fehlt (KS-01).")
    z = _datum(zugang)
    land = _land(land)
    weg = ["[KS-01] Klage innerhalb von drei Wochen nach Zugang der schriftlichen Kündigung "
           "(§ 4 Satz 1 KSchG)."]
    fe = frist_ende(z, 3, "wochen", land, True, regime="ArbGG", gemeinde=gemeinde)
    weg += fe.rechenweg
    weg.append(f"[KS-04] Maßgeblich sind die Feiertage am Sitz des Arbeitsgerichts ({LAENDER[land]}).")
    weg.append("[KS-05] Fristwahrend ist der Eingang der Klage beim Arbeitsgericht, nicht die Absendung.")
    return Ergebnis(datum=fe.datum, normen=_eindeutig(["§ 4 Satz 1 KSchG"] + fe.normen), rechenweg=weg,
                    roh_datum=fe.roh_datum, unsicher=fe.unsicher,
                    details={"zugang": z, "land": land, "fristbeginn": fe.details["fristbeginn"],
                             "verschoben": fe.details["verschoben"]})


# ----------------------------------------------------------- Mietkündigung

def werktage_im_monat(jahr: int, monat: int, land: str, anzahl: int = 3, samstag_ist_werktag: bool = True,
                      gemeinde=None) -> list[date]:
    out = []
    d = date(jahr, monat, 1)
    while len(out) < anzahl:
        if ist_werktag(d, land, samstag_ist_werktag=samstag_ist_werktag, gemeinde=gemeinde):
            out.append(d)
        d += timedelta(days=1)
    return out


def jahre_seit(beginn: date, stichtag: date) -> int:
    """Volle Jahre seit beginn (Starttag zählt mit), Stand Ablauf des Vortags von stichtag.

    n Jahre sind voll, wenn ihr Ende vor dem Stichtag liegt: Ablauf des Tages vor dem Jahrestag
    (§ 187 Abs. 2, § 188 Abs. 2 Alt. 2 BGB); fehlt der Jahrestag (Beginn 29.02.), Ablauf des
    28.02. (§ 188 Abs. 3 BGB, wie beim Lebensalter). Gleiche Rechnung wie frist_ende mit
    beginn_mitzaehlen=True.
    """
    n = 0
    while _ende_tagesbeginn(beginn, 12 * (n + 1))[0] < stichtag:
        n += 1
    return n


def _grenzfall_29_februar(beginn: date, stichtag: date) -> bool:
    """Beginn am 29.02., Stichtag am 28.02. eines Gemeinjahrs: das Jahr endet erst mit Ablauf dieses Tages.

    Die Anwendung von § 188 Abs. 3 BGB auf Jahresfristen ist nicht gesondert belegt (FR-06).
    """
    return (beginn.month, beginn.day) == (2, 29) and (stichtag.month, stichtag.day) == (2, 28) \
        and not calendar.isleap(stichtag.year) and stichtag > beginn


def kuendigung_miete(zugang: date, land: str, *, partei: str = "mieter", ueberlassung: date | None = None,
                     samstag_ist_werktag: bool = True, gemeinde=None) -> Ergebnis:
    """Ende eines Wohnraummietverhältnisses nach § 573c Abs. 1 BGB.

    partei: 'mieter' (immer drei Monate) oder 'vermieter' (Staffel nach Überlassung, MI-07).
    samstag_ist_werktag: nur für Fehlermodelle auf False setzen (MI-04 sagt True).
    Datum im Ergebnis: letzter Tag des Mietverhältnisses (Ablauf).
    """
    if zugang is None:
        raise ValueError("Der Zugangstag der Kündigung fehlt (MI-02).")
    z = _datum(zugang)
    land = _land(land)
    weg: list[str] = []
    normen = ["§ 573c Abs. 1 Satz 1 BGB", "§ 130 Abs. 1 Satz 1 BGB"]
    unsicher: list[str] = []
    strittig = False

    weg.append(f"[MI-02] Maßgeblich ist der Zugang der Kündigung am {fmt(z)}, nicht das Datum des Schreibens.")
    w = werktage_im_monat(z.year, z.month, land, 3, samstag_ist_werktag, gemeinde)
    w3 = w[2]
    lueckentage = []
    d = date(z.year, z.month, 1)
    while d < w3:
        if d not in w:
            lueckentage.append(f"{fmt(d)} {tagesart(d, land, gemeinde)}")
        d += timedelta(days=1)
    weg.append(f"[MI-03] Werktage im {MONATE[z.month - 1]} {z.year} in {LAENDER[land]}: "
               f"1. {fmt(w[0])}, 2. {fmt(w[1])}, 3. {fmt(w3)}"
               + (f" (nicht gezählt: {', '.join(lueckentage)})." if lueckentage else "."))
    if samstag_ist_werktag and any(x.weekday() == 5 for x in w[:2]):
        weg.append("[MI-04] Ein Samstag unter den ersten beiden Werktagen zählt als Werktag mit.")

    rechtzeitig = z <= w3
    if w3.weekday() == 5 and samstag_ist_werktag:
        verlaengert = naechster_werktag(w3 + timedelta(days=1), land, samstag_ist_werktag=False, gemeinde=gemeinde)
        if w3 < z <= verlaengert:
            strittig = True
            weg.append(f"[MI-05] Der dritte Werktag ist Samstag {fmt(w3)}; ob die Karenzzeit bis {fmt(verlaengert)} "
                       f"verlängert wird, ist strittig. Hier ohne Verlängerung gerechnet.")

    if partei == "mieter":
        frist_monate = 3
        weg.append("[MI-01] Mieterkündigung: spätestens am dritten Werktag eines Monats zum Ablauf des "
                   "übernächsten Monats (drei Monate).")
    elif partei == "vermieter":
        if ueberlassung is None:
            raise ValueError("Für die Vermieterkündigung ist das Überlassungsdatum nötig (MI-07, MI-08).")
        u = _datum(ueberlassung)
        jahre = jahre_seit(u, z)

        def _staffel(j):
            return 9 if j >= 8 else 6 if j >= 5 else 3
        frist_monate = _staffel(jahre)
        if _grenzfall_29_februar(u, z) and _staffel(jahre + 1) != frist_monate:
            unsicher.append("Überlassung am 29.02., Zugang am 28.02.: Ende des Jahres nach § 188 Abs. 3 BGB "
                            "nicht gesondert belegt (FR-06, MI-07).")
        weg.append(f"[MI-07] Vermieterkündigung: Überlassung am {fmt(u)}, bei Zugang {_jahre_text(jahre)}; "
                   f"Kündigungsfrist {frist_monate} Monate (§ 573c Abs. 1 Satz 2 BGB).")
        normen.append("§ 573c Abs. 1 Satz 2 BGB")
        for grenze in (5, 8):
            jt = plus_monate(u, 12 * grenze)[0]
            if jt.year == z.year and jt.month == z.month:
                unsicher.append(f"Jahrestag {grenze} Jahre ({jt.isoformat()}) im Zugangsmonat: Stichtag nicht "
                                f"belegt (MI-07).")
    else:
        raise ValueError("partei muss 'mieter' oder 'vermieter' sein")

    extra = frist_monate - 1 if rechtzeitig else frist_monate
    ende = monatsletzter(plus_monate(date(z.year, z.month, 1), extra)[0])
    if rechtzeitig:
        weg.append(f"[MI-01] Zugang {fmt(z)} am oder vor dem dritten Werktag {fmt(w3)}: das Mietverhältnis "
                   f"endet mit Ablauf des {fmt(ende)}.")
    else:
        weg.append(f"[MI-01] Zugang {fmt(z)} nach dem dritten Werktag {fmt(w3)}: der {MONATE[z.month - 1]} zählt "
                   f"nicht mehr mit; das Mietverhältnis endet mit Ablauf des {fmt(ende)}.")
    art = _hinweis_art(ende, land, gemeinde)
    if art != "Werktag":
        weg.append(f"[FR-13] Das Mietende {fmt(ende)} ist ein {art}; § 193 BGB gilt für Kündigungsfristen "
                   f"nicht, keine Verschiebung.")
    return Ergebnis(datum=ende, normen=_eindeutig(normen), rechenweg=weg, roh_datum=ende, strittig=strittig,
                    unsicher=unsicher,
                    details={"zugang": z, "land": land, "partei": partei, "werktage": w, "dritter_werktag": w3,
                             "rechtzeitig": rechtzeitig, "frist_monate": frist_monate})


def spaetester_zugang_miete(mietende: date, land: str, *, partei: str = "mieter",
                            ueberlassung: date | None = None, gemeinde=None) -> Ergebnis:
    """Letzter Tag, an dem die Kündigung zugehen muss, damit das Mietverhältnis zu ``mietende`` endet."""
    m = _datum(mietende)
    land = _land(land)
    if m != monatsletzter(m):
        raise ValueError("mietende muss ein Monatsletzter sein (§ 573c Abs. 1 BGB)")
    kandidaten = (3,) if partei == "mieter" else (3, 6, 9)
    treffer = []
    for k in kandidaten:
        start = plus_monate(date(m.year, m.month, 1), -(k - 1))[0]
        w3 = werktage_im_monat(start.year, start.month, land, 3, True, gemeinde)[2]
        # spätester Tag bis einschließlich zum dritten Werktag; bei einem Staffelwechsel im Monat
        # (Jahrestag der Überlassung) kann das ein Tag vor dem dritten Werktag sein
        d = w3
        while d.month == start.month:
            e = kuendigung_miete(d, land, partei=partei, ueberlassung=ueberlassung, gemeinde=gemeinde)
            if e.datum == m:
                treffer.append((d, w3, start, k, e))
                break
            d -= timedelta(days=1)
    if not treffer:
        raise ValueError("Kein Zugangstag führt zu diesem Mietende.")
    d, w3, start, k, e = max(treffer, key=lambda t: t[0])
    if d == w3:
        weg = [f"[MI-01] Für ein Mietende mit Ablauf des {fmt(m)} muss die Kündigung spätestens am dritten "
               f"Werktag des Monats {MONATE[start.month - 1]} {start.year} zugehen."]
    else:
        weg = [f"[MI-07] Für ein Mietende mit Ablauf des {fmt(m)} muss die Kündigung spätestens am {fmt(d)} "
               f"zugehen; ab dem Folgetag gilt wegen der längeren Überlassungsdauer die nächste Stufe."]
    weg += e.rechenweg
    unsicher = list(e.unsicher)
    if d != w3 and not unsicher:
        unsicher.append("Staffelwechsel im Zugangsmonat: Stichtag nicht belegt (MI-07).")
    return Ergebnis(datum=d, normen=e.normen, rechenweg=weg, roh_datum=d,
                    strittig=e.strittig or (d == w3 and w3.weekday() == 5),
                    unsicher=unsicher, details={"mietende": m, "land": land, "frist_monate": k,
                                                "dritter_werktag": w3})


# --------------------------------------------------------- Arbeitskündigung

STAFFEL_622 = ((20, 7), (15, 6), (12, 5), (10, 4), (8, 3), (5, 2), (2, 1))


def frist_monate_622(jahre: int) -> int:
    for grenze, monate in STAFFEL_622:
        if jahre >= grenze:
            return monate
    return 0


def kuendigung_arbeit(zugang: date, betriebszugehoerigkeit_jahre: int | None, probezeit: bool, *,
                      partei: str = "arbeitgeber", beginn: date | None = None, probezeit_monate: int = 6,
                      gemeinde=None, land: str | None = None) -> Ergebnis:
    """Frühester Beendigungstermin einer ordentlichen Kündigung nach § 622 BGB (gesetzliche Fristen).

    partei: 'arbeitgeber' oder 'arbeitnehmer'.
    betriebszugehoerigkeit_jahre: volle Jahre bei Zugang (AR-02); None -> aus ``beginn`` berechnet.
    probezeit: Kündigung in einer vereinbarten Probezeit (§ 622 Abs. 3). Mit ``beginn`` wird geprüft,
        ob der Zugang noch in der Probezeit liegt (AR-06; höchstens sechs Monate, AR-05).
    land: nur für die Wochentags-/Feiertagsangabe im Rechenweg (keine Verschiebung, FR-14).
    """
    if zugang is None:
        raise ValueError("Der Zugangstag der Kündigung fehlt (AR-02).")
    z = _datum(zugang)
    b = _datum(beginn)
    land = _land(land) if land else None
    weg: list[str] = []
    normen: list[str] = []
    details: dict = {"zugang": z, "partei": partei}
    if partei not in ("arbeitgeber", "arbeitnehmer"):
        raise ValueError("partei muss 'arbeitgeber' oder 'arbeitnehmer' sein")

    unsicher: list[str] = []
    in_probezeit = bool(probezeit)
    if in_probezeit and b is not None:
        pm = min(probezeit_monate, 6)
        pz_ende, gekappt = _ende_tagesbeginn(b, pm)
        details["probezeit_ende"] = pz_ende
        weg.append(f"[AR-06] Probezeit ab {fmt(b)} ({pm} Monate, erster Tag zählt mit) endet mit Ablauf des "
                   f"{fmt(pz_ende)} (§ 187 Abs. 2, § 188 Abs. 2 BGB).")
        normen += ["§ 187 Abs. 2 BGB"]
        if gekappt:
            weg.append(f"[FR-06] Den {b.day}. gibt es im {MONATE[pz_ende.month - 1]} {pz_ende.year} nicht; die "
                       f"Probezeit endet mit Ablauf des Monatsletzten {fmt(pz_ende)} (§ 188 Abs. 3 BGB).")
            normen.append("§ 188 Abs. 3 BGB")
            unsicher.append("Tagesbeginn-Frist mit fehlendem Anfangstag im Endmonat (§ 188 Abs. 3 BGB) "
                            "ist nicht belegt.")
        if z > pz_ende:
            in_probezeit = False
            weg.append(f"[AR-06] Die Kündigung ging erst am {fmt(z)} zu, also nach der Probezeit; die kurze "
                       f"Frist gilt nicht.")

    def _wt(d):
        art = _hinweis_art(d, land, gemeinde) if land else "Werktag"
        return f" ({art})" if art != "Werktag" else ""

    if in_probezeit:
        ende = z + timedelta(days=14)
        weg.append(f"[AR-05] Kündigung in der Probezeit: zwei Wochen ohne Kündigungstermin; Zugang {fmt(z)} "
                   f"+ 14 Tage = {fmt(ende)}{_wt(ende)} (§ 622 Abs. 3 BGB).")
        normen = ["§ 622 Abs. 3 BGB", "§ 187 Abs. 1 BGB", "§ 188 Abs. 2 BGB"] + normen
        details.update(fristende=ende, termin=ende, frist="2 Wochen")
        termin = ende
    else:
        jahre = betriebszugehoerigkeit_jahre
        if jahre is None:
            if b is None:
                raise ValueError("betriebszugehoerigkeit_jahre oder beginn nötig")
            jahre = jahre_seit(b, z)
            weg.append(f"[AR-02] Beschäftigt seit {fmt(b)}: bei Zugang {_jahre_text(jahre)}.")
            if (_grenzfall_29_februar(b, z) and partei == "arbeitgeber"
                    and frist_monate_622(jahre + 1) != frist_monate_622(jahre)):
                unsicher.append("Beginn am 29.02., Zugang am 28.02.: Ende des Beschäftigungsjahres nach § 188 "
                                "Abs. 3 BGB nicht gesondert belegt (FR-06, AR-02).")
        details["jahre"] = jahre
        m = frist_monate_622(jahre) if partei == "arbeitgeber" else 0
        if m == 0:
            fristende = z + timedelta(days=28)
            termin = date(fristende.year, fristende.month, 15)
            if termin < fristende:
                termin = monatsletzter(fristende)
            wer = ("Arbeitnehmerkündigung" if partei == "arbeitnehmer"
                   else f"Arbeitgeberkündigung, Beschäftigung bei Zugang {_jahre_text(jahre)} (unter zwei Jahren)")
            weg.append(f"[AR-01] {wer}: vier Wochen zum 15. oder zum Monatsende (§ 622 Abs. 1 BGB).")
            weg.append(f"[AR-01] Zugang {fmt(z)} + 28 Tage = {fmt(fristende)}; erster Termin am oder danach: "
                       f"{fmt(termin)}.")
            weg.append("[FR-10] Ende des Monats ist der letzte Tag des Monats (§ 192 BGB).")
            normen = ["§ 622 Abs. 1 BGB", "§ 187 Abs. 1 BGB", "§ 188 Abs. 2 BGB", "§ 192 BGB"] + normen
            details.update(fristende=fristende, termin=termin, frist="4 Wochen")
        else:
            fristende, gekappt = plus_monate(z, m)
            termin = monatsletzter(fristende)
            weg.append(f"[AR-02] Arbeitgeberkündigung, Beschäftigung bei Zugang {_jahre_text(jahre)}: {_dauer(m, 'monate', dativ=False)} zum Ende eines "
                       f"Kalendermonats (§ 622 Abs. 2 BGB).")
            weg.append("[AR-03] Beschäftigungszeiten vor dem 25. Lebensjahr zählen mit (Satz 2 a. F. aufgehoben).")
            normen = ["§ 622 Abs. 2 BGB", "§ 187 Abs. 1 BGB", "§ 188 Abs. 2 BGB"] + normen
            if gekappt:
                weg.append(f"[FR-06] Den {z.day}. gibt es im {MONATE[fristende.month - 1]} {fristende.year} nicht; "
                           f"das Fristende ist der Monatsletzte {fmt(fristende)} (§ 188 Abs. 3 BGB).")
                normen.append("§ 188 Abs. 3 BGB")
            weg.append(f"[AR-04] Zugang {fmt(z)} plus {_dauer(m, 'monate')} = {fmt(fristende)}; Termin ist der nächste "
                       f"Monatsletzte: {fmt(termin)}.")
            normen.append("§ 192 BGB")
            details.update(fristende=fristende, termin=termin, frist=f"{m} Monate")
    if land and _hinweis_art(termin, land, gemeinde) != "Werktag":
        weg.append(f"[FR-14] Der Termin {fmt(termin)} ist ein {_hinweis_art(termin, land, gemeinde)}; keine "
                   f"Verschiebung nach § 193 BGB.")
    return Ergebnis(datum=termin, normen=_eindeutig(normen), rechenweg=weg, roh_datum=termin, unsicher=unsicher,
                    details=details)


# ---------------------------------------------------------------- Verteiler

FUNKTIONEN = {
    "frist_ende": frist_ende,
    "bekanntgabe_fiktion": bekanntgabe_fiktion,
    "rechtsbehelf": rechtsbehelf,
    "kschg_klage": kschg_klage,
    "kuendigung_miete": kuendigung_miete,
    "spaetester_zugang_miete": spaetester_zugang_miete,
    "kuendigung_arbeit": kuendigung_arbeit,
}

_DATUMSFELDER = {"beginn_ereignis", "aufgabe_post", "zustellung", "zugang", "ueberlassung", "beginn", "mietende"}


def berechne(funktion: str, argumente: dict) -> Ergebnis:
    """Aufruf aus JSON-Parametern (Daten als ISO-Text)."""
    if funktion not in FUNKTIONEN:
        raise ValueError(f"Unbekannte Funktion {funktion!r}")
    args = {k: (_datum(v) if k in _DATUMSFELDER else v) for k, v in argumente.items()}
    return FUNKTIONEN[funktion](**args)
