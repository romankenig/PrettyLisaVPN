from enum import StrEnum


class VpnNodeProvider(StrEnum):
    DIGITALOCEAN = "DIGITALOCEAN"
    NETCUP = "NETCUP"


class VpnNodeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"
    DISABLED = "DISABLED"


class VpnNodeHealthStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"


class VpnSessionStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DISCONNECTED = "DISCONNECTED"
    FAILED = "FAILED"
