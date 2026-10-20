# Rangliste Fristen-Benchmark (fristen-prompt-v1)

Hauptnote: Aufgabe zählt nur, wenn alle 3 Läufe exakt sind (Antwortart und Fristende). Bewertung nur per Code.

Prüfung erfundener Normen: Positivliste + Wissensbasis (6139 Gesetze, 109457 Normen, gebaut 2026-10-15T09:32:16+00:00).

Zeilen mit „+rechner“: Kette „Modell liest, Code rechnet“ (eigener Auslese-Prompt; Schema als Grammatik, bei „+rechner-json“ nur format json wie die Einzelmodelle). Normen und Sicherheit kommen dort aus dem Code: Mit den Einzelmodellen vergleichbar ist nur „exakt“; Belegquote, Erfindungsquote, Brier und sicher+falsch messen dort den Rechner. „+rechner-v3“: geschärfter Auslese-Prompt, Gegenproben im Code und höchstens eine gezielte Nachfrage je Aufgabe (zweiter Modellaufruf).

## Gesamt

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 49/50 | 98 % | 0.98 | 96 % | 0 % | 0.0358 | 0 | 16.3 |
| qwen3.5:9b-nvfp4+rechner-v3 | 48/50 | 97 % | 0.973 | 99 % | 0 % | 0.0503 | 0 | 21 |
| qwen3:4b+rechner-v3 | 47/50 | 95 % | 0.953 | 98 % | 0 % | 0.0711 | 0 | 26.8 |
| claude-opus-5.5 | 45/50 | 93 % | 0.927 | 99 % | 0 % | 0.0737 | 1 | — |
| qwen3.5:9b+rechner-v3 | 44/50 | 96 % | 0.96 | 99 % | 0 % | 0.063 | 0 | 8.9 |
| gemma3:4b+rechner-v3 | 44/50 | 91 % | 0.907 | 85 % | 0 % | 0.1933 | 9 | 29.2 |
| qwen3:8b+rechner | 40/50 | 82 % | 0.82 | 78 % | 0 % | 0.1192 | 3 | 17.2 |
| qwen3.5:4b-nvfp4+rechner-v3 | 36/50 | 88 % | 0.88 | 96 % | 0 % | 0.1149 | 1 | 33.4 |
| gemma4:e4b-it-qat+rechner-v3 | 36/50 | 83 % | 0.833 | 89 % | 0 % | 0.1098 | 0 | 32.3 |
| gemma3:4b+rechner | 33/50 | 69 % | 0.693 | 80 % | 0 % | 0.2557 | 11 | 30.9 |
| qwen3:4b+rechner | 32/50 | 68 % | 0.68 | 84 % | 0 % | 0.1958 | 7 | 37.2 |
| phi4-mini:latest+rechner | 20/50 | 51 % | 0.513 | 55 % | 0 % | 0.2716 | 6 | 38.8 |
| qwen3:1.7b+rechner | 18/50 | 40 % | 0.42 | 57 % | 0 % | 0.2646 | 4 | 75.2 |
| llama3.2:3b+rechner | 12/50 | 48 % | 0.48 | 65 % | 0 % | 0.2664 | 4 | 49.1 |
| qwen3:8b | 8/50 | 18 % | 0.203 | 5 % | 43 % | 1.6154 | 121 | 20.8 |
| llama3.2:3b | 6/50 | 19 % | 0.237 | 4 % | 8 % | 0.8835 | 79 | 38.4 |
| gemma3:4b | 5/50 | 11 % | 0.153 | 7 % | 26 % | 1.5874 | 133 | 40.7 |
| qwen3:4b | 4/50 | 15 % | 0.177 | 4 % | 31 % | 1.5753 | 128 | 22.6 |
| qwen3:1.7b | 1/50 | 3 % | 0.03 | 9 % | 0 % | 1.4645 | 133 | 55.1 |
| phi4-mini:latest | 0/50 | 0 % | 0.04 | 6 % | 33 % | 2 | 150 | 27 |

