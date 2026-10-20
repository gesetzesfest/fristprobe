# Offene Punkte für Fachleute (Fristen-Benchmark v1)

Stand 14.10.2026. Diese Konstellationen sind **nicht** in den 50 Aufgaben enthalten oder beruhen auf einer Annahme.
Bitte durch eine Juristin oder einen Juristen gegenlesen lassen, bevor der Benchmark veröffentlicht wird.

## 1. Strittige Konstellationen (bewusst ausgelassen)

Der Rechner markiert sie mit `strittig=True`, der Generator verwirft sie.

| Regel | Konstellation | Warum ausgelassen |
|---|---|---|
| MI-05 | Mietkündigung: dritter Werktag fällt auf einen Samstag, Zugang am folgenden Werktag | BGH VIII ZR 206/04 hat offen gelassen, ob § 193 BGB die Karenzzeit verlängert; LG Berlin 65 S 395/16 bejaht. Beispiel: April 2026, Zugang Di 07.04.2026 (Dienstag nach Ostern). |
| MI-08 | Vermieterstaffel mit früherer Überlassung aus anderem Rechtsgrund | Anrechnung umstritten; Aufgaben nennen nur ein klares Überlassungsdatum. |
| B-05 | VwVfG: vierter Tag nach Aufgabe zur Post fällt auf Samstag, Sonntag oder Feiertag | Überwiegend keine Verschiebung, Gegenansicht in der Literatur, kein BVerwG. Alle VwVfG-Briefaufgaben haben einen Werktag als Fiktionstag. |
| B-03 | Einschreiben nach § 4 VwZG im Bereich der AO am Wochenende | Nur Verwaltungsanweisung; Einschreiben kommen nicht vor. |
| G-02 | Feiertag am Sitz der Behörde, wenn Wohnort in einem anderen Land liegt | Nur Verwaltungsauffassung; Behörde, Wohnort und Gericht liegen immer im selben Land. |
| G-03 | AO-Fiktion: Feiertag am Ort des Empfängers vs. Behördensitz | Nur Verwaltungsanweisungen von 2004; gleiches Land wie oben. |
| A-11 | Bestreiten des Zugangs (BVerwG vs. BFH) | Zugangsdaten sind in allen Aufgaben unstreitig. |

## 2. Annahmen, die gegengelesen werden sollten

1. **Feiertagstabelle** (`pruefki/fristen/feiertage.py`) ist aus Fachwissen gebaut und nur in Einzelpunkten gegen die
   Landesgesetze geprüft (Stand 14.10.2026, über umwelt-online.de, nicht amtlich): einmalige Berliner Feiertage
   08.05.2025 und 17.06.2028 (GVBl. Berlin 2024 S. 460; 08.05.2020 durch eigenes Gesetz), Hessen (§ 1 Abs. 1
   HFeiertagsG: „die Sonntage sowie …“, Oster- und Pfingstsonntag nicht eigens genannt; nur § 2 Abs. 1 FTG BB nennt
   sie, ohne Wirkung auf Werktage), Thüringen (§ 2 ThürFGtG, Weltkindertag, Fronleichnam nur per Verordnung für
   einzelne Gemeinden). Übrige Länder nicht geprüft (die Feiertags-Recherche wurde nicht gestartet). Besonders prüfen:
   Reformationstag in HB, HH, NI, SH seit 2018; Frauentag BE seit 2019 und MV seit 2023. Teil-Feiertage nur per Option
   `gemeinde` (Mariä Himmelfahrt BY, Fronleichnam SN/TH, Friedensfest Augsburg). 24.12. und 31.12. gelten als Werktage
   (nicht belegt). Die Tabelle reicht von 2020 bis 2030; der Rechner bricht nur ab, wenn Feiertage außerhalb davon das
   Datum bestimmen könnten (reine Hinweise im Rechenweg nennen dort nur Samstag und Sonntag).
2. **Vier-Tage-Fiktion für VwVfG und SGB X ab 01.01.2025** (A-09: keine eigene Übergangsnorm, Arbeitsannahme). Alle
   Aufgaben haben ein Aufgabedatum nach dem 31.12.2024.
