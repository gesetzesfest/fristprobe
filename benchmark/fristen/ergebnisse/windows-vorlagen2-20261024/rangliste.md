# Rangliste Fristen-Benchmark (fristen-prompt-v1)

Hauptnote: Aufgabe zählt nur, wenn alle 3 Läufe exakt sind (Antwortart und Fristende). Bewertung nur per Code.

Prüfung erfundener Normen: Positivliste + Wissensbasis (6139 Gesetze, 109457 Normen, gebaut 2026-10-15T09:32:16+00:00).

Zeilen mit „+rechner“: Kette „Modell liest, Code rechnet“ (eigener Auslese-Prompt; Schema als Grammatik, bei „+rechner-json“ nur format json wie die Einzelmodelle). Normen und Sicherheit kommen dort aus dem Code: Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, Erfindungsquote, Brier und sicher+falsch messen dort den Rechner. „+rechner-v3“: geschärfter Auslese-Prompt, Gegenproben im Code und höchstens eine gezielte Nachfrage je Aufgabe (zweiter Modellaufruf).

## Gesamt

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 0/50 | 81 % | 0.814 | 79 % | 0 % | 0.0877 | 0 | 23.7 |

## Öffentlich

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 0/35 | 77 % | 0.767 | 76 % | 0 % | 0.0997 | 0 | 23.6 |

## Privat

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 0/15 | 92 % | 0.923 | 85 % | 0 % | 0.06 | 0 | 23.7 |

## Typ berechnen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 0/30 | 77 % | 0.769 | 79 % | 0 % | 0.0854 | 0 | 23.7 |

## Typ prüfen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 0/20 | 88 % | 0.882 | 79 % | 0 % | 0.0912 | 0 | 23.4 |

## Vergleich mit dem Besten (gepaart, Aufgabe als Einheit)

Bezug: qwen3:8b+rechner-v3. „nur Bester : nur Modell“ zählt die Aufgaben, die genau einer der beiden besteht; p aus dem exakten McNemar-Test, Differenz als 95-%-Intervall (Bootstrap über Aufgaben). Ab p < 0,05 gilt der Abstand als belegt, sonst gleichauf.

| Modell | bestanden | 95 % (Wilson) | nur Bester : nur Modell | p | Differenz (Prozentpunkte) | Urteil |
|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 0/50 | 0–7 % | — | — | — | Bezug |

