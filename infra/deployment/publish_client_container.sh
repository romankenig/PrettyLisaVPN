#!/usr/bin/env bash
set -Eeuo pipefail

# Reuse the deployment account's existing Docker access. Do not grant it root
# SSH access or make the dashboard password directory readable by that account.
test "$#" -eq 5
platform="$1"
incoming="$2"
sha="$3"
run="$4"
attempt="$5"
case "$platform" in android|windows) ;; *) exit 1 ;; esac
[[ "$sha" =~ ^[a-f0-9]{40}$ && "$run" =~ ^[1-9][0-9]*$ && "$attempt" =~ ^[1-9][0-9]*$ ]]
[[ "$incoming" == "/opt/prettylisavpn/incoming/client-${platform}-${run}-${attempt}" ]]

# An immutable local image ID avoids pulling an unrelated runtime. Only the
# incoming build and the download store are mounted; no credentials or socket.
image="$(docker inspect --format '{{.Image}}' prettylisavpn-development-backend-1)"
[[ "$image" =~ ^sha256:[a-f0-9]{64}$ ]]
downloads=/opt/prettylisavpn/secrets/dashboard/downloads
exec docker run --rm --pull never --network none --read-only --user 0:0 \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 32 \
  --no-healthcheck --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  --mount "type=bind,src=$incoming,dst=$incoming,readonly" \
  --mount "type=bind,src=$downloads,dst=$downloads" \
  --entrypoint python "$image" "$incoming/publish_client.py" \
  --platform "$platform" --directory "$incoming" --sha "$sha" \
  --run "$run" --attempt "$attempt"