## Öffentlich

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 35/35 | 100 % | 1 | 97 % | 0 % | 0.0314 | 0 | 16.3 |
| qwen3:4b+rechner-v3 | 34/35 | 99 % | 0.99 | 98 % | 0 % | 0.0633 | 0 | 26.8 |
| qwen3.5:9b-nvfp4+rechner-v3 | 33/35 | 96 % | 0.962 | 100 % | 0 % | 0.049 | 0 | 21 |
| gemma3:4b+rechner-v3 | 31/35 | 92 % | 0.924 | 91 % | 0 % | 0.1758 | 6 | 29.1 |
| claude-opus-5.5 | 31/35 | 91 % | 0.914 | 98 % | 0 % | 0.0796 | 1 | — |
| qwen3.5:9b+rechner-v3 | 29/35 | 94 % | 0.943 | 99 % | 0 % | 0.06 | 0 | 8.9 |
| qwen3:8b+rechner | 29/35 | 86 % | 0.857 | 89 % | 0 % | 0.1131 | 3 | 17.3 |
| gemma4:e4b-it-qat+rechner-v3 | 24/35 | 81 % | 0.81 | 92 % | 0 % | 0.1051 | 0 | 32.3 |
| qwen3.5:4b-nvfp4+rechner-v3 | 23/35 | 85 % | 0.848 | 95 % | 0 % | 0.1318 | 1 | 33.4 |
| gemma3:4b+rechner | 23/35 | 70 % | 0.695 | 90 % | 0 % | 0.259 | 9 | 30.8 |
| qwen3:4b+rechner | 21/35 | 66 % | 0.657 | 89 % | 0 % | 0.2254 | 7 | 37.2 |
| phi4-mini:latest+rechner | 14/35 | 52 % | 0.524 | 62 % | 0 % | 0.2413 | 2 | 38.8 |
| qwen3:1.7b+rechner | 11/35 | 36 % | 0.386 | 54 % | 0 % | 0.2392 | 0 | 75.2 |
| llama3.2:3b+rechner | 8/35 | 48 % | 0.476 | 69 % | 0 % | 0.2816 | 4 | 49 |
| qwen3:8b | 4/35 | 14 % | 0.176 | 4 % | 46 % | 1.6791 | 88 | 20.9 |
| gemma3:4b | 4/35 | 11 % | 0.157 | 9 % | 31 % | 1.5744 | 93 | 40.8 |
| llama3.2:3b | 3/35 | 18 % | 0.233 | 6 % | 10 % | 0.9416 | 60 | 38.6 |
| qwen3:4b | 3/35 | 14 % | 0.181 | 4 % | 31 % | 1.5837 | 90 | 22.7 |
| qwen3:1.7b | 1/35 | 4 % | 0.043 | 13 % | 0 % | 1.4188 | 91 | 55.1 |
| phi4-mini:latest | 0/35 | 0 % | 0.048 | 4 % | 38 % | 2 | 105 | 27 |

