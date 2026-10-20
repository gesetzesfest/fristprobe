#!/usr/bin/env python3
"""Stufe-1-Messung: Token/s kalt und warm nach Dauerlast (Ollama, nur Standardbibliothek).

Je Modell:
  1. kalt: Modell entladen (keep_alive 0), dann eine Anfrage mit festem Prompt.
     Gemessen: Ladezeit, Prompt-Token/s, Ausgabe-Token/s.
  2. Dauerlast: N Minuten (Standard 15) Anfragen hintereinander. Zeigt, ob der
     Mac (MacBook Air ohne Lüfter) heiß wird und drosselt.
  3. warm: Median der Ausgabe-Token/s der letzten drei Anfragen der Dauerlast.
  4. Modell wieder entladen.

Ergebnis als Markdown-Tabelle auf dem Bildschirm und in benchmark/tempo-<datum>.md
(Rohdaten in benchmark/tempo-<datum>.json).

  python3 benchmark/tempo.py                         # Standardmodelle, 15 Minuten je Modell
  python3 benchmark/tempo.py --modelle qwen3:4b --minuten 2
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:11434"
STANDARD_MODELLE = ["gemma3:4b", "llama3.2:3b", "phi4-mini:latest", "qwen3:1.7b", "qwen3:4b", "qwen3:8b"]
DENK_FAMILIEN = ("qwen3", "gemma4", "deepseek-r1", "gpt-oss", "magistral", "qwq")
PROMPT = ("Erkläre in etwa 150 Wörtern auf Deutsch, wie man das Ende einer Widerspruchsfrist von einem Monat "
          "berechnet, wenn ein Bescheid am vierten Tag nach Aufgabe zur Post als bekannt gegeben gilt.")


def _post(host, pfad, body, timeout):
    req = urllib.request.Request(f"{host}{pfad}", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(host, pfad, timeout):
    with urllib.request.urlopen(f"{host}{pfad}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def entladen(host: str, modell: str, timeout: float = 60) -> bool:
    """keep_alive 0 entlädt das Modell; danach warten, bis /api/ps es nicht mehr zeigt."""
    try:
        _post(host, "/api/generate", {"model": modell, "keep_alive": 0}, timeout)
    except Exception:  # noqa: BLE001
        pass
    ende = time.monotonic() + 30
    while time.monotonic() < ende:
        try:
            geladen = {m.get("name") for m in _get(host, "/api/ps", 10).get("models", [])}
        except Exception:  # noqa: BLE001
            return False
        if modell not in geladen:
            return True
        time.sleep(1)
    return False


def anfrage(host: str, modell: str, args) -> dict:
    body = {"model": modell, "prompt": args.prompt, "stream": False, "keep_alive": "30m",
            "options": {"num_predict": args.num_predict, "temperature": 0, "seed": 42}}
    if modell.split("/")[-1].startswith(DENK_FAMILIEN):
        body["think"] = False
    t0 = time.monotonic()
    r = _post(host, "/api/generate", body, args.timeout)
    wand = time.monotonic() - t0

    def rate(n, d):
        return round(n / (d / 1e9), 2) if n and d else None

    return {"zeit": datetime.now().isoformat(timespec="seconds"), "wand_s": round(wand, 2),
            "load_s": round((r.get("load_duration") or 0) / 1e9, 2),
            "prompt_token_s": rate(r.get("prompt_eval_count"), r.get("prompt_eval_duration")),
            "token_s": rate(r.get("eval_count"), r.get("eval_duration")), "eval_count": r.get("eval_count")}


def miss_modell(host: str, modell: str, args) -> dict:
    erg = {"modell": modell, "kalt": None, "dauerlast": [], "warm_token_s": None, "fehler": None}
    try:
        erg["entladen_vorher"] = entladen(host, modell)
        erg["kalt"] = anfrage(host, modell, args)
        print(f"  kalt: {erg['kalt']['token_s']} Token/s, Ladezeit {erg['kalt']['load_s']} s", flush=True)
        ende = time.monotonic() + 60 * args.minuten
        while time.monotonic() < ende:
            try:
                m = anfrage(host, modell, args)
                erg["dauerlast"].append(m)
                print(f"  Dauerlast {len(erg['dauerlast'])}: {m['token_s']} Token/s", flush=True)
            except Exception as e:  # noqa: BLE001 - Dauerlast läuft weiter
                erg["dauerlast"].append({"zeit": datetime.now().isoformat(timespec="seconds"), "fehler": str(e)})
            if args.pause:
                time.sleep(args.pause)
        werte = [m["token_s"] for m in erg["dauerlast"] if m.get("token_s")]
        if werte:
            erg["warm_token_s"] = round(statistics.median(werte[-3:]), 2)
            erg["dauerlast_min"] = min(werte)
            erg["dauerlast_median"] = round(statistics.median(werte), 2)
        elif args.minuten == 0:
            erg["warm_token_s"] = erg["kalt"]["token_s"]
    except Exception as e:  # noqa: BLE001
        erg["fehler"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        erg["entladen_nachher"] = entladen(host, modell)
    return erg


def tabelle(ergebnisse: list[dict], minuten: float) -> str:
    z = [f"| Modell | Ladezeit kalt (s) | Token/s kalt | Token/s warm nach {minuten:g} min | Veränderung | "
         f"Prompt-Token/s kalt | Anfragen Dauerlast | Fehler |",
         "|---|---|---|---|---|---|---|---|"]
    for e in ergebnisse:
        k = e.get("kalt") or {}
        kalt, warm = k.get("token_s"), e.get("warm_token_s")
        veraend = f"{100 * (warm - kalt) / kalt:+.0f} %" if kalt and warm else "—"
        z.append(f"| {e['modell']} | {k.get('load_s', '—')} | {kalt or '—'} | {warm or '—'} | {veraend} | "
                 f"{k.get('prompt_token_s') or '—'} | {len(e.get('dauerlast', []))} | {e.get('fehler') or ''} |")
    return "\n".join(z)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Token/s kalt und warm nach Dauerlast messen (Ollama)")
    ap.add_argument("--modelle", nargs="+", default=STANDARD_MODELLE)
    ap.add_argument("--minuten", type=float, default=15)
    ap.add_argument("--num-predict", type=int, default=256)
    ap.add_argument("--pause", type=float, default=0, help="Sekunden Pause zwischen Anfragen der Dauerlast")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--ausgabe", type=Path, default=HIER / f"tempo-{date.today().isoformat()}")
    args = ap.parse_args(argv)
    try:
        vorhanden = {m.get("name") for m in _get(args.host, "/api/tags", 10).get("models", [])}
    except Exception:  # noqa: BLE001
        print(f"Ollama unter {args.host} nicht erreichbar. Läuft 'ollama serve'?", file=sys.stderr)
        return 2
    ergebnisse = []
    for m in args.modelle:
        if m not in vorhanden:
            print(f"- {m}: nicht installiert, übersprungen", file=sys.stderr)
            continue
        print(f"- {m}", flush=True)
        ergebnisse.append(miss_modell(args.host, m, args))
    md = (f"# Tempo-Messung Stufe 1 ({date.today().isoformat()})\n\n"
          f"Prompt fest, num_predict {args.num_predict}, Temperatur 0, Denkmodus aus.\n\n"
          + tabelle(ergebnisse, args.minuten))
    args.ausgabe.with_suffix(".md").write_text(md + "\n", encoding="utf-8")
    args.ausgabe.with_suffix(".json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
