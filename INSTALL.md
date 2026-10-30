# Install the public preview

Preview: [v1.3.5.post7](https://github.com/PUSCHi1337/Bose-Homeassistant/releases/tag/v1.3.5.post7).
The declared minimum Home Assistant version is **2026.10.4**, which is also the
version used in CI. Read [VALIDATION.md](VALIDATION.md) for test coverage and
remaining limits before installing.

Take a full Home Assistant backup and preserve the existing
`custom_components/bose` directory. Both this fork and the original integration
use the domain `bose`; they cannot be installed side by side. When upgrading an
existing installation, keep its Bose entry under **Settings → Devices & services**.

## HACS custom repository

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/PUSCHi1337/Bose-Homeassistant` with type **Integration**.
3. Open **Bose stability fork**. In its download/redownload version selector,
   enable **Show beta versions** if the preview is hidden, then select
   **v1.3.5.post7**.
4. Download the selected version and restart Home Assistant at a suitable time.
5. For a new installation, add **Bose** under **Settings → Devices & services**.
   For an upgrade, keep the existing entry and check its entities and logs.

HACS installs the integration from the tagged repository's
`custom_components/bose` directory. No separate release ZIP asset or pybose
installation is needed. This repository is offered as a custom repository;
it has not been submitted to the default HACS catalog.

If HACS already manages another Bose repository, avoid competing update sources
for the same directory. If it refuses the fork, use the manual method below and
resolve the old repository's HACS tracking before accepting future HACS updates.

HACS versions differ in their beta controls. Its optional per-repository
pre-release switch controls whether beta versions are considered for update
notifications; selecting a preview for download is a separate step.
See the official [custom repository guide](https://hacs.dev/docs/faq/custom_repositories/),
[integration layout guide](https://hacs.dev/docs/publish/integration/) and
[pre-release update switch documentation](https://www.hacs.dev/docs/use/entities/switch/).

## Manual installation

1. Open the [v1.3.5.post7 release](https://github.com/PUSCHi1337/Bose-Homeassistant/releases/tag/v1.3.5.post7)
   and download **Source code (zip)**.
2. Extract it. Inside the top-level repository folder, locate
   `custom_components/bose`.
3. With the previous directory safely backed up, replace only
   `<HA configuration directory>/custom_components/bose` with that complete
   directory. Do not copy the repository's top-level folder into
   `custom_components`, and ensure the installed manifest is directly at
   `custom_components/bose/manifest.json`.
4. Keep the downloaded source and its `LICENSE` for reference.
5. Restart Home Assistant, then follow step 5 of the HACS instructions above.

The manifest pins pybose source commit
`bfcce6fc33a6a174484acd09ba0f30c1513843a0` (package **2026.10.2.post2**).
Home Assistant downloads it automatically through its requirement manager.
A plain `pip install pybose` installs a different distribution and is not the
installation method for this fork.

## Check and return

Check the loaded integration version, expected entity availability and fresh
startup logs. An offline speaker should be unavailable. Accessories may remain
unavailable after a standby restart until the speaker advertises them.
No power-cycle or playback test is required to install this preview.

See [ROLLBACK.md](ROLLBACK.md) to restore the previous files and dependency.