## Privat

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3.5:9b-nvfp4+rechner-v3 | 15/15 | 100 % | 1 | 98 % | 0 % | 0.0533 | 0 | 21 |
| qwen3.5:9b+rechner-v3 | 15/15 | 100 % | 1 | 100 % | 0 % | 0.07 | 0 | 8.8 |
| claude-opus-5.5 | 14/15 | 96 % | 0.956 | 100 % | 0 % | 0.0601 | 0 | — |
| qwen3:8b+rechner-v3 | 14/15 | 93 % | 0.933 | 93 % | 0 % | 0.046 | 0 | 16.3 |
| qwen3.5:4b-nvfp4+rechner-v3 | 13/15 | 96 % | 0.956 | 98 % | 0 % | 0.0756 | 0 | 33.3 |
| qwen3:4b+rechner-v3 | 13/15 | 87 % | 0.867 | 100 % | 0 % | 0.0893 | 0 | 26.8 |
| gemma3:4b+rechner-v3 | 13/15 | 87 % | 0.867 | 74 % | 0 % | 0.234 | 3 | 29.5 |
| gemma4:e4b-it-qat+rechner-v3 | 12/15 | 89 % | 0.889 | 80 % | 0 % | 0.1207 | 0 | 32.1 |
| qwen3:4b+rechner | 11/15 | 73 % | 0.733 | 74 % | 0 % | 0.1267 | 0 | 37.2 |
| qwen3:8b+rechner | 11/15 | 73 % | 0.733 | 55 % | 0 % | 0.1333 | 0 | 17.2 |
| gemma3:4b+rechner | 10/15 | 69 % | 0.689 | 59 % | 0 % | 0.2482 | 2 | 31.1 |
| qwen3:1.7b+rechner | 7/15 | 49 % | 0.5 | 66 % | 0 % | 0.3238 | 4 | 75.2 |
| phi4-mini:latest+rechner | 6/15 | 47 % | 0.489 | 39 % | 0 % | 0.3422 | 4 | 38.8 |
| llama3.2:3b+rechner | 4/15 | 49 % | 0.489 | 55 % | 0 % | 0.2309 | 0 | 49.1 |
| qwen3:8b | 4/15 | 27 % | 0.267 | 8 % | 38 % | 1.4667 | 33 | 20.7 |
| llama3.2:3b | 3/15 | 22 % | 0.244 | 1 % | 2 % | 0.7479 | 19 | 38.1 |
| qwen3:4b | 1/15 | 16 % | 0.167 | 3 % | 30 % | 1.5557 | 38 | 22.5 |
| gemma3:4b | 1/15 | 11 % | 0.144 | 3 % | 12 % | 1.6178 | 40 | 40.5 |
| phi4-mini:latest | 0/15 | 0 % | 0.022 | 8 % | 22 % | 2 | 45 | 27.1 |
| qwen3:1.7b | 0/15 | 0 % | 0 | 0 % | 0 % | 1.5711 | 42 | 55 |

## Typ berechnen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 30/30 | 100 % | 1 | 97 % | 0 % | 0.015 | 0 | 16.4 |
| qwen3.5:9b-nvfp4+rechner-v3 | 29/30 | 97 % | 0.967 | 100 % | 0 % | 0.0433 | 0 | 20.9 |
| qwen3:4b+rechner-v3 | 29/30 | 97 % | 0.967 | 98 % | 0 % | 0.06 | 0 | 26.9 |
| claude-opus-5.5 | 28/30 | 93 % | 0.933 | 98 % | 0 % | 0.055 | 0 | — |
| qwen3.5:9b+rechner-v3 | 27/30 | 97 % | 0.967 | 99 % | 0 % | 0.0583 | 0 | 8.9 |
| gemma3:4b+rechner-v3 | 26/30 | 89 % | 0.889 | 86 % | 0 % | 0.2426 | 8 | 29.3 |
| qwen3:8b+rechner | 25/30 | 84 % | 0.844 | 78 % | 0 % | 0.0744 | 0 | 17.3 |
| gemma4:e4b-it-qat+rechner-v3 | 24/30 | 88 % | 0.878 | 91 % | 0 % | 0.09 | 0 | 32.6 |
| qwen3:4b+rechner | 22/30 | 78 % | 0.778 | 80 % | 0 % | 0.0928 | 0 | 37.3 |
| gemma3:4b+rechner | 21/30 | 72 % | 0.722 | 80 % | 0 % | 0.1556 | 0 | 30.9 |
| qwen3.5:4b-nvfp4+rechner-v3 | 20/30 | 87 % | 0.867 | 96 % | 0 % | 0.1161 | 1 | 33.4 |
| phi4-mini:latest+rechner | 12/30 | 50 % | 0.511 | 57 % | 0 % | 0.2691 | 3 | 38.7 |
| qwen3:1.7b+rechner | 10/30 | 39 % | 0.422 | 48 % | 0 % | 0.2386 | 1 | 75.5 |
| llama3.2:3b+rechner | 8/30 | 49 % | 0.489 | 62 % | 0 % | 0.2699 | 3 | 49.1 |
| gemma3:4b | 4/30 | 13 % | 0.2 | 5 % | 30 % | 1.6383 | 78 | 40.7 |
| llama3.2:3b | 3/30 | 12 % | 0.194 | 4 % | 5 % | 0.9844 | 55 | 38 |
| qwen3:4b | 3/30 | 12 % | 0.172 | 3 % | 28 % | 1.5955 | 79 | 22.5 |
| qwen3:8b | 2/30 | 9 % | 0.128 | 3 % | 48 % | 1.7812 | 80 | 20.8 |
| phi4-mini:latest | 0/30 | 0 % | 0.067 | 6 % | 34 % | 2 | 90 | 26.6 |
| qwen3:1.7b | 0/30 | 0 % | 0.006 | 8 % | 0 % | 1.5923 | 88 | 55.2 |

