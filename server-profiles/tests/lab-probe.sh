#!/bin/sh
set -eu
# Only use inside an isolated client container, never the host network namespace.
endpoint=$(python3 -c 'import json;print(json.load(open("/pki/client.json"))["endpoint"].split(":")[0])')
gateway=$(ip -4 route show default | awk '{print $3}')
ip route replace "$endpoint/32" via "$gateway" dev eth0
ip route replace 0.0.0.0/1 dev plmasque
ip route replace 128.0.0.0/1 dev plmasque
ip route get 1.1.1.1
curl --silent --fail --noproxy '*' --max-time 20 --interface plmasque https://1.1.1.1/cdn-cgi/trace | awk -F= '$1 == "ip" {print "egress_ip=" $2}'
