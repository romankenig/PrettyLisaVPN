#!/usr/bin/env bash
set -Eeuo pipefail

deployment_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
environment_file="${1:-/etc/prettylisavpn/deployment.env}"
project_name="prettylisavpn"

if [[ ! -f "$environment_file" ]]; then
    printf 'Environment file does not exist: %s\n' "$environment_file" >&2
    exit 1
fi

environment_mode="$(stat -c '%a' "$environment_file")"
if [[ "$environment_mode" != "600" ]]; then
    printf 'Environment file must have mode 600; found %s: %s\n' \
        "$environment_mode" "$environment_file" >&2
    exit 1
fi

for command_name in docker curl getent sed; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Required command is missing: %s\n' "$command_name" >&2
        exit 1
    fi
done

api_domain="$(sed -n 's/^API_DOMAIN=//p' "$environment_file" | tail -n 1)"
backend_image="$(sed -n 's/^BACKEND_IMAGE=//p' "$environment_file" | tail -n 1)"

if [[ ! "$api_domain" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]; then
    printf 'API_DOMAIN must be an unquoted public DNS hostname: %s\n' "$api_domain" >&2
    exit 1
fi

if [[ -z "$backend_image" || "$backend_image" == *:latest ]]; then
    printf 'BACKEND_IMAGE must be an immutable digest or unique release tag, not latest.\n' >&2
    exit 1
fi

if ! getent ahosts "$api_domain" >/dev/null 2>&1; then
    printf 'API_DOMAIN does not resolve yet: %s\n' "$api_domain" >&2
    printf 'Create DNS records manually before deployment; this script never changes DNS.\n' >&2
    exit 1
fi

compose=(docker compose --project-name "$project_name" \
    --env-file "$environment_file" --file "$deployment_dir/compose.yaml")

"${compose[@]}" config --quiet
"${compose[@]}" pull
"${compose[@]}" up --detach --remove-orphans --wait --wait-timeout 120

curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --max-time 10 "https://${api_domain}/health" >/dev/null

printf 'Deployment is healthy: https://%s/health\n' "$api_domain"
printf 'Check dependency readiness: curl --fail https://%s/ready\n' "$api_domain"
