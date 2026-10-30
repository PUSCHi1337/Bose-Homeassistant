# Validation and remaining limits

## Runtime baseline

The installed runtime candidate is integration **1.3.5.post7** from
`f3060b1c677ee05047aace3ef3a8a44711067231`, paired with the immutable pybose
source `bfcce6fc33a6a174484acd09ba0f30c1513843a0` (package version
`2026.10.2.post2`). Repository preparation updates documentation,
artifact metadata, workflow behavior and requirement notation. The manifest's
named library URL uses
compact PEP 508 notation (`pybose@https://...`) to satisfy Hassfest's no-space
rule. The Python runtime code, package versions and exact library source remain
unchanged.

[Baseline CI](https://github.com/PUSCHi1337/Bose-Homeassistant/actions/runs/41030871351):
112 integration tests, 174 library tests with the HA dependency set and two
package checks pass. Package checks pass again after dependency downgrade and
reinstallation. The library additionally passes 174 tests on Python 3.12 and 3.14.
Tests use fake credentials/devices and block network sockets.

The packaged archive is checked for checksum, immutable dependency provenance,
license, rollback instructions and platform imports against the actual HA and
library dependencies. Actions workflows are checked with actionlint; library CI
also builds its wheel and source distribution.

## Limited passive device checks

One Soundbar 700 installation was observed without agent-issued power, playback,
volume, source or accessory commands during the post7 test:

- A real loss of power made the media player and previously available settings
  unavailable. More than six minutes offline produced no new operational Bose
  warnings or errors at the normal WARNING level.
- After power returned, the media player recovered automatically on its existing
  entity ID. A further observation longer than eight minutes remained free of new
  Bose warnings/errors.
- The ordinary one-time HA custom-integration loader notice is separate from
  operational errors. Other integrations' messages are outside this comparison.

These are bounded observations, not full device compatibility or long-term
resource-stability guarantees. No audio or TTS playback test is implied.

## Known follow-ups

- On an HA restart while the soundbar is in standby, accessory controls can remain
  restored/unavailable until Bose advertises their status. Late discovery is
  implemented and tested, but accessory reappearance during subsequent active
  operation still needs a real-device check.
- The optional live Cast socket state was not extracted. The precise concurrent
  TCP-timeout/stop race is reproduced through the real installed PyChromecast code
  in CI; it is not inferred solely from an empty live log.
- Longer resource monitoring and broader device/firmware coverage remain open.
- The first public preview is distributed through a GitHub pre-release and can
  be selected through a HACS custom repository; see [INSTALL.md](INSTALL.md).
  A public stable release remains a separate decision after further observation.

Home network addresses, authentication material, private entity IDs and raw
household logs are intentionally absent from this report.
