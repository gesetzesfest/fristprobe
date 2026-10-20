"""Geheime Seeds: Hash vorab, Seed erst bei Freigabe, jeder kann nachrechnen (benchmark/fristen/geheim.py)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "benchmark" / "fristen"))

import geheim as GH  # noqa: E402


class GeheimeSeeds(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ort = {"geheim": self.tmp / "geheim", "hashes": self.tmp / "geheim_hashes.json"}

    def test_hash_vorab_seed_erst_bei_freigabe(self):
        e = GH.neu("frisch-a", heute="2026-10-20", **self.ort)
        oeffentlich = self.ort["hashes"].read_text(encoding="utf-8")
        seed = json.loads((self.ort["geheim"] / "seeds.json").read_text(encoding="utf-8"))["frisch-a"]["seed"]
        self.assertNotIn(str(seed), oeffentlich)
        self.assertEqual(e["aufgaben"], len((self.ort["geheim"] / "frisch-a" / "aufgaben.jsonl").read_text(
            encoding="utf-8").splitlines()))
        self.assertEqual(GH.pruefe("frisch-a", hashes=self.ort["hashes"]), ["frisch-a ist noch geheim"])
        GH.freigeben("frisch-a", **self.ort)
        self.assertIn(str(seed), self.ort["hashes"].read_text(encoding="utf-8"))
        self.assertEqual(GH.pruefe("frisch-a", hashes=self.ort["hashes"]), [])

    def test_faelschung_faellt_auf(self):
        GH.neu("frisch-b", **self.ort)
        GH.freigeben("frisch-b", **self.ort)
        d = json.loads(self.ort["hashes"].read_text(encoding="utf-8"))
        d["frisch-b"]["seed"] += 1
        self.ort["hashes"].write_text(json.dumps(d), encoding="utf-8")
        self.assertEqual(len(GH.pruefe("frisch-b", hashes=self.ort["hashes"])), 2)

    def test_name_ohne_seed_und_einmalig(self):
        with self.assertRaises(SystemExit):
            GH.neu("Seed 123", **self.ort)
        GH.neu("frisch-c", **self.ort)
        with self.assertRaises(SystemExit):
            GH.neu("frisch-c", **self.ort)


if __name__ == "__main__":
    unittest.main()
