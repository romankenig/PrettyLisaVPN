"""New presets remain bounded and match the observed, non-personal catalog evidence."""

import importlib.util
import json
from pathlib import Path

from prettylisavpn.traffic.service import TrafficService


def test_new_presets_preserve_legacy_ids_and_fit_existing_clients():
    root = Path(__file__).resolve().parents[2]
    file = root / "backend/migrations/versions/0040_traffic_catalog_refresh.py"
    spec = importlib.util.spec_from_file_location("catalog_refresh", file)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    services = [TrafficService.model_validate(row) for row in migration.SERVICES]
    assert len(services) == 40
    assert len({row.id for row in services}) == 40
    assert len({row.slug for row in services}) == 40
    assert {"youtube", "instagram", "telegram"}.isdisjoint(row.slug for row in services)
    assert len(migration.POPULARITY) == 60
    assert all(row.category == "popular" for row in services)
    evidence = json.loads(
        (root / "assets/domain-catalog/selection.json").read_text(encoding="utf-8")
    )
    assert evidence["app"] == "com.notvpn" and evidence["version"] == "25.3"
    assert len(evidence["services"]) == 50
    assert {row.slug for row in services} <= {row["slug"] for row in evidence["services"]}
