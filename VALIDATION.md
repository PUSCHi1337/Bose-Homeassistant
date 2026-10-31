# Validation and remaining limits

## Version 1.3.6

Integration **1.3.6** changes the owned Cast shutdown logger from the
[post7 baseline](https://github.com/PUSCHi1337/Bose-Homeassistant/releases/tag/v1.3.5.post7).
The immutable pybose source remains
`bfcce6fc33a6a174484acd09ba0f30c1513843a0` (package **2026.10.2.post2**).
No Bose request, entity ID, power-switch dependency or playback behavior is added.

PyChromecast 14.0.10, declared by Home Assistant 2026.10.4's Cast integration,
includes the device prefix in its stopped-connect message template.
PyChromecast 14.1.0 adds that prefix through its socket logger instead.
Post7 only recognized the latter template. The adapter now recognizes both
exact templates, and only for the integration-owned client after its stop event
is set. Other errors, warnings, unstopped clients, unrelated Cast clients and
global logger settings retain their behavior. A TCP timeout itself remains
possible when the endpoint is unavailable.

[Regression-only commit](https://github.com/PUSCHi1337/Bose-Homeassistant/commit/0f834aaa10fbc75ce9861a13cb0bb7913c4b82d5):
the real SocketClient reproduces the stopped-connect error, with and without
a friendly name, and the legacy-template check also fails before the fix.
The [baseline CI run](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/runs/41184884600)
has **3 failed and 10 passed** focused tests. No network sockets are permitted;
the tests simulate only the TCP endpoint while keeping the real client,
selector, logger and connection-initialization code.

## Automated checks

The [integration workflow](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/workflows/offline-tests.yml)
runs:

- **125 integration tests** with the HA-declared PyChromecast **14.0.10**.
- The same **125 integration tests** with the manifest-resolved Cast dependency;
  its exact installed version is printed in the job log.
- **174 pinned library tests** with the HA dependency set.
- **Two package checks**, repeated after the original-library downgrade and
  exact fork-library reinstallation.

The required `test` job depends on successful HA Cast compatibility tests.
HA **2026.10.4** and Python **3.14** are used. No live HA instance is started.
Tests cover both exact stopped-connect templates, normal and unnamed devices,
device-name percent signs, preserved device context, no classification change
without a stop event, unaffected other clients, and visible authentication,
unexpected, no-retry and similar-but-different errors.

The package checks verify checksum, immutable library provenance, license,
rollback instructions and platform imports. Workflows are checked with
actionlint. The companion library also has separate Python 3.12/3.14 coverage.
HACS/Hassfest validation remains a separate workflow.

## Limited passive device evidence

One Soundbar 700 installation was observed under post7 without agent-issued
power, playback, volume, source or accessory commands during these checks:

- Real power loss made the media player and settings unavailable, followed by
  automatic recovery on their existing entity IDs when power returned.
- Subsequent normal use confirmed both accessory controls reappearing.
- Later ordinary usage again showed two automatic returns from offline.
- The old repeated operational warning/error series did not return in the
  inspected interval. An isolated stopped-connect ERROR exposed the older
  dependency-template mismatch addressed by 1.3.6.
- The ordinary HA custom-integration loader notice is separate from operational
  errors. Other integrations' messages are outside this comparison.

These observations concern the post7 baseline. The 1.3.6 compatibility fix is
verified by offline regression tests; its live activation and log follow-up
are a separate step. No new power-cycle test is required for this fix.
No audio or TTS playback test is implied.

## Remaining limits

- Longer resource monitoring and broader device/firmware coverage remain open.
- Accessories depend on Bose advertising their status; temporary unavailability
  after a standby restart remains possible.
- Expected connection loss while a speaker is unreachable is not a hardware
  fault corrected by this software. Recovery and diagnostic classification
  are separate from the physical reason for being offline.
- See [INSTALL.md](INSTALL.md) for HACS custom-repository installation and
  [ROLLBACK.md](ROLLBACK.md) for restoration of the previous version.

Home network addresses, authentication material, private entity IDs and raw
household logs are intentionally absent from this report.
