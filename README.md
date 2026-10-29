# Bose Home Assistant — experimental stability fork

> Documentation adapted by [PUSCHi1337](https://github.com/PUSCHi1337) on 2026-10-29,
> based on [cavefire/Bose-Homeassistant](https://github.com/cavefire/Bose-Homeassistant).
> Upstream authorship, copyright notices and the [GNU GPLv3 license](LICENSE) are retained.
> This fork is not an official Bose product or an upstream release.

## Fork development status

This repository is the companion integration fork for the stability work in
[PUSCHi1337/pybose](https://github.com/PUSCHi1337/pybose).
The library's [discovery cleanup](https://github.com/PUSCHi1337/pybose/pull/1)
and [connection lifecycle work](https://github.com/PUSCHi1337/pybose/pull/2)
are draft changes. Their GitHub checks cover simulated unit tests, not hardware
validation of this integration.

This documentation branch does not change the integration's runtime code.
The manifest still requires upstream `pybose==2026.10.2`: installing this
integration fork alone therefore does **not** activate the draft library fixes.
The token background-task lifecycle and stale entity client/callback references
after reconnection remain open. There is no tested fork installation package or
fork release, and a fix for a full NAS hang has not been established.

The installation instructions, screenshots, feature lists and device reports below
are retained as upstream reference. They must not be read as evidence that the
modified fork has been tested on those devices. Discuss fork-specific changes in
the relevant fork PR; upstream maintainers are not responsible for this branch.


This is a custom component for Home Assistant to integrate with Bose soundbars / speakers.
The speakers are controlled 100% locally. However, a cloud account is needed and required configured in the integration. Read more about this in the [BOSE Account](#bose-account) section.

![Preview](images/entities.jpg)

![Preview](images/media_player.jpg)

## Upstream installation reference

### Using HACS

For the original integration, follow the
[upstream installation instructions](https://github.com/cavefire/Bose-Homeassistant#installation).
Those instructions install the upstream package, not the draft stability fixes
being developed in this fork.

### Upstream manual installation (reference only)

1. Clone or download the [upstream repository](https://github.com/cavefire/Bose-Homeassistant).
2. Copy the `custom_components` directory of this repository to your Home Assistant `config` directory.
3. Restart Home Assistant.

## Setup

1. Go to "Configuration" -> "Devices & Services" -> "Add Device" -> "Bose".
2. Enter your BOSE account credentials (required, see [BOSE Account](#bose-account)).
3. Select the device you want to add (discovered by mDNS or manually).
4. Click "Add Device".

## BOSE Account

BOSE requires you to have an account in order to control a soundbar / speaker. Even if you allow access for all users in the network, you still need to provide your account credentials.

So this integration is making use of `pybose`'s authentication. You can find more information about this in the [pybose repository](https://github.com/cavefire/pybose).

`pybose` is a Python library that reverse-engineers the BOSE API. It is used to authenticate with the BOSE API and to control the soundbar / speaker. After the initial call to the BOSE API, an access token is stored, making the following calls to the device locally.

## Features

This is the list of features implemented in the integration. Non-marked features are not yet implemented. Feel free to do so!

- [x] Control power
- [x] Control volume
- [x] See current volume
- [x] See currently playing media (title, artist, album, cover, duration and position)
- [x] Control media (play, pause, next, previous)
- [x] Select sources (aux, chinch, optical - based on the speaker)
- [x] Control bluetooth 
- [x] Audio setup (bass, treble, center, surround)
- [x] Enable / disable bass module and gain
- [x] Enable / disable surround speakers 
- [x] Group speakers
- [x] HDMI-CEC settings
- [x] Standby timer settings
- [x] Optical activation settings
- [x] Battery Level (for portable speakers)
- [x] Rebroadcast latency settings
- [x] Standby timer settings
- [x] Dialog settings (AI Dialog Mode, Dialog Mode, Normal - based on the speaker)
- [x] Dual Mono settings
- [x] Send arbitrary request via service

### Group speakers
You can group multiple Bose speakers together, like in the Bose App. This is done by using the service `media_player.join`.

**Target:** Select the entity you want to be the master speaker (max. 1 media player!)
**Group members:** Select the entities you want to join the master speaker.

You can either join all desired speakers together, or you can join them one by one.
Joining a speaker to a other speaker, that is already in a group, will join the new speaker to the existing group.

**Example:**
```yaml
action: media_player.join
data:
  group_members:
    - media_player.bose_smart_ultra_soundbar
target:
  entity_id: media_player.bose_music_amplifier
```

To remove a speaker from the group, use the service `media_player.unjoin`. If the target is the master speaker, the group will be dissolved. Otherwise the target will be removed from the group.

### Services

- `bose.send_custom_request` - Send a custom request to the speaker. This can be used to control features that are not yet implemented in the integration and for debugging purposes.

### Devices reported as tested by upstream

Upstream aims to support devices connected via WiFi and controlled using the BOSE App. The following device reports are inherited from upstream; this fork has not independently verified them:

**Soundbars:**
- [x] Soundbar 500
- [x] Soundbar 700
- [x] Soundbar 900
- [x] Soundbar Ultra

**Home Speakers:**
- [x] Home Speaker 300
- [x] Home Speaker 500

**Others:**
- [x] Music Amplifier
- [x] Portable Speaker

If you have a device that is not listed here, please open an issue or a pull request.
These devices only work with the features that are marked as completed above. Some features might not work due to hardware or software limitations. 
**If a feature is missing on your device, please open an issue.**

## Contributing
This project is a work in progress, and contributions are welcome!
If you encounter issues, have feature requests, or want to contribute, feel free to submit a pull request or open an issue.

The upstream architecture separates the integration from the `pybose` library so that the library can also be used in other projects. So every function that is calling the speaker's websocket, should be implemented in the `pybose` library. The integration should only be responsible for the Home Assistant part.

To support the original author's work, the following donation link belongs to **cavefire**, not to the fork maintainer: 
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/yellow_img.png)](https://www.buymeacoffee.com/cavefire)


## Disclaimer
This project is not affiliated with Bose Corporation. The API is reverse-engineered and may break at any time. Use at your own risk.

**Original author's note to the BOSE legal team (retained from cavefire's README):**

All API keys used in this project are publicly available on the Bose website.

There was no need to be a computer specialist to find them, so: Please do not sue me for making people use their products in a way they want to.

If you have any issues with me publishing this, please contact me! I am happy to discuss this with you and make your products better.

## License
This project is licensed under GNU GPLv3 - see the [LICENSE](LICENSE) file for details.