3. **Jahresfrist bei fehlender Rechtsbehelfsbelehrung** (E-01 bis E-03): Ob das Ende der Jahresfrist auf den nächsten
   Werktag verschoben wird, ist in den Belegen nicht eigens geprüft. Die Aufgaben sind so gewählt, dass das Jahresende
   auf einen Werktag fällt. VwGO und SGG nur mit Postzustellungsurkunde („seit Zustellung“ wörtlich).
4. **§ 66 SGG beim Widerspruch**: Die Jahresfrist für den Widerspruch ohne Belehrung folgt aus § 84 Abs. 2 Satz 3 SGG
   (Verweis auf § 66 SGG). Dieser Verweis steht nicht in recht/belege.json (betrifft eine Prüfaufgabe).
5. **Widerspruchsfrist VwGO**: Verschiebung nach § 57 Abs. 2 VwGO i. V. m. § 222 Abs. 2 ZPO; § 31 Abs. 3 VwVfG führt
   zum selben Ergebnis (R-01, Lehrmaterial). Die Aufgaben nennen nur erfundene Bundesbehörden (Landes-VwVfG nicht geprüft, A-14).
   Beim Widerspruch nach SGG gelten § 64 Abs. 3 SGG und § 26 Abs. 3 SGB X gleichwertig. Bei den **Klagefristen**
   (§ 74 VwGO, § 87 SGG) zählen nur § 57 Abs. 2 VwGO / § 222 Abs. 2 ZPO bzw. § 64 Abs. 3 SGG als Pflichtnorm:
   VwVfG und SGB X gelten nicht für das gerichtliche Verfahren (§ 1 Abs. 1 VwVfG, § 1 Abs. 1 SGB X).
6. **Mietrecht**: Feiertage des Landes, in dem die Wohnung liegt (MI-03 offen). Vermieterstaffel: Stichtag Zugang, volle
   Jahre ab Überlassung nach § 187 Abs. 2, § 188 Abs. 2 BGB (MI-07 nicht belegt); der Generator nimmt nur Fälle, in denen
   der fünfte oder achte Jahrestag nicht im Zugangsmonat liegt.
7. **Arbeitsrecht**: „zum 15.“ = Ablauf des 15. (AR-01 offen). Rechenketten AR-01 und AR-04 sind in den Tests gegen eine
   zweite, unabhängig geschriebene Implementierung geprüft (alle Tage 2025 bis 2027). Betriebszugehörigkeit nach vollen
   Jahren bis zum Zugang (AR-02, Ableitung). Probezeitfälle nur in unbefristeten Verträgen.
8. **Zugang am Samstag** (§ 130 BGB, Kündigungen) nur bei persönlicher Übergabe (KSchG-Aufgabe mit Botenprotokoll);
   ein Briefkasteneinwurf am Samstag als Zugang nach § 130 BGB kommt nicht vor (ZU-01 offen). Anders die
   **förmliche Zustellung**: Bei der Postzustellungsurkunde gilt das Schriftstück mit der Einlegung in den Briefkasten
   als zugestellt, auch an einem Samstag (§ 180 Satz 2 ZPO i. V. m. § 3 Abs. 2 VwZG, C-02; Fristbeginn trotzdem am
   Folgetag, FR-12). Solche Fälle kommen vor (z. B. F024: Einlegung Sa 06.12.2025).
9. **Prüfaufgaben**: Das zu prüfende Datum steht in einem Vermerk Dritter (Beratung, Kanzlei, Betriebsrat, Hausverwaltung),
   nie in der Rechtsbehelfsbelehrung selbst. Sonst wäre eine falsche Datumsangabe in der Belehrung eine unrichtige
   Belehrung mit Jahresfrist (§ 58 Abs. 2 VwGO) und die Aufgabe nicht mehr eindeutig.
