# Gesetzesfest · Fristprobe

Prüfreihe 1 von https://gesetzesfest.de.

Eine deutsche Prüf-KI, die Dokumente gegen Regeln prüft und jeden Befund mit einer Norm belegt.
Erster Baustein: der **Bürokratie-Benchmark**, Klasse 1 „Fristen“. Ein Modell bekommt einen erfundenen Bescheid,
Vertrag oder ein Kündigungsschreiben und muss das Fristende und die tragenden Normen nennen oder ein genanntes
Fristende prüfen.

Grundsätze: Sollwerte kommen nur aus Python-Code (`pruefki/fristen/rechner.py`), nie aus einer KI. Jede
Rechenzeile verweist auf eine Regel-ID in `recht/belege.json`. Strittige Fälle kommen nicht in die Wertung
(`benchmark/fristen/offen.md`). Alle Personen, Orte, Behörden und Aktenzeichen sind erfunden.
Nur Python-Standardbibliothek, Python 3.12.

## Aufbau

```
recht/belege.json                 geprüfte Rechtsregeln aus der Recherche (Regel-IDs FR-, AR-, KS-, MI-, A-, B-, ...)
pruefki/fristen/feiertage.py      Feiertage je Bundesland 2020 bis 2030, Ostern per Algorithmus
pruefki/fristen/rechner.py        Fristenrechner mit Rechenweg und Normen
pruefki/fristen/normen.py         Normen erkennen und vergleichen, Positivliste
tests/                            Unit-Tests (von Hand nachgerechnete Sollwerte, Gegenprobe, Benchmark)
benchmark/fristen/generator.py    erzeugt aufgaben.jsonl (50 Aufgaben, fester Seed; Ereignistage 2025 bis 2027,
                                  Fristenden und Termine bis 2028)
benchmark/fristen/prompt.py       System-Prompt und Antwortformat für alle Modelle
benchmark/fristen/run_ollama.py   lokale Modelle über Ollama laufen lassen
benchmark/fristen/opus_auftrag.py Aufträge ohne Sollwert für blinde Opus-Antworten
benchmark/fristen/run_antworten.py fremde Antworten ins Ergebnisformat einlesen
benchmark/fristen/bewerten.py     Bewertung nur per Code -> rangliste.md / rangliste.json
benchmark/fristen/prompt_kette.py Auslese-Prompt und Auslese-Schema der Kette (nur Tatsachen)
benchmark/fristen/kette.py        Kette „Modell liest, Code rechnet“ (Ollama oder Orakel + Rechner)
benchmark/fristen/fehleranalyse.py falsch ausgelesene Felder der Kette zählen
benchmark/fristen/offen.md        strittige Fälle und Annahmen für Fachleute
benchmark/fristen/geheim.py       geheime Seeds: Hash vorab in geheim_hashes.json, Seed erst bei Freigabe
benchmark/fristen/beispiel/       künstliche Antworten zum Testen der Bewertung
benchmark/tempo.py                Token/s kalt und warm nach Dauerlast
```

## Befehle

```sh
PY=python3.12

$PY -m unittest discover -s tests -v                  # alle Tests
$PY benchmark/fristen/generator.py --tabelle          # Aufgaben neu erzeugen (reproduzierbar)

$PY benchmark/fristen/run_ollama.py                   # 6 Standardmodelle, 3 Läufe, Denkmodus aus
$PY benchmark/fristen/run_ollama.py --modelle qwen3:8b --think
$PY benchmark/fristen/opus_auftrag.py                 # -> opus_auftrag.jsonl (id, system, user)
$PY benchmark/fristen/run_antworten.py antworten.jsonl   # (modell, id, lauf, antwort) einlesen
$PY benchmark/fristen/bewerten.py                     # -> rangliste.md, rangliste.json

$PY benchmark/tempo.py --minuten 15                   # kalt vs. warm, je Modell
```

Ergebnisse landen in `benchmark/fristen/ergebnisse/<datum>-<modell>.jsonl`; ein abgebrochener Lauf setzt dort wieder
auf. Veröffentlicht sind nur die Ranglisten je Lauf, nicht die Rohantworten.

## Kette

