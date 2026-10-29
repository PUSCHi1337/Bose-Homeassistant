"""Build a deterministic candidate; runs only on the GitHub Actions runner."""
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

root = Path(__file__).resolve().parents[1]
component = root / "custom_components" / "bose"
output = root / "dist"
output.mkdir(exist_ok=True)
manifest = json.loads((component / "manifest.json").read_text())
requirement = next(r for r in manifest["requirements"] if r.startswith("pybose @ "))
library_url = requirement.split(" @ ", 1)[1]
match = re.fullmatch(
    r"https://github.com/PUSCHi1337/pybose/archive/([a-f0-9]{40})\\.zip",
    library_url,
)
if match is None:
    raise SystemExit("The candidate must pin one immutable fork library archive")
source = {
    "integration_repository": "PUSCHi1337/Bose-Homeassistant",
    "integration_commit": os.environ["GITHUB_SHA"],
    "library_repository": "PUSCHi1337/pybose",
    "library_commit": match.group(1),
    "library_requirement": requirement,
    "integration_version": manifest["version"],
    "status": "offline-tested candidate; no hardware or live HA validation",
}
source_bytes = (json.dumps(source, indent=2) + "\n").encode()
rollback = (root / "ROLLBACK.md").read_bytes()
archive = output / "bose-stability-candidate.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as result:
    def write(name, data):
        info = zipfile.ZipInfo(name, date_time=(2026, 10, 29, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        result.writestr(info, data)

    for path in sorted(component.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            write(path.relative_to(root).as_posix(), path.read_bytes())
    write("custom_components/bose/LICENSE", (root / "LICENSE").read_bytes())
    write("custom_components/bose/FORK_SOURCE.json", source_bytes)
    write("SOURCE.json", source_bytes)
    write("ROLLBACK.md", rollback)
(output / "SOURCE.json").write_bytes(source_bytes)
(output / "ROLLBACK.md").write_bytes(rollback)
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n")
print(json.dumps({"archive": archive.name, "sha256": digest, **source}, indent=2))
