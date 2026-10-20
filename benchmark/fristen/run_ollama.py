#!/usr/bin/env python3
"""Lässt lokale Ollama-Modelle die Fristen-Aufgaben lösen (nur Standardbibliothek).

Ruft http://127.0.0.1:11434/api/chat (stream false, format json, think aus) und
schreibt je Antwort eine Zeile nach
benchmark/fristen/ergebnisse/<datum>-<modell>.jsonl.

Beispiele:
  python3 benchmark/fristen/run_ollama.py                       # Standardmodelle, 3 Läufe
  python3 benchmark/fristen/run_ollama.py --modelle qwen3:4b --think
  python3 benchmark/fristen/run_ollama.py --split oeffentlich --laeufe 1 --ids F001 F002

Bereits vorhandene Zeilen (gleiches Modell, gleiche Aufgabe, gleicher Lauf) werden
übersprungen, ein abgebrochener Lauf kann also einfach neu gestartet werden.
"""

from __future__ import annotations

import argparse
import json
import socket
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import prompt as P  # noqa: E402

STANDARD_MODELLE = ["gemma3:4b", "llama3.2:3b", "phi4-mini:latest", "qwen3:1.7b", "qwen3:4b", "qwen3:8b"]
DENK_FAMILIEN = ("qwen3", "gemma4", "deepseek-r1", "gpt-oss", "magistral", "qwq")
HOST = "http://127.0.0.1:11434"


def dateiname(modell: str) -> str:
    return modell.replace("/", "-").replace(":", "-")


def denkfaehig(modell: str) -> bool:
    return modell.split("/")[-1].startswith(DENK_FAMILIEN)


def _post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(host: str, modell: str, nachrichten: list, *, think: bool, timeout: float, optionen: dict,
         format_="json", keep_alive="10m") -> dict:
    body = {"model": modell, "messages": nachrichten, "stream": False, "format": format_,
            "options": optionen, "keep_alive": keep_alive}
    if think or denkfaehig(modell):
        body["think"] = bool(think)
    try:
        return _post(f"{host}/api/chat", body, timeout)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        if "think" in body and "think" in text.lower():
            body.pop("think")  # Modell kennt den Schalter nicht: ohne ihn wiederholen
            return _post(f"{host}/api/chat", body, timeout)
        raise RuntimeError(f"HTTP {e.code}: {text[:300]}") from None


def token_pro_s(antwort: dict) -> float | None:
    n, dauer = antwort.get("eval_count"), antwort.get("eval_duration")
    if n and dauer:
        return round(n / (dauer / 1e9), 2)
    return None


def lade_aufgaben(pfad: Path, split: str, ids: list[str] | None, limit: int | None) -> list[dict]:
    with open(pfad, encoding="utf-8") as fh:
        aufgaben = [json.loads(z) for z in fh if z.strip()]
    if split != "alle":
        aufgaben = [a for a in aufgaben if a["split"] == split]
    if ids:
        aufgaben = [a for a in aufgaben if a["id"] in set(ids)]
    return aufgaben[:limit] if limit else aufgaben


def schon_da(pfad: Path) -> set[tuple[str, int]]:
    fertig = set()
    if pfad.exists():
        with open(pfad, encoding="utf-8") as fh:
            for z in fh:
                try:
                    d = json.loads(z)
                except json.JSONDecodeError:
                    continue
                if not d.get("fehler"):
                    fertig.add((d["id"], d["lauf"]))
    return fertig


def verfuegbare_modelle(host: str, timeout: float = 10) -> set[str] | None:
    try:
        tags = _get(f"{host}/api/tags", timeout)
    except Exception:  # noqa: BLE001 - Server nicht erreichbar
        return None
    return {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}