## Typ prüfen

| Modell | exakt (alle Läufe) | exakt je Antwort | Teilpunkte | Belegquote | Erfindungsquote | Brier | sicher+falsch | Token/s (Median) |
|---|---|---|---|---|---|---|---|---|
| qwen3.5:9b-nvfp4+rechner-v3 | 19/20 | 98 % | 0.983 | 97 % | 0 % | 0.0608 | 0 | 21 |
| qwen3:8b+rechner-v3 | 19/20 | 95 % | 0.95 | 94 % | 0 % | 0.067 | 0 | 16.2 |
| qwen3:4b+rechner-v3 | 18/20 | 93 % | 0.933 | 100 % | 0 % | 0.0878 | 0 | 26.6 |
| gemma3:4b+rechner-v3 | 18/20 | 93 % | 0.933 | 84 % | 0 % | 0.1193 | 1 | 29.2 |
| qwen3.5:9b+rechner-v3 | 17/20 | 95 % | 0.95 | 99 % | 0 % | 0.07 | 0 | 8.9 |
| claude-opus-5.5 | 17/20 | 92 % | 0.917 | 100 % | 0 % | 0.1019 | 1 | — |
| qwen3.5:4b-nvfp4+rechner-v3 | 16/20 | 90 % | 0.9 | 97 % | 0 % | 0.1132 | 0 | 33.4 |
| qwen3:8b+rechner | 15/20 | 78 % | 0.783 | 78 % | 0 % | 0.1863 | 3 | 17.2 |
| gemma4:e4b-it-qat+rechner-v3 | 12/20 | 77 % | 0.767 | 84 % | 0 % | 0.1395 | 0 | 31.9 |
| gemma3:4b+rechner | 12/20 | 65 % | 0.65 | 80 % | 0 % | 0.406 | 11 | 30.8 |
| qwen3:4b+rechner | 10/20 | 53 % | 0.533 | 92 % | 0 % | 0.3503 | 7 | 36.8 |
| phi4-mini:latest+rechner | 8/20 | 52 % | 0.517 | 50 % | 0 % | 0.2753 | 3 | 38.8 |
| qwen3:1.7b+rechner | 8/20 | 42 % | 0.417 | 75 % | 0 % | 0.3037 | 3 | 74.6 |
| qwen3:8b | 6/20 | 32 % | 0.317 | 8 % | 37 % | 1.3667 | 41 | 20.9 |
| llama3.2:3b+rechner | 4/20 | 47 % | 0.467 | 70 % | 0 % | 0.2612 | 1 | 48.8 |
| llama3.2:3b | 3/20 | 30 % | 0.3 | 5 % | 12 % | 0.732 | 24 | 39.3 |
| qwen3:4b | 1/20 | 18 % | 0.183 | 5 % | 36 % | 1.5449 | 49 | 22.9 |
| gemma3:4b | 1/20 | 8 % | 0.083 | 10 % | 20 % | 1.5112 | 55 | 40.8 |
| qwen3:1.7b | 1/20 | 7 % | 0.067 | 9 % | 0 % | 1.2727 | 45 | 54.9 |
| phi4-mini:latest | 0/20 | 0 % | 0 | 4 % | 30 % | 2 | 60 | 27.3 |

