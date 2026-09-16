#!/usr/bin/env bash
set -Eeuo pipefail

deployment_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
environment_file="${1:-/etc/prettylisavpn/deployment.env}"

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

for command_name in docker curl getent grep sed; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Required command is missing: %s\n' "$command_name" >&2
        exit 1
    fi
done

read_environment_value() {
    local value
    value="$(sed -n "s/^${1}=//p" "$environment_file" | tail -n 1)"
    value="${value#\'}"
    value="${value%\'}"
    printf '%s' "$value"
}

api_domain="$(read_environment_value API_DOMAIN)"
backend_image="$(read_environment_value BACKEND_IMAGE)"
application_version="$(read_environment_value APPLICATION_VERSION)"
project_name="$(read_environment_value COMPOSE_PROJECT_NAME)"
project_name="${project_name:-prettylisavpn}"

if [[ ! "$api_domain" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]; then
    printf 'API_DOMAIN must be an unquoted public DNS hostname: %s\n' "$api_domain" >&2
    exit 1
fi

if [[ -z "$backend_image" || "$backend_image" == *:latest ]]; then
    printf 'BACKEND_IMAGE must be an immutable digest or unique release tag, not latest.\n' >&2
    exit 1
fi

if [[ -z "$application_version" ]]; then
    printf 'APPLICATION_VERSION must be set.\n' >&2
    exit 1
fi

if ! getent ahosts "$api_domain" >/dev/null 2>&1; then
    printf 'API_DOMAIN does not resolve yet: %s\n' "$api_domain" >&2
    printf 'Create DNS records manually before deployment; this script never changes DNS.\n' >&2
    exit 1
fi

compose=(docker compose --project-name "$project_name" \
    --env-file "$environment_file" --file "$deployment_dir/compose.yaml")

node_agent_token="$(read_environment_value VPN_NODE_AGENT_AUTH_TOKEN)"
if [[ -n "$node_agent_token" ]]; then
    node_agent_compose="$deployment_dir/compose.node-agent.yaml"
    if [[ ! -f "$node_agent_compose" ]]; then
        printf 'Node agent is configured but deployment override is missing.\n' >&2
        exit 1
    fi
    compose+=(--file "$node_agent_compose")
fi

"${compose[@]}" config --quiet
if [[ "${SKIP_BACKEND_PULL:-0}" == "1" ]]; then
    "${compose[@]}" pull caddy
else
    "${compose[@]}" pull
fi

printf 'Applying database migrations...\n'
"${compose[@]}" run --rm --no-deps --no-tty backend alembic upgrade head </dev/null

printf 'Recreating application containers...\n'
"${compose[@]}" up --detach --remove-orphans --wait --wait-timeout 120

curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --max-time 10 "https://${api_domain}/health" >/dev/null
curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --max-time 10 "https://${api_domain}/ready" >/dev/null

version_response="$(curl --fail --silent --show-error --retry 12 --retry-delay 5 \
    --retry-connrefused --max-time 10 "https://${api_domain}/version")"
if ! grep -Fq "\"application_version\":\"${application_version}\"" <<<"$version_response"; then
    printf 'Version check failed: deployed application did not report the expected version.\n' >&2
    exit 1
fi

printf 'Deployment passed health, readiness, and version checks.\n'
