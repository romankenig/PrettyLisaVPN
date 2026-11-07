"""Real adapter shape: only customer per-lease counters, in user directions."""

import json
from uuid import uuid4

from prettylisavpn.fleet.traffic import Snapshot
from prettylisavpn.fleet.ubuntu import traffic


def test_wireguard_mapping_excludes_probes_and_transit_and_swaps_directions(tmp_path, monkeypatch):
    monkeypatch.setattr(traffic, "ROOT", tmp_path)
    boot, interface = tmp_path / "boot", tmp_path / "index"
    boot.write_text("test-boot")
    interface.write_text("42")
    monkeypatch.setattr(traffic, "BOOT", boot)
    monkeypatch.setattr(traffic, "INTERFACE", interface)
    monkeypatch.setattr(traffic.time, "time", lambda: 100)
    monkeypatch.setattr(traffic.time, "monotonic", lambda: 50)
    (tmp_path / "clients").mkdir()
    lease = uuid4()
    (tmp_path / "clients" / f"{lease}.json").write_text(
        json.dumps(
            {
                "public_key": "customer-key",
                "expires": 200,
                "generation": "generation-1",
            }
        )
    )
    fields = []

    def wg(field):
        fields.append(field)
        return "customer-key 111 222\nmonitor-key 999999 999999"

    monkeypatch.setattr(traffic, "wg", wg)
    result = Snapshot.model_validate(traffic.snapshot())
    assert result.complete
    assert len(result.counters) == 1
    assert result.counters[0].lease_id == lease
    assert result.counters[0].download == 222
    assert result.counters[0].upload == 111
    assert "customer-key" not in result.model_dump_json()
    assert fields == ["transfer"]  # no interface counters, private keys or peer endpoints
    interface.write_text("43")
    assert Snapshot.model_validate(traffic.snapshot()).counters[0].epoch != result.counters[0].epoch


def test_managed_stale_legacy_missing_counters_are_partial_not_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(traffic, "ROOT", tmp_path)
    boot = tmp_path / "boot"
    boot.write_text("boot")
    monkeypatch.setattr(traffic, "BOOT", boot)
    monkeypatch.setattr(traffic, "INTERFACE", tmp_path / "absent")
    monkeypatch.setattr(traffic.time, "time", lambda: 100)
    monkeypatch.setattr(traffic.time, "monotonic", lambda: 50)
    leases = tmp_path / "managed" / "leases"
    leases.mkdir(parents=True)
    current = uuid4()
    for index, kind in enumerate(("current", "stale", "legacy", "monitor")):
        path = leases / f"{current if index == 0 else uuid4()}.json"
        path.write_text(
            json.dumps({"expires": 200, "purpose": "monitor" if kind == "monitor" else "client"})
        )
        data = {
            "rx_bytes": 123,
            "tx_bytes": 456,
            "observed_at": 99,
            "monotonic": 49,
            "generation": "engine-1",
        }
        if kind == "stale":
            data["observed_at"] = 50
        if kind == "legacy":
            data.pop("generation")
        path.with_suffix(".stats").write_text(json.dumps(data))
    result = Snapshot.model_validate(traffic.snapshot())
    assert not result.complete
    assert len(result.counters) == 1
    assert result.counters[0].lease_id == current
    assert (result.counters[0].download, result.counters[0].upload) == (456, 123)
