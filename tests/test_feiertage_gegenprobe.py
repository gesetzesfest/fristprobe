"""Gegenprobe der Feiertagstabelle mit dem unabhängigen Paket ``holidays`` (MIT, Community-Pflege, nicht amtlich).

Läuft nur, wenn ``holidays`` installiert ist; die Laufzeit des Projekts bleibt reine Standardbibliothek.
Einmalig zum Prüfen:  uv run --with holidays python -m unittest tests.test_feiertage_gegenprobe
Stand 15.10.2026 (holidays 0.106): 16 Länder x 2020 bis 2030, 0 Abweichungen.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

from pruefki.fristen.feiertage import LAENDER, feiertage  # noqa: E402

try:
    import holidays
except ImportError:  # pragma: no cover
    holidays = None


@unittest.skipIf(holidays is None, "Paket holidays fehlt (nur für die Gegenprobe nötig)")
class GegenprobeHolidays(unittest.TestCase):
    def test_landesweite_feiertage_2020_bis_2030(self):
        abweichungen = []
        for land in LAENDER:
            for jahr in range(2020, 2031):
                unsere = set(feiertage(jahr, land))
                fremde = set(holidays.Germany(subdiv=land, years=jahr))
                if unsere != fremde:
                    abweichungen.append((land, jahr, sorted(unsere - fremde), sorted(fremde - unsere)))
        self.assertEqual(abweichungen, [])


if __name__ == "__main__":
    unittest.main()