10. **SGB X: Fiktionstag am Wochenende** wird nicht verschoben (B-04). Das stützt sich auf BSG 06.05.2010 –
    B 14 AS 12/09 R (Drei-Tage-Fassung; § 37 Abs. 2 SGB X regelt einen Zeitpunkt, keine Frist, § 26 Abs. 3 SGB X
    weder direkt noch analog; bewusste Abgrenzung zu BFH IX R 68/98) und LSG Bayern L 2 U 140/13. Inhalt am
    14.10.2026 über urteile-gesetze.de nachgelesen, nicht im amtlichen Volltext. Für die Vier-Tage-Fassung gibt es keine
    Entscheidung; die Übertragung ist eine Annahme. Für die AO hat der Gesetzgeber die BFH-Linie ausdrücklich
    fortgelten lassen (B-02), für das SGB X nichts geregelt. Betroffen: F001, F005, F022, F027, F035, F040. Nach der
    Gegenansicht (Verschiebung wie § 108 Abs. 3 AO) änderten sich F005, F022 und F035.
11. **KSchG-Klagefrist am Wochenende**: Ob § 4 KSchG eine prozessuale oder materiell-rechtliche Frist ist, ist
    umstritten. Praxis und Kommentare nennen für die Verschiebung § 222 Abs. 2 ZPO und § 193 BGB nebeneinander; beide
    führen zum selben Tag und zählen in `normen_pflicht` gleichwertig. Die Aussage in KS-03 („§ 222 Abs. 2 ZPO ersetzt
    § 193 BGB“) ist nur für Prozessfristen allgemein belegt (BGH AnwZ (Brfg) 7/11), nicht für § 4 KSchG.
12. **§ 188 Abs. 3 BGB bei Fristen ab Tagesbeginn**: Probezeit ab dem 29., 30. oder 31. und Jahresfristen ab dem 29.02.
    enden mit Ablauf des Monatsletzten (wie beim Lebensalter: Geburtstag 29.02. vollendet das Jahr mit Ablauf des
    28.02.). Der Rechner rechnet so, markiert die Fälle aber als unsicher (nicht gesondert belegt, FR-06); sie tragen
    keinen Sollwert.
13. **Gleiche falsche Daten aus verschiedenen Fehlern**: Bei einfachem Brief im VwVfG und SGB X führen „alte
    Drei-Tage-Fiktion“ und „Ereignistag mitgezählt“ immer zum selben Datum, bei der AO „Fiktionstag nicht verschoben“
    und „Ereignistag mitgezählt“, wenn der Fiktionstag ein Sonntag ist. Befund-Aufgaben tragen dann alle passenden
    Fallen-Labels (z. B. F018, F038); eine Auswertung nach Fallen muss das berücksichtigen.
14. **Rückfragen**: (a) Bescheiddatum ohne Postausgangsvermerk genügt nicht für die Fiktion (A-10); (b) Mietkündigung ohne
    Zugangsdatum, Schreiben vor dem dritten Werktag datiert; (c) Arbeitgeberkündigung ohne Eintrittsdatum.

## 3. Für spätere Klassen (nicht in v1)

Aus den offenen Punkten der Recherche: Fristverlängerung (§ 190 BGB, § 224 Abs. 3 ZPO), § 167 ZPO bei der Klagefrist,
formunwirksame Kündigung und Klagefrist, Einschreiben nach § 4 VwZG, elektronischer Abruf (§ 41 Abs. 2a VwVfG,
§ 122a AO), Bekanntgabe im Ausland (§ 122 Abs. 2 Nr. 2 AO, § 84 Abs. 1 S. 2 SGG), Sonderkündigungsschutz
(§ 4 Satz 4 KSchG), nachträgliche Zulassung (§ 5 KSchG), Wiedereinsetzung, Verjährung, Widerrufsfristen, Gewerberaum
(§ 580a BGB), Landes-VwVfG.

## 4. Quellenqualität

Die Gesetzeszitate in recht/belege.json sind teils aus Zusammenfassungen; ein wörtlicher Abgleich mit
gesetze-im-internet.de steht aus. Einige Urteile sind nur über Datenbankwiedergaben belegt (siehe offene_punkte in
recht/belege.json).
