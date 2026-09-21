"""Provider policy independent of VPN encryption and session orchestration."""


def validate_obfuscation(
    protocol: str,
    transport: str,
    mode: str,
    version: int | None,
    parameters: dict[str, int] | None,
    mtu: int,
) -> None:
    if version is not None and type(version) is not int:
        raise ValueError("unsupported obfuscation version")
    params = parameters or {}
    if mode == "NATIVE" and transport == "NATIVE" and version is None and not params:
        return  # Existing local transport policy; not a new provider.
    if mode == "NONE" and version in (None, 0) and not params:
        return
    if type(version) is not int or version != 1:
        raise ValueError("unsupported obfuscation version")
    if mode == "TLS_TRANSPORT" and protocol == "OPENVPN" and transport == "TCP" and not params:
        return  # Runtime capability is additionally required on the client.
    if mode == "SIMPLE_PACKET_WRAPPER_V1" and protocol == "WIREGUARD" and transport == "UDP":
        maximum = params.get("max_datagram_size", 1400)
        if (
            set(params) <= {"max_datagram_size"}
            and type(maximum) is int
            and mtu + 40 <= maximum <= 65507
        ):
            return
    raise ValueError("unsupported obfuscation configuration")
