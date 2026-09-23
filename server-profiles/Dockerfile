FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates curl iproute2 iptables wireguard-tools openvpn stunnel4 openssl python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/probe
COPY profiles.py probe.py wrapper_client.py run_profile.py ./
COPY runtime/*.whl /tmp/wheels/
RUN python3 -m venv /opt/probe/venv && /opt/probe/venv/bin/pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels
COPY --chmod=0755 masque/masque /usr/local/bin/prettylisa-masque
ENTRYPOINT ["sleep", "infinity"]
