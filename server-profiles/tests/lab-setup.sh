#!/bin/sh
# LOCAL LAB ONLY. Ephemeral test CA shared by two disposable containers.
set -eu
umask 077
cd /pki
openssl req -x509 -newkey rsa:3072 -nodes -keyout ca.key -out ca.crt -days 2 -subj /CN=PrettyLisa-Lab-CA >/dev/null 2>&1
openssl req -new -newkey rsa:3072 -nodes -keyout server.key -out server.csr -subj /CN=vpn.test >/dev/null 2>&1
printf 'subjectAltName=DNS:vpn.test\nextendedKeyUsage=serverAuth\n' > server.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 2 -extfile server.ext >/dev/null 2>&1
openssl req -new -newkey rsa:3072 -nodes -keyout client.key -out client.csr -subj /CN=external-test >/dev/null 2>&1
printf 'extendedKeyUsage=clientAuth\n' > client.ext
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 2 -extfile client.ext >/dev/null 2>&1
python3 - <<'PY'
import hashlib,json,ssl,subprocess
address=json.loads(subprocess.check_output(['ip','-j','-4','address','show','eth0']))[0]['addr_info'][0]['local']
cert=ssl.PEM_cert_to_DER_cert(open('/pki/client.crt').read())
base=dict(endpoint=address+':443',server_name='vpn.test',interface='plmasque',ca='/pki/ca.crt')
server=dict(base,mode='server',address='10.80.0.1/24',certificate='/pki/server.crt',private_key='/pki/server.key',clients={hashlib.sha256(cert).hexdigest():'10.80.0.2'})
client=dict(base,mode='client',address='10.80.0.2/24',certificate='/pki/client.crt',private_key='/pki/client.key',clients={})
for name,data in [('server',server),('client',client)]:
 with open('/pki/'+name+'.json','w') as f:json.dump(data,f)
PY
iptables -t nat -A POSTROUTING -s 10.80.0.0/24 -o eth0 -j MASQUERADE
printf 'lab_configured\n'