def laufe_modell(modell: str, aufgaben: list[dict], args, ausgabe_dir: Path, datum: str) -> dict:
    pfad = ausgabe_dir / f"{datum}-{dateiname(modell)}.jsonl"
    fertig = schon_da(pfad)
    optionen = {"num_ctx": args.num_ctx}
    if args.temperatur is not None:
        optionen["temperature"] = args.temperatur
    if args.seed is not None:
        optionen["seed"] = args.seed
    zaehler = {"ok": 0, "fehler": 0, "uebersprungen": 0}
    tps = []
    verbindungsfehler_folge = 0
    with open(pfad, "a", encoding="utf-8") as out:
        for lauf in range(1, args.laeufe + 1):
            for a in aufgaben:
                if (a["id"], lauf) in fertig:
                    zaehler["uebersprungen"] += 1
                    continue
                zeile = {"modell": modell, "id": a["id"], "lauf": lauf, "split": a["split"], "typ": a["typ"],
                         "zeit": datetime.now().isoformat(timespec="seconds"), "quelle": "ollama",
                         "prompt_version": P.PROMPT_VERSION, "prompt_hash": P.prompt_hash(),
                         "think": bool(args.think), "optionen": optionen}
                t0 = time.monotonic()
                try:
                    r = chat(args.host, modell, P.nachrichten(a), think=args.think, timeout=args.timeout,
                             optionen=optionen, keep_alive=args.keep_alive)
                    msg = r.get("message", {}) or {}
                    zeile.update(
                        antwort=msg.get("content", ""), denken=(msg.get("thinking") or "")[:4000] or None,
                        antwort_json=P.lies_antwort(msg.get("content", "")),
                        eval_count=r.get("eval_count"), eval_duration=r.get("eval_duration"),
                        load_duration=r.get("load_duration"), prompt_eval_count=r.get("prompt_eval_count"),
                        prompt_eval_duration=r.get("prompt_eval_duration"), total_duration=r.get("total_duration"),
                        tokens_pro_s=token_pro_s(r), fehler=None)
                    verbindungsfehler_folge = 0
                    zaehler["ok"] += 1
                    if zeile["tokens_pro_s"]:
                        tps.append(zeile["tokens_pro_s"])
                except (socket.timeout, TimeoutError):
                    zeile.update(antwort=None, antwort_json=None, fehler=f"Zeitüberschreitung nach {args.timeout} s")
                    zaehler["fehler"] += 1
                except urllib.error.URLError as e:
                    zeile.update(antwort=None, antwort_json=None, fehler=f"Verbindung: {e.reason}")
                    zaehler["fehler"] += 1
                    verbindungsfehler_folge += 1
                except Exception as e:  # noqa: BLE001 - robust weiterlaufen
                    zeile.update(antwort=None, antwort_json=None, fehler=f"{type(e).__name__}: {e}"[:400])
                    zaehler["fehler"] += 1
                zeile["dauer_s"] = round(time.monotonic() - t0, 2)
                out.write(json.dumps(zeile, ensure_ascii=False) + "\n")
                out.flush()
                status = "ok" if not zeile["fehler"] else zeile["fehler"]
                print(f"  {modell} Lauf {lauf} {a['id']}: {status} ({zeile['dauer_s']} s)", flush=True)
                if verbindungsfehler_folge >= 5:
                    print("  Fünf Verbindungsfehler hintereinander: Abbruch dieses Modells.", flush=True)
                    return {"datei": str(pfad), **zaehler, "abbruch": True}
    median = statistics.median(tps) if tps else None
    return {"datei": str(pfad), **zaehler, "tokens_pro_s_median": median}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fristen-Benchmark mit lokalen Ollama-Modellen")
    ap.add_argument("--modelle", nargs="+", default=STANDARD_MODELLE)
    ap.add_argument("--laeufe", type=int, default=3)
    ap.add_argument("--think", action="store_true", help="Denkmodus einschalten (z. B. qwen3)")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--temperatur", type=float, default=None, help="Standard: Voreinstellung des Modells")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--keep-alive", default="10m")
    ap.add_argument("--split", choices=["alle", "oeffentlich", "privat"], default="alle")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--aufgaben", type=Path, default=HIER / "aufgaben.jsonl")
    ap.add_argument("--ausgabe-dir", type=Path, default=HIER / "ergebnisse")
    ap.add_argument("--datum", default=date.today().isoformat())
    args = ap.parse_args(argv)

    aufgaben = lade_aufgaben(args.aufgaben, args.split, args.ids, args.limit)
    args.ausgabe_dir.mkdir(parents=True, exist_ok=True)
    vorhanden = verfuegbare_modelle(args.host)
    if vorhanden is None:
        print(f"Ollama unter {args.host} nicht erreichbar. Läuft 'ollama serve'?", file=sys.stderr)
        return 2
    print(f"{len(aufgaben)} Aufgaben, {args.laeufe} Läufe, Modelle: {', '.join(args.modelle)}")
    bericht = {}
    for m in args.modelle:
        if m not in vorhanden:
            print(f"- {m}: nicht installiert (ollama pull {m}), übersprungen", file=sys.stderr)
            bericht[m] = {"fehlt": True}
            continue
        print(f"- {m}")
        bericht[m] = laufe_modell(m, aufgaben, args, args.ausgabe_dir, args.datum)
    print(json.dumps(bericht, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
