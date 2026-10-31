# Bose Home Assistant — stability fork

Custom integration for local control of Bose smart soundbars and speakers.

Forked from [cavefire/Bose-Homeassistant](https://github.com/cavefire/Bose-Homeassistant).
The original copyright and [GNU GPLv3 license](LICENSE) remain in effect.
Fork changes are maintained by [PUSCHi1337](https://github.com/PUSCHi1337),
dated 2026-10-28 through 2026-10-31 and developed with AI assistance.
This project is unofficial and is not affiliated with Bose Corporation.

## Current state

This fork contains the stability fixes and uses the companion
[pybose fork](https://github.com/PUSCHi1337/pybose). The integration manifest
pins an immutable library source commit; a plain `pip install pybose` does
not install these changes.

[![Offline integration tests](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml/badge.svg?branch=main)](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml)

The current source version is **1.3.6**. The fixes cover:

- Discovery browser cleanup, a shared connection handshake and bounded recovery.
- Entry-owned background tasks and the same client retained across address changes.
- IPv6 WebSocket addresses, typed local response timeouts and immediate connection notifications.
- Unavailability while offline, fresh reads after recovery and no repeated known-offline polls.
- Late accessory discovery once the speaker advertises the accessory status.
- Entry-owned Cast discovery and shutdown. Automatic startup/recovery never enable
  Chromecast or issue playback commands. The configured auto-enable option is
  used only by an explicit media-play request.
- Expected cancellation of an already stopped Cast connect is DEBUG for that
  owned socket only. Both the older device-prefixed template and the newer
  socket-logger template are recognized exactly; other errors, clients and
  global logging settings are preserved.

CI runs **125 integration tests** with both Home Assistant 2026.10.4's declared
Cast dependency (PyChromecast 14.0.10) and the manifest-resolved dependency.
It also runs **174 library tests with HA dependencies and two package checks**,
including a dependency downgrade/reinstall check. Tests block network sockets.
See [validation and known limits](VALIDATION.md) for exact source references
and the scope of the limited passive device checks.

Version **1.3.6** fixes the Cast cancellation message-format mismatch left in
[the first preview](https://github.com/PUSCHi1337/Bose-Homeassistant/releases/tag/v1.3.5.post7).
The change corrects diagnostic classification during an explicitly requested
shutdown; it does not make a powered-off speaker answer network requests.
Longer resource monitoring and broader device coverage remain open; see
[VALIDATION.md](VALIDATION.md).

## Installation and rollback

Use the [installation guide](INSTALL.md) to add this fork as a HACS custom
repository and select a published version, or install from its source ZIP.
Home Assistant installs the pinned companion library automatically. No separate
pybose installation is required.

Take a Home Assistant backup first. When replacing an existing Bose installation,
preserve its configuration entry and use only one `custom_components/bose`
directory. A planned HA restart is needed after changing the installed files.
See [ROLLBACK.md](ROLLBACK.md) for the return path.

CI artifacts remain development candidates with source references and SHA-256
checksums. The manual **Prepare release bundle** workflow builds these review
artifacts; it does not create tags, delete drafts, publish releases or upload to PyPI.

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
