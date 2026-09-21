"""Reproducible codec CPU benchmark; not end-to-end network latency."""

import json
import platform
import statistics
import timeit

from prettylisavpn_obfuscator.providers import NoObfuscation, SimplePacketWrapperV1


def main() -> None:
    rows = []
    for size in (148, 1312, 4096):
        packet = bytes(index % 256 for index in range(size))
        measurements = {}
        for name, codec in (
            ("NONE", NoObfuscation(65507)),
            ("SIMPLE_PACKET_WRAPPER_V1", SimplePacketWrapperV1(65507)),
        ):

            def roundtrip(codec: NoObfuscation = codec, packet: bytes = packet) -> None:
                codec.decode(codec.encode(packet))

            elapsed = statistics.median(timeit.repeat(roundtrip, number=100_000, repeat=5))
            measurements[name] = round(elapsed * 1_000_000 / 100_000, 3)
        rows.append(
            {
                "input_bytes": size,
                "extra_bytes": 8,
                "overhead_percent": round(800 / size, 3),
                "median_roundtrip_microseconds": measurements,
            }
        )
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.system(),
                "iterations_per_repeat": 100_000,
                "repeats": 5,
                "results": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
