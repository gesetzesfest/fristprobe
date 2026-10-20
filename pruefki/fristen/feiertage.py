"""Gesetzliche Feiertage je Bundesland, 2020 bis 2030.

Nur Standardbibliothek. Ostern nach dem gregorianischen Algorithmus
(Meeus/Jones/Butcher), alle beweglichen Feiertage davon abgeleitet.

Quelle: die Feiertagsgesetze der Länder (z. B. FTG BW § 1, BayFTG Art. 1,
SächsSFG § 1, ThürFGtG § 2, FTG NW § 2, NFeiertagsG § 2, HFeiertagsG § 1,
FTG BB § 2). Die Tabelle ist aus Fachwissen gebaut und nur in Einzelpunkten
gegen die Landesgesetze geprüft (Berlin GVBl. 2024 S. 460, HFeiertagsG § 1,
ThürFGtG § 2; Stand 14.10.2026, über umwelt-online.de, nicht amtlich). Die
Feiertags-Recherche in recht/belege.json ist leer. Offene Punkte stehen in
benchmark/fristen/offen.md.

Teil-Feiertage, die nur in einzelnen Gemeinden gelten, kommen nur mit der
Option ``gemeinde`` dazu:
  * ``mariae_himmelfahrt``  BY (Gemeinden mit überwiegend katholischer Bevölkerung)
  * ``fronleichnam``        SN (einzelne Gemeinden im sorbischen Siedlungsgebiet),
                            TH (einzelne Gemeinden, v. a. Eichsfeld)
  * ``friedensfest``        BY (nur Stadt Augsburg, 08.08.)
``gemeinde=True`` nimmt alle Teil-Feiertage des Landes dazu.

Einmalige Feiertage in Berlin: 08.05.2020 (75. Jahrestag Kriegsende),
08.05.2025 (80. Jahrestag) und 17.06.2028 (75. Jahrestag des Aufstandes vom
17. Juni 1953; Viertes Gesetz zur Änderung des Gesetzes über die Sonn- und
Feiertage vom 10.07.2024, GVBl. S. 460, Art. 1 und 3). Der 17.06.2028 ist ein
Samstag: für Fristenden ohne Wirkung, für die Werktagszählung nach § 573c BGB
zählt er nicht als Werktag.

Sonntage: In Hessen sind alle Sonntage gesetzliche Feiertage (§ 1 Abs. 1
HFeiertagsG), Brandenburg nennt Oster- und Pfingstsonntag ausdrücklich (§ 2
Abs. 1 FTG BB). Die Tabelle führt nur die ausdrücklich genannten Tage (BB);
auf Werktage und Fristenden wirkt das nicht, weil Sonntage nie Werktage sind.

Werktag (für §§ 193 BGB, 222 ZPO, 31 VwVfG, 108 AO, 64 SGG): weder
Samstag noch Sonntag noch Feiertag, also ``samstag_ist_werktag=False``.
Werktag im Sinn von § 573c BGB (BGH VIII ZR 206/04, MI-04): Samstag zählt
mit, also ``samstag_ist_werktag=True`` (Voreinstellung).
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

LAENDER: dict[str, str] = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}

ERSTES_JAHR = 2020
LETZTES_JAHR = 2030

WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
WOCHENTAGE_LANG = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

# Teil-Feiertage: Schlüssel -> Länder, in denen sie in einzelnen Gemeinden gelten
TEIL_FEIERTAGE: dict[str, tuple[str, ...]] = {
    "mariae_himmelfahrt": ("BY",),
    "fronleichnam": ("SN", "TH"),
    "friedensfest": ("BY",),
}


def ostersonntag(jahr: int) -> date:
    """Ostersonntag nach dem anonymen gregorianischen Algorithmus."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


def buss_und_bettag(jahr: int) -> date:
    """Mittwoch vor dem 23. November (also zwischen 16. und 22. November)."""
    d = date(jahr, 11, 22)
    return d - timedelta(days=(d.weekday() - 2) % 7)


def _pruefe(jahr: int, land: str) -> str:
    land = land.upper()
    if land not in LAENDER:
        raise ValueError(f"Unbekanntes Land {land!r}; erlaubt: {', '.join(LAENDER)}")
    if not ERSTES_JAHR <= jahr <= LETZTES_JAHR:
        raise ValueError(f"Jahr {jahr} außerhalb der geprüften Spanne {ERSTES_JAHR} bis {LETZTES_JAHR}")
    return land


def _gemeinde_schluessel(land: str, gemeinde) -> set[str]:
    if not gemeinde:
        return set()
    if gemeinde is True:
        return {k for k, laender in TEIL_FEIERTAGE.items() if land in laender}
    if isinstance(gemeinde, str):
        gemeinde = {gemeinde}
    unbekannt = set(gemeinde) - set(TEIL_FEIERTAGE)
    if unbekannt:
        raise ValueError(f"Unbekannte Teil-Feiertage: {sorted(unbekannt)}")
    return {k for k in gemeinde if land in TEIL_FEIERTAGE[k]}


