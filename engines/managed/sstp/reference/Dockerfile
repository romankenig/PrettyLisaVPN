# Independent test oracle only; never packaged in PrettyLisaVPN binaries.
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 ca-certificates openssl make gcc libc6-dev && rm -rf /var/lib/apt/lists/*
RUN python3 -c "import urllib.request,hashlib,tarfile,io; data=urllib.request.urlopen('https://github.com/SoftEtherVPN/SoftEtherVPN_Stable/releases/download/v4.41-9787-rtm/softether-vpnserver-v4.41-9787-rtm-2023.03.14-linux-x64-64bit.tar.gz',timeout=60).read(20000000); assert hashlib.sha256(data).hexdigest()=='c766f92fc664cc95eb4b78d7c041a1e26dbd20d2e714438426c7bc45b146ffd9'; tarfile.open(fileobj=io.BytesIO(data)).extractall('/reference',filter='data')"
RUN cd /reference/vpnserver && make main
ENV PATH=/reference/vpnserver:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
COPY configure.py /reference/configure.py
CMD ["python3", "/reference/configure.py"]
