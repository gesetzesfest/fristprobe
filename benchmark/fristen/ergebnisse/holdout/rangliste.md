# Rangliste Fristen-Benchmark (fristen-prompt-v1)

Hauptnote: Aufgabe zählt nur, wenn alle 3 Läufe exakt sind (Antwortart und Fristende). Bewertung nur per Code.

Prüfung erfundener Normen: Positivliste + Wissensbasis (6139 Gesetze, 109457 Normen, gebaut 2026-10-15T09:32:16+00:00).

Zeilen mit „+rechner“: Kette „Modell liest, Code rechnet“ (eigener Auslese-Prompt; Schema als Grammatik, bei „+rechner-json“ nur format json wie die Einzelmodelle). Normen und Sicherheit kommen dort aus dem Code: Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, Erfindungsquote, Brier und sicher+falsch messen dort den Rechner. „+rechner-v3“: geschärfter Auslese-Prompt, Gegenproben im Code und höchstens eine gezielte Nachfrage je Aufgabe (zweiter Modellaufruf).

## Gesamt

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| orakel+rechner-v3 | 50/50 | 100 % | 1 | 100 % | 0 % | 0.019 | 0 | — |
| qwen3:8b+rechner-v3 | 49/50 | 98 % | 0.98 | 95 % | 0 % | 0.033 | 0 | 16.2 |
| qwen3.5:9b+rechner-v3 | 47/50 | 98 % | 0.98 | 97 % | 0 % | 0.063 | 0 | 6.1 |
| gemma3:4b+rechner-v3 | 44/50 | 91 % | 0.913 | 85 % | 0 % | 0.1953 | 10 | 30.6 |
| qwen3:4b+rechner-v3 | 42/50 | 87 % | 0.873 | 96 % | 0 % | 0.1319 | 4 | 28.3 |
| qwen3:8b+rechner | 38/50 | 79 % | 0.793 | 78 % | 0 % | 0.1177 | 1 | 18 |
| gemma4:e4b-it-qat+rechner-v3 | 37/50 | 87 % | 0.873 | 90 % | 0 % | 0.0928 | 0 | 33.6 |

## Öffentlich

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| orakel+rechner-v3 | 35/35 | 100 % | 1 | 100 % | 0 % | 0.0186 | 0 | — |
| qwen3.5:9b+rechner-v3 | 34/35 | 99 % | 0.99 | 97 % | 0 % | 0.0605 | 0 | 6.1 |
| qwen3:8b+rechner-v3 | 34/35 | 97 % | 0.971 | 98 % | 0 % | 0.0386 | 0 | 16.2 |
| gemma3:4b+rechner-v3 | 30/35 | 90 % | 0.895 | 85 % | 0 % | 0.2055 | 8 | 30.6 |
| qwen3:4b+rechner-v3 | 28/35 | 85 % | 0.848 | 96 % | 0 % | 0.1585 | 4 | 28.3 |
| gemma4:e4b-it-qat+rechner-v3 | 26/35 | 89 % | 0.886 | 91 % | 0 % | 0.0912 | 0 | 33.6 |
| qwen3:8b+rechner | 25/35 | 76 % | 0.762 | 81 % | 0 % | 0.1325 | 1 | 18 |

## Privat

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| orakel+rechner-v3 | 15/15 | 100 % | 1 | 100 % | 0 % | 0.02 | 0 | — |
| qwen3:8b+rechner-v3 | 15/15 | 100 % | 1 | 86 % | 0 % | 0.02 | 0 | 16.2 |
| gemma3:4b+rechner-v3 | 14/15 | 96 % | 0.956 | 86 % | 0 % | 0.1716 | 2 | 31.2 |
| qwen3:4b+rechner-v3 | 14/15 | 93 % | 0.933 | 96 % | 0 % | 0.07 | 0 | 28.2 |
| qwen3.5:9b+rechner-v3 | 13/15 | 96 % | 0.956 | 98 % | 0 % | 0.0689 | 0 | 6.1 |
| qwen3:8b+rechner | 13/15 | 87 % | 0.867 | 71 % | 0 % | 0.0833 | 0 | 18.1 |
| gemma4:e4b-it-qat+rechner-v3 | 11/15 | 84 % | 0.844 | 87 % | 0 % | 0.0964 | 0 | 33.8 |