@lru_cache(maxsize=None)
def _feiertage(jahr: int, land: str, gemeinde: frozenset[str]) -> tuple[tuple[date, str], ...]:
    o = ostersonntag(jahr)
    t: dict[date, str] = {}

    # bundeseinheitlich
    t[date(jahr, 1, 1)] = "Neujahr"
    t[o - timedelta(days=2)] = "Karfreitag"
    t[o + timedelta(days=1)] = "Ostermontag"
    t[date(jahr, 5, 1)] = "Tag der Arbeit"
    t[o + timedelta(days=39)] = "Christi Himmelfahrt"
    t[o + timedelta(days=50)] = "Pfingstmontag"
    t[date(jahr, 10, 3)] = "Tag der Deutschen Einheit"
    t[date(jahr, 12, 25)] = "1. Weihnachtstag"
    t[date(jahr, 12, 26)] = "2. Weihnachtstag"

    # Landesfeiertage
    if land in ("BW", "BY", "ST"):
        t[date(jahr, 1, 6)] = "Heilige Drei Könige"
    if (land == "BE" and jahr >= 2019) or (land == "MV" and jahr >= 2023):
        t[date(jahr, 3, 8)] = "Internationaler Frauentag"
    if land == "BB":
        # § 2 Abs. 1 Nr. 3 und 7 FTG BB nennt sie ausdrücklich; als Sonntage ohne Wirkung auf Werktage.
        # Hessen nennt sie nicht eigens (§ 1 Abs. 1 HFeiertagsG: „die Sonntage sowie …“).
        t[o] = "Ostersonntag"
        t[o + timedelta(days=49)] = "Pfingstsonntag"
    if land in ("BW", "BY", "HE", "NW", "RP", "SL"):
        t[o + timedelta(days=60)] = "Fronleichnam"
    if land == "SL":
        t[date(jahr, 8, 15)] = "Mariä Himmelfahrt"
    if land == "TH" and jahr >= 2019:
        t[date(jahr, 9, 20)] = "Weltkindertag"
    if land in ("BB", "MV", "SN", "ST", "TH") or (land in ("HB", "HH", "NI", "SH") and jahr >= 2018):
        t[date(jahr, 10, 31)] = "Reformationstag"
    if land in ("BW", "BY", "NW", "RP", "SL"):
        t[date(jahr, 11, 1)] = "Allerheiligen"
    if land == "SN":
        t[buss_und_bettag(jahr)] = "Buß- und Bettag"

    # einmalige Feiertage
    if land == "BE" and jahr == 2020:
        t[date(2020, 5, 8)] = "75. Jahrestag der Befreiung (einmalig)"
    if land == "BE" and jahr == 2025:
        t[date(2025, 5, 8)] = "80. Jahrestag der Befreiung (einmalig)"
    if land == "BE" and jahr == 2028:
        t[date(2028, 6, 17)] = "75. Jahrestag des Aufstandes vom 17. Juni 1953 (einmalig)"

    # Teil-Feiertage (nur auf Wunsch)
    if "mariae_himmelfahrt" in gemeinde:
        t[date(jahr, 8, 15)] = "Mariä Himmelfahrt (nur einzelne Gemeinden)"
    if "fronleichnam" in gemeinde:
        t[o + timedelta(days=60)] = "Fronleichnam (nur einzelne Gemeinden)"
    if "friedensfest" in gemeinde:
        t[date(jahr, 8, 8)] = "Augsburger Hohes Friedensfest (nur Stadt Augsburg)"

    return tuple(sorted(t.items()))


def feiertage(jahr: int, land: str, gemeinde=None) -> dict[date, str]:
    """Alle gesetzlichen Feiertage eines Jahres in einem Land.

    ``gemeinde``: None (nur landesweite Feiertage), True (alle Teil-Feiertage
    des Landes) oder ein Schlüssel bzw. eine Menge aus TEIL_FEIERTAGE.
    """
    land = _pruefe(jahr, land)
    return dict(_feiertage(jahr, land, frozenset(_gemeinde_schluessel(land, gemeinde))))


def feiertag_name(d: date, land: str, gemeinde=None) -> str | None:
    return feiertage(d.year, land, gemeinde).get(d)


def ist_feiertag(d: date, land: str, gemeinde=None) -> bool:
    return d in feiertage(d.year, land, gemeinde)


def ist_werktag(d: date, land: str, samstag_ist_werktag: bool = True, gemeinde=None) -> bool:
    """Werktag = kein Sonntag, kein Feiertag im Land; Samstag nach Wahl.

    Voreinstellung samstag_ist_werktag=True entspricht dem allgemeinen
    Sprachgebrauch (§ 3 Abs. 2 BUrlG, § 573c BGB). Für die Verschiebung des
    Fristendes (§ 193 BGB, § 222 Abs. 2 ZPO usw.) samstag_ist_werktag=False.
    """
    wt = d.weekday()
    if wt == 6:
        return False
    if wt == 5 and not samstag_ist_werktag:
        return False
    return not ist_feiertag(d, land, gemeinde)


def naechster_werktag(d: date, land: str, samstag_ist_werktag: bool = False, gemeinde=None) -> date:
    """Der Tag selbst, wenn er Werktag ist, sonst der nächste Werktag danach."""
    while not ist_werktag(d, land, samstag_ist_werktag, gemeinde):
        d += timedelta(days=1)
    return d


def in_spanne(d: date) -> bool:
    """Liegt d in der geprüften Spanne der Feiertagstabelle (ERSTES_JAHR bis LETZTES_JAHR)?"""
    return ERSTES_JAHR <= d.year <= LETZTES_JAHR


def tagesart(d: date, land: str, gemeinde=None) -> str:
    """Kurzbeschreibung für den Rechenweg: 'Samstag', 'Sonntag', Feiertagsname oder 'Werktag'."""
    name = feiertag_name(d, land, gemeinde)
    if name:
        return name
    if d.weekday() == 5:
        return "Samstag"
    if d.weekday() == 6:
        return "Sonntag"
    return "Werktag"


def fmt(d: date | None) -> str:
    """Datum mit Wochentag für den Rechenweg, z. B. 'Mo 03.02.2025'."""
    if d is None:
        return "—"
    return f"{WOCHENTAGE[d.weekday()]} {d:%d.%m.%Y}"
