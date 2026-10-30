# Candidate installation and rollback

This artifact is an offline-tested candidate, not a hardware-tested release.
Read SOURCE.json for both source commits and verify SHA256SUMS before use.

Installation is a separate, explicitly approved step:
1. Take a full Home Assistant backup and preserve the current custom_components/bose.
2. Copy only this ZIP's custom_components/bose into the HA configuration directory.
3. After approval, restart HA so its requirement manager installs the exact library
   archive declared in the candidate manifest.
4. Check startup errors, one-device connectivity, natural offline/reconnect behavior
   and task/resource stability before enabling any broader rollout.

Rollback:
1. Restore the preserved custom_components/bose directory, or reinstall HACS Bose 1.3.5.
2. Confirm that manifest.json again declares pybose==2026.10.2.
3. Restart HA after approval. The fork library has version 2026.10.2.post1; the
   original exact requirement therefore replaces it with 2026.10.2.
4. Verify the original integration starts. The full backup remains the fallback
   if the original source directory cannot be restored.

CI verifies package import, exact library provenance, and pip upgrade/downgrade on
a GitHub runner. It never installs this candidate on the user's HA or sends any
real speaker command. User-specific HA backups are not included in the artifact.
