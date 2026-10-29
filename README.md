# Bose Home Assistant — stability fork

Custom integration for local control of Bose smart soundbars and speakers.

Forked from [cavefire/Bose-Homeassistant](https://github.com/cavefire/Bose-Homeassistant).
The original copyright and [GNU GPLv3 license](LICENSE) remain in effect.
Fork changes are maintained by [PUSCHi1337](https://github.com/PUSCHi1337),
dated 2026-10-28/29 and developed with AI assistance. This project is
unofficial and is not affiliated with Bose Corporation.

## Fix status

The integration uses the companion [pybose fork](https://github.com/PUSCHi1337/pybose).
Development changes cover discovery resource cleanup, coordinated reconnects,
entry-owned background tasks, bounded mDNS recovery and a stable client retained
by entities and callbacks after an IP-address change.

The current changes are in the [fork pull requests](https://github.com/PUSCHi1337/Bose-Homeassistant/pulls).
[Offline CI](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml)
runs simulated tests against Home Assistant 2026.10.4 with network sockets blocked.
These checks do not establish hardware compatibility, long-term stability or the
cause of a NAS hang. No live Home Assistant or real Bose device is used by CI.

No fork release has been published. Follow the exact commit and artifact in the
relevant PR; the default branch may still contain the original implementation.

## Installation and rollback

The tested candidate artifact contains `custom_components/bose`. Its manifest
pins the exact tested library source archive, so the integration and library
changes belong together. A plain `pip install pybose` does not install this fix.

Before a real installation, preserve the existing integration directory and take
a full Home Assistant backup. Replace only `custom_components/bose` with the
verified candidate, then restart Home Assistant after explicit approval.
A restart and real-device verification are separate from the offline CI results.

To roll back, restore the previous integration directory (or reinstall the
previous HACS version), restoring its original manifest requirement
`pybose==2026.10.2`, and restart Home Assistant. The fork library identifies itself
as a different version so the original requirement installs the original library
again. The candidate includes its source commit references and SHA-256 checksums.

## Setup and authentication

Add **Bose** through Settings → Devices & services. A Bose account is required to
obtain and refresh authentication tokens; device commands use the local network.
Never include credentials or tokens in code, screenshots or issue reports.

## Features and devices

The inherited implementation exposes power, volume, media information and
playback controls, source selection, audio/bass/surround settings, speaker groups,
Bluetooth settings and device-specific controls. Availability depends on the
speaker's advertised capabilities.

Inherited device reports cover Soundbar 500/700/900/Ultra, Home Speaker 300/500,
Music Amplifier and Portable Speaker. These are historical reports and do not
represent hardware tests of this fork.

![Entity preview](images/entities.jpg)
![Media player preview](images/media_player.jpg)

## Development and support

Discuss this fork's changes in the relevant
[pull request](https://github.com/PUSCHi1337/Bose-Homeassistant/pulls).
The test suite and dependency pins are under `tests/`; CI installs them only on
GitHub's runner. It never creates a second local or live Home Assistant instance.

## License

GNU GPLv3; see [LICENSE](LICENSE). The inherited history and notices are retained.
