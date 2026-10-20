# Rangliste Fristen-Benchmark (fristen-prompt-v1)

Hauptnote: Aufgabe zählt nur, wenn alle 3 Läufe exakt sind (Antwortart und Fristende). Bewertung nur per Code.

Prüfung erfundener Normen: Positivliste + Wissensbasis (6139 Gesetze, 109457 Normen, gebaut 2026-10-15T09:32:16+00:00).

Zeilen mit „+rechner“: Kette „Modell liest, Code rechnet“ (eigener Auslese-Prompt; Schema als Grammatik, bei „+rechner-json“ nur format json wie die Einzelmodelle). Normen und Sicherheit kommen dort aus dem Code: Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, Erfindungsquote, Brier und sicher+falsch messen dort den Rechner. „+rechner-v3“: geschärfter Auslese-Prompt, Gegenproben im Code und höchstens eine gezielte Nachfrage je Aufgabe (zweiter Modellaufruf).

## Gesamt

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 50/50 | 100 % | 1 | 94 % | 0 % | 0.053 | 0 | 27.9 |
| qwen3.5:9b+rechner-v3 | 44/50 | 95 % | 0.947 | 97 % | 0 % | 0.0703 | 0 | 6.4 |

## Öffentlich

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 35/35 | 100 % | 1 | 100 % | 0 % | 0.0557 | 0 | 27.9 |
| qwen3.5:9b+rechner-v3 | 30/35 | 93 % | 0.933 | 96 % | 0 % | 0.077 | 0 | 6.4 |

## Privat

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 15/15 | 100 % | 1 | 83 % | 0 % | 0.0467 | 0 | 27.9 |
| qwen3.5:9b+rechner-v3 | 14/15 | 98 % | 0.978 | 100 % | 0 % | 0.0544 | 0 | 6.3 |

## Typ berechnen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 30/30 | 100 % | 1 | 98 % | 0 % | 0.0367 | 0 | 28 |
| qwen3.5:9b+rechner-v3 | 28/30 | 97 % | 0.967 | 99 % | 0 % | 0.0583 | 0 | 6.3 |

## Typ prüfen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 20/20 | 100 % | 1 | 88 % | 0 % | 0.0775 | 0 | 27.8 |
| qwen3.5:9b+rechner-v3 | 16/20 | 92 % | 0.917 | 93 % | 0 % | 0.0882 | 0 | 8.7 |

## Vergleich mit dem Besten (gepaart, Aufgabe als Einheit)

Bezug: qwen3:8b+rechner-v3. „nur Bester : nur Modell“ zählt die Aufgaben, die genau einer der beiden besteht; p aus dem exakten McNemar-Test, Differenz als 95-%-Intervall (Bootstrap über Aufgaben). Ab p < 0,05 gilt der Abstand als belegt, sonst gleichauf.

| Modell | bestanden | 95 % (Wilson) | nur Bester : nur Modell | p | Differenz (Prozentpunkte) | Urteil |
|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 50/50 | 93–100 % | — | — | — | Bezug |
| qwen3.5:9b+rechner-v3 | 44/50 | 76–94 % | 6 : 0 | 0.031 | +4 bis +22 | Bester belegt besser |

