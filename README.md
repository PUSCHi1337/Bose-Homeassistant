# Bose Home Assistant — stability fork

Custom integration for local control of Bose smart soundbars and speakers.

Forked from [cavefire/Bose-Homeassistant](https://github.com/cavefire/Bose-Homeassistant).
The original copyright and [GNU GPLv3 license](LICENSE) remain in effect.
Fork changes are maintained by [PUSCHi1337](https://github.com/PUSCHi1337),
dated 2026-10-28 through 2026-10-30 and developed with AI assistance.
This project is unofficial and is not affiliated with Bose Corporation.

## Current state

This fork contains the stability fixes and uses the companion
[pybose fork](https://github.com/PUSCHi1337/pybose). The integration manifest
pins an immutable library source commit; a plain `pip install pybose` does
not install these changes.

[![Offline integration tests](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml/badge.svg?branch=main)](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml)

The current runtime version is **1.3.5.post7**. The fixes cover:

- Discovery browser cleanup, a shared connection handshake and bounded recovery.
- Entry-owned background tasks and the same client retained across address changes.
- IPv6 WebSocket addresses, typed local response timeouts and immediate connection notifications.
- Unavailability while offline, fresh reads after recovery and no repeated known-offline polls.
- Late accessory discovery once the speaker advertises the accessory status.
- Entry-owned Cast discovery and shutdown. Automatic startup/recovery never enable
  Chromecast or issue playback commands. The configured auto-enable option is
  used only by an explicit media-play request.
- The exact diagnostic from an already stopped Cast connect is DEBUG for that
  owned socket only; other errors, clients and global logging settings are preserved.

The baseline has **112 integration tests, 174 library tests with HA dependencies
and two package checks**, including a dependency downgrade/reinstall check.
CI uses Home Assistant 2026.10.4 and blocks network sockets in tests.
See [validation and known limits](VALIDATION.md) for exact source references
and the scope of the limited passive device checks.

No public fork release is available yet. The protected `main` branch contains the
development source; use a successful CI candidate when testing before release.

## Installation and rollback

The successful [Offline integration tests workflow](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml)
provides a `bose-stability-candidate` artifact containing the installable ZIP,
source references, SHA-256 checksums and rollback instructions. It is a test
candidate, not a stable release. GitHub may require sign-in to download artifacts.

Preserve the existing integration directory and take a Home Assistant backup.
Verify the artifact checksum, then replace only `custom_components/bose`.
The paired library is installed through its manifest requirement. Restart
Home Assistant when the short outage is acceptable and verify the entity states
and logs. See [ROLLBACK.md](ROLLBACK.md) for the full return path.

To return to the original dependency, restore the previous integration and its
manifest requirement `pybose==2026.10.2`, then restart Home Assistant.
The fork library has a distinct version so HA can reinstall the original library.

The manual **Prepare release bundle** workflow only builds review artifacts.
It does not create tags, delete drafts, publish releases or upload to PyPI.

## Setup and authentication

Add **Bose** through Settings → Devices & services. A Bose account is required
to obtain and refresh authentication tokens; device commands use the local network.
Keep credentials and tokens in the local HA configuration, never in source,
screenshots or public reports.

## Features and devices

The inherited implementation exposes power, volume, media information and playback,
source selection, audio/bass/surround settings, speaker groups, Bluetooth settings
and device-specific controls. Availability depends on advertised capabilities.

Inherited device reports cover Soundbar 500/700/900/Ultra, Home Speaker 300/500,
Music Amplifier and Portable Speaker. These historical reports are not a
compatibility guarantee for this fork.

![Entity preview](images/entities.jpg)
![Media player preview](images/media_player.jpg)

## Development and support

Changes and discussion are tracked in the [fork pull requests](https://github.com/PUSCHi1337/Bose-Homeassistant/pulls).
Tests and their dependencies run on GitHub's runners; no second live HA instance
is started by CI. See [VALIDATION.md](VALIDATION.md) before broadening test claims.

## License

GNU GPLv3; see [LICENSE](LICENSE). The inherited history and notices are retained.
