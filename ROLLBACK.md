# Installation and rollback

The public preview has limited passive device checks and offline CI coverage;
see [VALIDATION.md](VALIDATION.md). Follow [INSTALL.md](INSTALL.md) for HACS
or manual installation. CI candidate artifacts also include SOURCE.json and
SHA256SUMS; verify those checksums before using a candidate.

Before installation:
1. Take a full Home Assistant backup and preserve the current `custom_components/bose`.
2. Record the currently installed integration version and its manifest requirement.
3. Keep the existing Bose configuration entry. Plan a short HA restart after
   replacing the files so the requirement manager can install the pinned library.

Rollback:
1. Restore the preserved `custom_components/bose` directory and its exact manifest.
   If the previous installation was upstream Bose 1.3.5, reinstall those files.
2. For upstream Bose 1.3.5, confirm that manifest.json again declares
   `pybose==2026.10.2`. For another saved version, restore its original requirement.
3. Restart HA. The fork library has version `2026.10.2.post2`; the original exact
   requirement therefore replaces it with `2026.10.2`.
4. Verify that the restored integration starts and its expected entities return.
   A full HA backup remains the fallback if the saved directory is unavailable.

CI verifies package imports, exact library provenance, and pip upgrade/downgrade
on a GitHub runner. It does not install files on a live HA instance or send real
speaker commands. Personal HA backups and authentication data are not part of
the public source or candidate artifacts.
