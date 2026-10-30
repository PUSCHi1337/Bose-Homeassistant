"""Constants for the Bose integration."""

import logging
import errno

DOMAIN = "bose"

# Token Refresh Delay is how long between each check if the token is valid
# Token Retry Delay is how long before each retry if refresh fails
TOKEN_REFRESH_DELAY = 3600  # seconds
# How long pybose waits for a speaker to answer a request. A speaker that is offline or in standby simply stays quiet.
REQUEST_TIMEOUT = 8  # Below HA's 10-second poll warning.
TOKEN_RETRY_DELAY = 120  # seconds

# Options key for Chromecast auto-enable setting
CONF_CHROMECAST_AUTO_ENABLE = "chromecast_auto_enable"


_LOGGER = logging.getLogger("bose")


def is_offline_error(error: Exception) -> bool:
    """Normal network absence; keep permissions and protocol failures visible."""
    return isinstance(error, (ConnectionError, TimeoutError)) or (
        isinstance(error, OSError) and error.errno in {
            errno.ECONNREFUSED, errno.ECONNRESET, errno.ECONNABORTED,
            errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ENETDOWN,
            errno.ETIMEDOUT,
        }
    )
