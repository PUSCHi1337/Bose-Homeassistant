"""Verify the installable ZIP using the real HA imports; no instance is started."""
import hashlib
import importlib
from importlib.metadata import distribution, version
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "dist" / "bose-stability-candidate.zip"


def test_candidate_checksum_and_immutable_library_source():
    recorded = (ROOT / "dist" / "SHA256SUMS").read_text().split()[0]
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == recorded
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert all(not name.startswith("/") and ".." not in Path(name).parts
                   for name in names)
        manifest = json.loads(archive.read("custom_components/bose/manifest.json"))
        source = json.loads(archive.read("SOURCE.json"))
        assert re.fullmatch("[a-f0-9]{40}", source["integration_commit"])
        assert re.fullmatch("[a-f0-9]{40}", source["library_commit"])
        requirement = "pybose @ https://github.com/PUSCHi1337/pybose/archive/" + source["library_commit"] + ".zip"
        assert requirement in manifest["requirements"]
        direct = json.loads(distribution("pybose").read_text("direct_url.json"))
        assert direct["url"] == requirement.split(" @ ", 1)[1]
        assert version("pybose") == "2026.10.2.post2"
        assert archive.read("custom_components/bose/LICENSE") == (ROOT / "LICENSE").read_bytes()
        assert "ROLLBACK.md" in names
        assert archive.read("VALIDATION.md") == (ROOT / "VALIDATION.md").read_bytes()


def test_all_packaged_platforms_import_against_pinned_library(tmp_path, monkeypatch):
    with zipfile.ZipFile(ARCHIVE) as archive:
        archive.extractall(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    for platform in ("", "config_flow", "coordinator", "entity", "media_player",
                     "number", "select", "switch", "sensor", "binary_sensor", "button"):
        suffix = "." + platform if platform else ""
        module = importlib.import_module("custom_components.bose" + suffix)
        assert str(tmp_path) in module.__file__
    from pybose.BoseSpeaker import BoseSpeaker
    assert callable(BoseSpeaker.reconnect)
