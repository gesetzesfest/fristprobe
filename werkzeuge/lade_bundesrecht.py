"""Lädt alle Bundesgesetze und -verordnungen als XML von gesetze-im-internet.de.

Quelle: https://www.gesetze-im-internet.de/gii-toc.xml (Inhaltsverzeichnis, je Norm ein xml.zip).
Nutzung frei nach § 4 Abs. 1 Datennutzungsgesetz, amtliche Werke nach § 5 UrhG.

Erster Lauf: alles laden. Spätere Läufe: nur geänderte Dateien (ETag / If-None-Match).
Nur Standardbibliothek. Aufruf:  python3.12 -I werkzeuge/lade_bundesrecht.py [--ziel daten/bund] [--pause 0.15]
"""

import argparse
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

TOC_URL = "https://www.gesetze-im-internet.de/gii-toc.xml"
USER_AGENT = "ki-labor-wissensbasis/0.1 (privates Forschungsprojekt)"


def hole(url, etag=None, timeout=60, versuche=4):
    """Gibt (status, body, etag) zurück. Status 304 = unverändert. Abgebrochene Übertragungen werden wiederholt."""
    for versuch in range(1, versuche + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if etag:
            req.add_header("If-None-Match", etag)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(), r.headers.get("ETag")
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return 304, b"", etag
            if e.code < 500 or versuch == versuche:
                raise
        except (http.client.IncompleteRead, urllib.error.URLError, TimeoutError, ConnectionError):
            if versuch == versuche:
                raise
        time.sleep(2 * versuch)


def sicher_entpacken(zip_pfad, ziel):
    """Entpackt nur flache, harmlose Namen (kein Pfad nach oben, keine absoluten Pfade)."""
    ziel.mkdir(parents=True, exist_ok=True)
    namen = []
    with zipfile.ZipFile(zip_pfad) as z:
        for info in z.infolist():
            name = PurePosixPath(info.filename)
            if info.is_dir() or name.is_absolute() or ".." in name.parts or len(name.parts) != 1:
                continue
            (ziel / name.name).write_bytes(z.read(info))
            namen.append(name.name)
    return namen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ziel", default="daten/bund")
    ap.add_argument("--pause", type=float, default=0.15, help="Sekunden zwischen Abrufen")
    ap.add_argument("--max", type=int, default=0, help="nur die ersten N (Test)")
    ap.add_argument("--nur-fehler", action="store_true", help="nur Normen erneut laden, die beim letzten Lauf fehlschlugen")
    args = ap.parse_args()

    ziel = Path(args.ziel)
    (ziel / "zip").mkdir(parents=True, exist_ok=True)
    (ziel / "xml").mkdir(parents=True, exist_ok=True)
    stand_pfad = ziel / "stand.json"
    stand = json.loads(stand_pfad.read_text("utf-8")) if stand_pfad.exists() else {}

    status, toc, _ = hole(TOC_URL)
    (ziel / "gii-toc.xml").write_bytes(toc)
    items = []
    for it in ET.fromstring(toc).iter("item"):
        link = (it.findtext("link") or "").strip()
        titel = " ".join((it.findtext("title") or "").split())
        kuerzel = link.rstrip("/").split("/")[-2] if link.endswith("/xml.zip") else None
        if kuerzel:
            items.append((kuerzel, titel, link.replace("http://", "https://", 1)))
    if args.nur_fehler:
        items = [it for it in items if "fehler" in stand.get(it[0], {})]
    if args.max:
        items = items[: args.max]

    neu = gleich = fehler = 0
    for i, (kuerzel, titel, url) in enumerate(items, 1):
        alt = stand.get(kuerzel, {})
        try:
            code, body, etag = hole(url, alt.get("etag"))
            if code == 304:
                gleich += 1
            else:
                zp = ziel / "zip" / f"{kuerzel}.zip"
                zp.write_bytes(body)
                dateien = sicher_entpacken(zp, ziel / "xml" / kuerzel)
                stand[kuerzel] = {
                    "titel": titel, "url": url, "etag": etag, "bytes": len(body), "dateien": dateien,
                    "geladen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                neu += 1
        except Exception as e:  # weiterlaufen, Fehler merken
            fehler += 1
            stand.setdefault(kuerzel, {})["fehler"] = f"{type(e).__name__}: {e}"
        if i % 250 == 0:
            stand_pfad.write_text(json.dumps(stand, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"{i}/{len(items)} neu {neu} gleich {gleich} fehler {fehler}", flush=True)
        time.sleep(args.pause)

    stand_pfad.write_text(json.dumps(stand, ensure_ascii=False, indent=0), encoding="utf-8")
    groesse = sum(v.get("bytes", 0) for v in stand.values())
    print(f"FERTIG {len(items)} Normen: neu {neu}, unverändert {gleich}, Fehler {fehler}, ZIP gesamt {groesse/1e6:.1f} MB")
    return 0 if fehler == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
