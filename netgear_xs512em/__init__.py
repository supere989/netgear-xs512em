"""Pure-Python control of the NETGEAR XS512EM Smart Managed Plus switch (no SSH/SNMP)."""
from .client import (
    XS512EM,
    SwitchError,
    AuthError,
    SessionBusyError,
    membership_string,
    UNTAGGED,
    TAGGED,
    NONMEMBER,
)

__version__ = "0.1.0"
__all__ = [
    "XS512EM",
    "SwitchError",
    "AuthError",
    "SessionBusyError",
    "membership_string",
    "UNTAGGED",
    "TAGGED",
    "NONMEMBER",
    "__version__",
]
