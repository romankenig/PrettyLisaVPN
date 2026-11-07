"""Privileged local read of customer counters. Called only through the SSH helper.

No interfaces, relay links, synthetic probes, public keys or destinations are
exported. The backend owns the mapping from lease UUID to account UUID.
"""

import time
from pathlib import Path
from typing import Any

if __package__:
    from .node import ROOT, WG, read, wg
else:
    from node import ROOT, WG, read, wg  # type: ignore[no-redef,import-not-found]

BOOT = Path("/proc/sys/kernel/random/boot_id")
INTERFACE = Path("/sys/class/net") / WG / "ifindex"


def snapshot() -> dict[str, Any]:
    boot = BOOT.read_text().strip()
    counters: list[dict[str, Any]] = []
    complete = True
    interface = INTERFACE
    clients = list((ROOT / "clients").glob("*.json"))
    if clients and interface.exists():
        transfer = {
            key: (int(rx), int(tx))
            for key, rx, tx in (line.split() for line in wg("transfer").splitlines())
        }
        at, mono = time.time(), time.monotonic()
        epoch = boot + ":" + interface.read_text().strip()
        for path in clients:
            row = read(path)
            if row.get("expires", 0) <= at:
                continue
            values = transfer.get(row["public_key"])
            if values is None:
                complete = False
                continue
            counters.append(
                {
                    "lease_id": path.stem,
                    "epoch": epoch + ":" + row.get("generation", path.stem),
                    "at": at,
                    "monotonic": mono,
                    "download": values[1],
                    "upload": values[0],
                }
            )
    elif clients:
        complete = False
    for path in (ROOT / "managed" / "leases").glob("*.json"):
        row = read(path)
        if row.get("purpose", "client") != "client" or row.get("expires", 0) <= time.time():
            continue
        sample = read(path.with_suffix(".stats"))
        # Old helpers/engines are unknown, never presented as zero traffic.
        if (
            not sample.get("generation")
            or "monotonic" not in sample
            or not 0 <= time.time() - sample.get("observed_at", 0) <= 7.5
        ):
            complete = False
            continue
        counters.append(
            {
                "lease_id": path.stem,
                "epoch": boot + ":" + sample["generation"],
                "at": sample["observed_at"],
                "monotonic": sample["monotonic"],
                "download": sample["tx_bytes"],
                "upload": sample["rx_bytes"],
            }
        )
    return {
        "at": time.time(),
        "monotonic": time.monotonic(),
        "boot": boot,
        "complete": complete,
        "counters": counters,
    }