## Vergleich mit dem Besten (gepaart, Aufgabe als Einheit)

Bezug: qwen3:8b+rechner-v3. „nur Bester : nur Modell“ zählt die Aufgaben, die genau einer der beiden besteht; p aus dem exakten McNemar-Test, Differenz als 95-%-Intervall (Bootstrap über Aufgaben). Ab p < 0,05 gilt der Abstand als belegt, sonst gleichauf.

| Modell | bestanden | 95 % (Wilson) | nur Bester : nur Modell | p | Differenz (Prozentpunkte) | Urteil |
|---|---|---|---|---|---|---|
| qwen3:8b+rechner-v3 | 49/50 | 90–100 % | — | — | — | Bezug |
| qwen3.5:9b-nvfp4+rechner-v3 | 48/50 | 86–99 % | 2 : 1 | 1.000 | -4 bis +10 | gleichauf (nicht trennbar) |
| qwen3:4b+rechner-v3 | 47/50 | 84–98 % | 2 : 0 | 0.500 | +0 bis +10 | gleichauf (nicht trennbar) |
| claude-opus-5.5 | 45/50 | 79–96 % | 5 : 1 | 0.219 | +0 bis +18 | gleichauf (nicht trennbar) |
| gemma3:4b+rechner-v3 | 44/50 | 76–94 % | 5 : 0 | 0.062 | +2 bis +20 | gleichauf (nicht trennbar) |
| qwen3.5:9b+rechner-v3 | 44/50 | 76–94 % | 6 : 1 | 0.125 | +0 bis +20 | gleichauf (nicht trennbar) |
| qwen3:8b+rechner | 40/50 | 67–89 % | 10 : 1 | 0.012 | +6 bis +30 | Bester belegt besser |
| gemma4:e4b-it-qat+rechner-v3 | 36/50 | 58–82 % | 13 : 0 | < 0.001 | +14 bis +38 | Bester belegt besser |
| qwen3.5:4b-nvfp4+rechner-v3 | 36/50 | 58–82 % | 14 : 1 | 0.001 | +14 bis +40 | Bester belegt besser |
| gemma3:4b+rechner | 33/50 | 52–78 % | 16 : 0 | < 0.001 | +20 bis +46 | Bester belegt besser |
| qwen3:4b+rechner | 32/50 | 50–76 % | 17 : 0 | < 0.001 | +22 bis +48 | Bester belegt besser |
| phi4-mini:latest+rechner | 20/50 | 28–54 % | 29 : 0 | < 0.001 | +44 bis +72 | Bester belegt besser |
| qwen3:1.7b+rechner | 18/50 | 24–50 % | 32 : 1 | < 0.001 | +48 bis +76 | Bester belegt besser |
| llama3.2:3b+rechner | 12/50 | 14–37 % | 38 : 1 | < 0.001 | +60 bis +86 | Bester belegt besser |
| qwen3:8b | 8/50 | 8–28 % | 41 : 0 | < 0.001 | +70 bis +92 | Bester belegt besser |
| llama3.2:3b | 6/50 | 6–24 % | 43 : 0 | < 0.001 | +76 bis +94 | Bester belegt besser |
| gemma3:4b | 5/50 | 4–21 % | 44 : 0 | < 0.001 | +78 bis +96 | Bester belegt besser |
| qwen3:4b | 4/50 | 3–19 % | 45 : 0 | < 0.001 | +80 bis +98 | Bester belegt besser |
| qwen3:1.7b | 1/50 | 0–10 % | 48 : 0 | < 0.001 | +90 bis +100 | Bester belegt besser |
| phi4-mini:latest | 0/50 | 0–7 % | 49 : 0 | < 0.001 | +94 bis +100 | Bester belegt besser |