Das kleine Modell liest nur aus, der Code rechnet. Schritt 1: Das Modell bekommt nur Dokument und Frage und füllt ein
festes JSON mit Tatsachen (Schema `fristen-kette-auslese-v2` in `prompt_kette.py`, über Ollamas `format` erzwungen;
lehnt der Server das Schema ab, weiter mit `format: "json"`). Der Prompt beschreibt jedes Feld nur über seine
Bedeutung: keine Namen, Wendungen oder Daten aus den Aufgaben (v1 nahm Fallen einzelner Aufgaben vorweg, auch im
privaten Split; ein Test sichert das ab). Felder: `schreiben`, `verfahren` (SGB X, VwVfG, AO),
`bundesland`, `art` (wie im Generator), `datum_schreiben`, `zustellart`, `datum_aufgabe_post`, `datum_zustellung`,
`datum_zugang`, `rechtsbehelfsbelehrung`, `kuendigende_partei`, `ueberlassung`, `beschaeftigungsbeginn`, `probezeit`,
`probezeit_monate`, `genanntes_fristende`; jedes darf null sein, Daten wie im Dokument (TT.MM.JJJJ). Kein Fristende,
keine Norm, keine Antwortart. Schritt 2: `kette.py` bildet die Felder auf `pruefki/fristen/rechner.py` ab. Bei
Bescheiden bestimmt der Code die Art aus `schreiben` und `verfahren` (das Feld `art` ist Gegenprobe), bei Prüfaufgaben
vergleicht er genanntes und berechnetes Fristende; bei Arbeitskündigungen ist die Frage (Klagefrist oder
Beendigungstermin) die Gegenprobe zum Feld `art`. Fehlt ein nötiges Feld: `rueckfrage`. Eine leere Auslese oder eine
ohne bestimmbare Art ergibt keine Antwort (zählt wie unlesbar), damit ein Modell, das nichts liest, die
Rückfrage-Aufgaben nicht geschenkt bekommt. Sicherheit 0,9, wenn alles da und lesbar ist und der Rechner keinen
Vorbehalt meldet; 0,6 bei Vorgaben (z. B. Belehrung nicht gelesen), unlesbaren Feldern oder Widersprüchen zwischen
Feldern; 0,5 bei Rechner-Vorbehalt; 0,3, wenn der Rechner die Angaben ablehnt. Daten außerhalb 1900 bis 2099 gelten
als unlesbar.

```sh
$PY benchmark/fristen/kette.py --modelle qwen3:8b llama3.2:3b     # -> ergebnisse/<datum>-<modell>+rechner.jsonl
$PY benchmark/fristen/kette.py --orakel --ausgabe-dir /tmp/kette  # wahre Felder statt Modell: Obergrenze, 50/50
$PY benchmark/fristen/bewerten.py                                 # wertet <modell>+rechner wie ein eigenes Modell
$PY benchmark/fristen/fehleranalyse.py                            # welches Feld wie oft falsch gelesen wurde
$PY benchmark/fristen/kette.py --modelle qwen3:8b --format json   # Kontrolllauf ohne Schema -> <modell>+rechner-json
$PY benchmark/fristen/generator.py --seed 7 --ausgabe /tmp/seed7.jsonl   # frische Aufgaben (gleiche Vorlagen)
$PY benchmark/fristen/kette.py --aufgaben /tmp/seed7.jsonl --ausgabe-dir /tmp/seed7 --modelle qwen3:8b
```

Vergleich mit den Einzelmodellen: Nur „exakt“ ist vergleichbar. Normen und Sicherheit der Kette kommen aus dem Code,
Belegquote, Erfindungsquote, Brier und „sicher und falsch“ messen dort den Rechner (die Rangliste sagt das). Die Kette
bekommt das Schema als Grammatik, die Einzelmodelle nur `format: "json"`; `--format json` trennt beide Effekte.
Öffentlich und privat getrennt lesen; der private Split ist für den Auslese-Prompt nicht zurückgehalten, daher
zusätzlich auf frischen Seeds messen. `fehleranalyse.py` zählt gleichwertige Lesarten (gleiche Rechnung wie mit den
wahren Feldern) nicht als „falsch, nötig“.

Die Ergebniszeilen haben das Format von `run_ollama.py`, dazu `felder_roh`, `felder` und `rechnung` (Abbildung,
fehlende Felder, Annahmen, unlesbare Felder). Das Orakel ergibt 50/50, Belegquote 100 %, keine erfundene Norm, auch
auf frischen Seeds (1 bis 8, 11, 42 geprüft).

## Wissensbasis

Bibliothek des Bundesrechts: alle Gesetze und Verordnungen von gesetze-im-internet.de als SQLite mit Volltext (FTS5).
Die Rohdaten (`daten/bund/`) und die Datenbank (`daten/wissen.sqlite`, rund 365 MB, Schema 3) liegen nicht im Git.

```
werkzeuge/lade_bundesrecht.py     XML laden (gii-toc.xml, je Gesetz xml.zip; später nur Geändertes per ETag)
pruefki/wissen/gii.py             Parser gii-norm-XML: Metadaten, Normen, Gliederung, Klartext, Fußnoten
pruefki/wissen/index.py           baut daten/wissen.sqlite (gesetze, normen, normen_fts, namen, aliase, meta)
pruefki/wissen/abruf.py           norm(), suche(), existiert() und Kommandozeile
pruefki/wissen/synonyme.json      Suchwortschatz: Bürgersprache -> Amtssprache, Gesetzes-Hinweise, Kerngesetze
benchmark/fristen/normen_check.py prüft die Benchmark-Normen gegen die Wissensbasis -> normen_check.md
```