## Typ berechnen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| orakel+rechner-v3 | 30/30 | 100 % | 1 | 100 % | 0 % | 0.01 | 0 | — |
| qwen3:8b+rechner-v3 | 30/30 | 100 % | 1 | 97 % | 0 % | 0.0167 | 0 | 16.3 |
| qwen3.5:9b+rechner-v3 | 27/30 | 97 % | 0.967 | 96 % | 0 % | 0.07 | 0 | 6.1 |
| gemma3:4b+rechner-v3 | 26/30 | 91 % | 0.911 | 87 % | 0 % | 0.1744 | 5 | 31 |
| qwen3:4b+rechner-v3 | 26/30 | 88 % | 0.878 | 93 % | 0 % | 0.0894 | 0 | 28.4 |
| gemma4:e4b-it-qat+rechner-v3 | 25/30 | 92 % | 0.922 | 94 % | 0 % | 0.0694 | 0 | 33.9 |
| qwen3:8b+rechner | 25/30 | 84 % | 0.844 | 79 % | 0 % | 0.0861 | 0 | 18 |

## Typ prüfen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| orakel+rechner-v3 | 20/20 | 100 % | 1 | 100 % | 0 % | 0.0325 | 0 | — |
| qwen3.5:9b+rechner-v3 | 20/20 | 100 % | 1 | 100 % | 0 % | 0.0525 | 0 | 6.1 |
| qwen3:8b+rechner-v3 | 19/20 | 95 % | 0.95 | 91 % | 0 % | 0.0575 | 0 | 16.1 |
| gemma3:4b+rechner-v3 | 18/20 | 92 % | 0.917 | 82 % | 0 % | 0.2267 | 5 | 30.5 |
| qwen3:4b+rechner-v3 | 16/20 | 87 % | 0.867 | 100 % | 0 % | 0.1957 | 4 | 28.1 |
| qwen3:8b+rechner | 13/20 | 72 % | 0.717 | 76 % | 0 % | 0.1652 | 1 | 18 |
| gemma4:e4b-it-qat+rechner-v3 | 12/20 | 80 % | 0.8 | 83 % | 0 % | 0.1278 | 0 | 33.4 |

## Vergleich mit dem Besten (gepaart, Aufgabe als Einheit)

Bezug: qwen3:8b+rechner-v3. „nur Bester : nur Modell“ zählt die Aufgaben, die genau einer der beiden besteht; p aus dem exakten McNemar-Test, Differenz als 95-%-Intervall (Bootstrap über Aufgaben). Ab p < 0,05 gilt der Abstand als belegt, sonst gleichauf.

| Modell | bestanden | 95 % (Wilson) | nur Bester : nur Modell | p | Differenz (Prozentpunkte) | Urteil |
|---|---|---|---|---|---|---|
| orakel+rechner-v3 | 50/50 | 93–100 % | 0 : 1 | 1.000 | -6 bis +0 | gleichauf (nicht trennbar) |
| qwen3:8b+rechner-v3 | 49/50 | 90–100 % | — | — | — | Bezug |
| qwen3.5:9b+rechner-v3 | 47/50 | 84–98 % | 3 : 1 | 0.625 | -4 bis +12 | gleichauf (nicht trennbar) |
| gemma3:4b+rechner-v3 | 44/50 | 76–94 % | 6 : 1 | 0.125 | +0 bis +20 | gleichauf (nicht trennbar) |
| qwen3:4b+rechner-v3 | 42/50 | 72–92 % | 7 : 0 | 0.016 | +6 bis +24 | Bester belegt besser |
| qwen3:8b+rechner | 38/50 | 63–86 % | 11 : 0 | 0.001 | +12 bis +34 | Bester belegt besser |
| gemma4:e4b-it-qat+rechner-v3 | 37/50 | 60–84 % | 13 : 1 | 0.002 | +12 bis +38 | Bester belegt besser |

