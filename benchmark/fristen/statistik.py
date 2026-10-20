"""Gepaarte Statistik für den Modellvergleich (nur Standardbibliothek).

Einheit ist die Aufgabe, nicht der einzelne Lauf: Die 3 Läufe einer Aufgabe sind nicht unabhängig. Eine Aufgabe
gilt als bestanden, wenn alle Läufe exakt sind (wie die Hauptnote in bewerten.py).

- wilson(k, n): 95-%-Intervall für eine Quote (49/50 -> 89 % bis 99,6 %).
- mcnemar_exakt(b, c): zweiseitiger p-Wert aus den Aufgaben, die nur A (b) oder nur B (c) besteht.
- bootstrap_differenz(a, b, ids): 95-%-Intervall der Differenz A - B in Prozentpunkten, Aufgaben mit Zurücklegen.
- vergleich(a, b, ids): alles zusammen für die Rangliste.

Bei 50 Aufgaben trennt der Test nur große Unterschiede. Kleine Abstände (49 gegen 45) heißen „gleichauf“, bis mehr
Aufgaben (weitere Seeds) sie tragen.
"""

from __future__ import annotations

import math
import random

Z95 = 1.959964


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    nenner = 1 + z * z / n
    mitte = (p + z * z / (2 * n)) / nenner
    halb = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / nenner
    return (max(0.0, mitte - halb), min(1.0, mitte + halb))


def mcnemar_exakt(b: int, c: int) -> float:
    """Exakter McNemar-Test (Binomialtest auf den abweichenden Aufgaben), zweiseitig."""
    n = b + c
    if n == 0:
        return 1.0
    kleiner = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(kleiner + 1)) / 2 ** n)


def bootstrap_differenz(a: set[str], b: set[str], ids: list[str], ziehungen: int = 10000,
                        seed: int = 20261015) -> tuple[float, float]:
    """95-%-Intervall (Perzentil) der Differenz der Bestehensquoten A - B in Prozentpunkten."""
    if not ids:
        return (0.0, 0.0)
    rnd = random.Random(seed)
    d = [(i in a) - (i in b) for i in ids]
    n = len(d)
    werte = sorted(100 * sum(d[rnd.randrange(n)] for _ in range(n)) / n for _ in range(ziehungen))
    return (werte[int(0.025 * ziehungen)], werte[int(0.975 * ziehungen) - 1])


def vergleich(a: set[str], b: set[str], ids: list[str]) -> dict:
    """A gegen B auf denselben Aufgaben."""
    nur_a, nur_b = sorted(set(ids) & a - b), sorted(set(ids) & b - a)
    lo, hi = bootstrap_differenz(a, b, ids)
    return {"nur_a": nur_a, "nur_b": nur_b, "p": round(mcnemar_exakt(len(nur_a), len(nur_b)), 4),
            "differenz_pp": [round(lo, 1), round(hi, 1)]}