```sh
$PY werkzeuge/lade_bundesrecht.py                         # Rohdaten laden oder aktualisieren
$PY -m pruefki.wissen.index --neu                         # Datenbank komplett neu bauen (ca. 25 s)
$PY -m pruefki.wissen.index                               # nur geänderte Gesetze (stand.json, builddate)
$PY -m pruefki.wissen.abruf "§ 41 Abs. 2 VwVfG"           # Normtext mit Absatz, Quelle und Stand
$PY -m pruefki.wissen.abruf --suche "Bekanntgabe vierter Tag" --limit 5
$PY -m pruefki.wissen.abruf --existiert "§ 999 BGB"       # Prüfung auf erfundene Normen (Exit-Code 0/1)
$PY benchmark/fristen/normen_check.py
```

Gesetzesnamen gehen über eine Alias-Tabelle: amtliche und juris-Abkürzung, SGB I bis XIV römisch, arabisch und als
`Zehntes Buch Sozialgesetzbuch`, Jahreszahl weggelassen (`AO` = `AO 1977`), Einführungsgesetze (`EGBGB` = `BGBEG`),
Kurz- und Langtitel, auch gebeugt (`des Bürgerlichen Gesetzbuchs`). `VwVfG NRW` gilt als Landesrecht (unbekannt).
Zitate verstehen Parallelzitate (`§§ 41 VwVfG, 37 SGB X`), römische Absätze (`§ 41 II 1 VwVfG`) und Kleinschreibung.
`existiert()` prüft streng auch Absatz, Satz (Obergrenze aus den Satzenden) und Nummer (Listenmarken); `§ 30 EGAO`
(steht nur als `Art. 97 § 30 EGAO`) ist streng nicht vorhanden, nicht streng schon.

Text: Tabellenüberschriften stehen im Text, Trenner (`Split`, `ABWFORMAT`) als Leerzeichen. Redaktionelle
juris-Notizen (`(Fundstelle: ...)`) stehen bei den Fußnoten, nicht im Normtext; Platzhalter wie
`(Inhalt: nicht darstellbares Muster, ...)` bleiben im Text. Fußnoten einer Überschrift (Amtlicher Hinweis,
`(+++ Abschn. 5 ... +++)`) stehen als `Zu Abschnitt 5 ...: ...` bei jeder Norm darunter.

Suche (`suche()`): ODER über alle Suchwörter, Wortstamm als Präfix plus Synonyme aus `synonyme.json`, Rang nach BM25
(Titel x4, Abkürzung und Bezeichnung x3, Text und Wortteile x1) mal Faktoren: alle Wörter x2, alle bis auf eins x1,5
(ab 4 Wörtern), Kerngesetz x1,5, Gesetz mit Hinweis (`Jobcenter` -> SGB II, SGB X, SGG) x2, Anlage x0,5. Wortteile:
der Index kennt das Grundwort zusammengesetzter Substantive (`Berufungsfrist` -> `frist`). Schutz: höchstens 2000
Zeichen und 8 Wörter, Einzelzeichen fallen weg. Prüfmenge in Bürgersprache: 15 von 15 (vorher 4), eigene 18 von 18
(vorher 10), vorab zurückgelegte 16 von 20 (vorher 13) unter den ersten 5; warm im Median rund 25 ms.
`bewerten.py` nutzt die Wissensbasis für die Erfindungsquote, sobald `daten/wissen.sqlite` existiert (sonst nur die
Positivliste; `--nur-positivliste` erzwingt das alte Verfahren). Jede Normzeile trägt Quelle-URL und Stand.

Quelle und Lizenz: Bundesministerium der Justiz, www.gesetze-im-internet.de. Gesetze und Verordnungen sind amtliche
Werke ohne Urheberrechtsschutz (§ 5 Abs. 1 UrhG); die Daten dürfen nach § 4 Abs. 1 Datennutzungsgesetz (DNG) für
jeden Zweck genutzt werden. Maßgeblich bleibt die Verkündung im Bundesgesetzblatt.

## Was hier fehlt, mit Absicht

Der geheime Testteil bleibt geheim: frische Seeds, Holdout und die Vorlagen v2 (`vorlagen2.py`) sind nicht in diesem
Repo, damit Modelle sie nicht aus dem Training kennen. Öffentlich sind der Übungssatz `benchmark/fristen/aufgaben.jsonl`,
der Generator mit den Vorlagen v1, Rechner, Bewertung und die Ranglisten. Die Tests zu Vorlagen v2 werden hier
übersprungen.

## Lizenz

Code: MIT (`LICENSE`). Daten: CC BY 4.0 (`LICENSE-DATEN.md`).
