"""Export capability metadata from explicit manifests and trusted probe results."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from profiles import load, revision, verified


def export(manifest, reports, now):
    profiles = []
    for profile in manifest["profiles"]:
        report = reports.get(profile["id"])
        state = "UNTESTED"
        evidence = None
        if report is not None:
            state = (
                "E2E_VERIFIED"
                if verified(manifest, profile, report, now)
                else "E2E_FAILED"
            )
            evidence = {
                key: report[key]
                for key in (
                    "node_id",
                    "profile",
                    "configuration_sha256",
                    "checked_at",
                    "transport_established",
                    "tunnel",
                    "dns",
                    "https",
                    "internet",
                    "route_verified",
                    "egress_ip",
                )
            }
        profiles.append(
            {
                key: profile[key]
                for key in (
                    "id",
                    "protocol",
                    "transport",
                    "port",
                    "encryption_mode",
                    "obfuscation_mode",
                    "free_available",
                    "enabled",
                )
            }
            | {
                "health_status": state,
                "configuration_sha256": revision(manifest),
                "evidence": evidence,
            }
        )
    return {"node_id": manifest["node_id"], "profiles": profiles}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("reports", nargs="*")
    args = parser.parse_args()
    reports = {}
    for path in args.reports:
        content = Path(path).read_text()
        rows = (
            [json.loads(line) for line in content.splitlines() if line.strip()]
            if path.endswith(".jsonl")
            else [json.loads(content)]
        )
        for report in rows:
            previous = reports.get(report["profile"])
            if previous is None or datetime.fromisoformat(
                report["checked_at"]
            ) >= datetime.fromisoformat(previous["checked_at"]):
                reports[report["profile"]] = report
    print(json.dumps(export(load(args.manifest), reports, datetime.now(UTC)), indent=2))
