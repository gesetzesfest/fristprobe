# Rangliste Fristen-Benchmark (fristen-prompt-v1)

Hauptnote: Aufgabe zählt nur, wenn alle 3 Läufe exakt sind (Antwortart und Fristende). Bewertung nur per Code.

Prüfung erfundener Normen: Positivliste + Wissensbasis (6139 Gesetze, 109457 Normen, gebaut 2026-10-15T09:32:16+00:00).

Zeilen mit „+rechner“: Kette „Modell liest, Code rechnet“ (eigener Auslese-Prompt; Schema als Grammatik, bei „+rechner-json“ nur format json wie die Einzelmodelle). Normen und Sicherheit kommen dort aus dem Code: Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, Erfindungsquote, Brier und sicher+falsch messen dort den Rechner. „+rechner-v3“: geschärfter Auslese-Prompt, Gegenproben im Code und höchstens eine gezielte Nachfrage je Aufgabe (zweiter Modellaufruf).

## Gesamt

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 49/50 | 99 % | 0.987 | 92 % | 0 % | 0.0607 | 0 | 27.8 |

## Öffentlich

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 34/35 | 98 % | 0.981 | 97 % | 0 % | 0.0667 | 0 | 27.8 |

## Privat

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 15/15 | 100 % | 1 | 81 % | 0 % | 0.0467 | 0 | 27.8 |

## Typ berechnen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 30/30 | 100 % | 1 | 95 % | 0 % | 0.05 | 0 | 27.8 |

## Typ prüfen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 19/20 | 97 % | 0.967 | 86 % | 0 % | 0.0767 | 0 | 27.8 |

## Vergleich mit dem Besten (gepaart, Aufgabe als Einheit)

Bezug: qwen3:8b+rechner-v3. „nur Bester : nur Modell“ zählt die Aufgaben, die genau einer der beiden besteht; p aus dem exakten McNemar-Test, Differenz als 95-%-Intervall (Bootstrap über Aufgaben). Ab p < 0,05 gilt der Abstand als belegt, sonst gleichauf.

| Modell | bestanden | 95 % (Wilson) | nur Bester : nur Modell | p | Differenz (Prozentpunkte) | Urteil |
|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 49/50 | 90–100 % | — | — | — | Bezug |

