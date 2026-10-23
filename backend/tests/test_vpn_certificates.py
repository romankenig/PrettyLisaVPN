import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from prettylisavpn.vpn_sessions.certificates import (
    CredentialPolicyError,
    RevokedCredential,
    X509ClientCertificateIssuer,
)

NOW = datetime(2026, 10, 23, 7, tzinfo=UTC)


def authority(
    *, ca: bool = True, signing: bool = True, expires: datetime = NOW + timedelta(days=30)
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-only-ca")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - timedelta(days=1))
        .not_valid_after(expires)
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, signing, signing, False, False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


def csr(key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey | None = None) -> bytes:
    key = key or ec.generate_private_key(ec.SECP256R1())
    return (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "untrusted-identity")]))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("untrusted.invalid")]), False)
        .sign(key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )


@pytest.mark.parametrize("key_kind", ["p256", "p384", "rsa2048"])
def test_issuance_owns_identity_extensions_and_preserves_client_key(key_kind: str) -> None:
    ca, key = authority()
    client_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if key_kind == "rsa2048"
        else ec.generate_private_key(ec.SECP384R1() if key_kind == "p384" else ec.SECP256R1())
    )
    credential_id, session_id = uuid4(), uuid4()
    issued = X509ClientCertificateIssuer(ca, key).issue(
        credential_id=credential_id,
        session_id=session_id,
        csr_pem=csr(client_key),
        authorized_until=NOW + timedelta(minutes=7),
        now=NOW,
    )
    cert = x509.load_pem_x509_certificate(issued.certificate_pem)
    cert.verify_directly_issued_by(ca)
    assert cert.serial_number == credential_id.int
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == str(session_id)
    assert cert.public_key() == client_key.public_key()
    assert cert.not_valid_after_utc == NOW + timedelta(minutes=7) == issued.expires_at
    assert not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not cert.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign
    assert list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [
        ExtendedKeyUsageOID.CLIENT_AUTH
    ]
    with pytest.raises(x509.ExtensionNotFound):
        cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert "CERTIFICATE" not in repr(issued)


@pytest.mark.parametrize("ca_minutes,expected", [(100, 60), (10, 10)])
def test_validity_capped_by_ca_and_one_hour(ca_minutes: int, expected: int) -> None:
    ca, key = authority(expires=NOW + timedelta(minutes=ca_minutes))
    issued = X509ClientCertificateIssuer(ca, key).issue(
        credential_id=uuid4(),
        session_id=uuid4(),
        csr_pem=csr(),
        authorized_until=NOW + timedelta(days=30),
        now=NOW,
    )
    assert issued.expires_at == NOW + timedelta(minutes=expected)


@pytest.mark.parametrize("kind", ["garbage", "oversize", "multiple", "tampered", "weak-rsa"])
def test_invalid_csr_fails_without_echoing_input(kind: str) -> None:
    ca, key = authority()
    data = csr()
    if kind == "garbage":
        data = b"sensitive-input"
    elif kind == "oversize":
        data += b" " * 16384
    elif kind == "multiple":
        data += data
    elif kind == "tampered":
        request = x509.load_pem_x509_csr(data)
        der = request.public_bytes(serialization.Encoding.DER)
        data = x509.load_der_x509_csr(der[:-1] + bytes([der[-1] ^ 1])).public_bytes(
            serialization.Encoding.PEM
        )
    else:
        data = csr(rsa.generate_private_key(public_exponent=65537, key_size=1024))
    with pytest.raises(CredentialPolicyError, match="^INVALID_CLIENT_CSR$"):
        X509ClientCertificateIssuer(ca, key).issue(
            credential_id=uuid4(),
            session_id=uuid4(),
            csr_pem=data,
            authorized_until=NOW + timedelta(minutes=5),
            now=NOW,
        )


@pytest.mark.parametrize("kind", ["not-ca", "no-signing", "wrong-key"])
def test_invalid_authority(kind: str) -> None:
    ca, key = authority(ca=kind != "not-ca", signing=kind != "no-signing")
    if kind == "wrong-key":
        key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(CredentialPolicyError, match="^INVALID_AUTHORITY$"):
        X509ClientCertificateIssuer(ca, key)


@pytest.mark.parametrize("kind", ["expired-ca", "future-ca", "expired-access", "naive", "nil"])
def test_issuance_fails_closed_for_invalid_time_and_identity(kind: str) -> None:
    ca, key = authority()
    now = NOW
    if kind == "expired-ca":
        now += timedelta(days=31)
    if kind == "future-ca":
        now -= timedelta(days=2)
    if kind == "naive":
        now = now.replace(tzinfo=None)
    with pytest.raises(CredentialPolicyError):
        X509ClientCertificateIssuer(ca, key).issue(
            credential_id=UUID(int=0) if kind == "nil" else uuid4(),
            session_id=uuid4(),
            csr_pem=csr(),
            authorized_until=NOW if kind == "expired-access" else NOW + timedelta(hours=1),
            now=now,
        )


def test_revocation_snapshot_is_signed_numbered_and_short_lived() -> None:
    ca, key = authority()
    revoked = RevokedCredential(uuid4(), NOW - timedelta(minutes=2))
    pem = X509ClientCertificateIssuer(ca, key).revocation_list((revoked,), number=12, now=NOW)
    crl = x509.load_pem_x509_crl(pem)
    assert crl.is_signature_valid(key.public_key())
    assert crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number == 12
    assert crl.next_update_utc == NOW + timedelta(minutes=15)
    assert crl.get_revoked_certificate_by_serial_number(revoked.credential_id.int) is not None


@pytest.mark.parametrize("kind", ["duplicate", "future", "nil", "negative-number"])
def test_invalid_revocation_snapshot(kind: str) -> None:
    ca, key = authority()
    item = RevokedCredential(
        UUID(int=0) if kind == "nil" else uuid4(),
        NOW + timedelta(seconds=1) if kind == "future" else NOW,
    )
    with pytest.raises(CredentialPolicyError, match="^INVALID_REVOCATION_SNAPSHOT$"):
        X509ClientCertificateIssuer(ca, key).revocation_list(
            (item, item) if kind == "duplicate" else (item,),
            number=-1 if kind == "negative-number" else 1,
            now=NOW,
        )


def test_openssl_client_purpose_and_revocation(tmp_path: Path) -> None:
    """Independent OpenSSL verifier, as used by the real OpenVPN/TLS services."""
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("OpenSSL CLI required (available in Linux CI)")
    ca, key = authority()
    signer = X509ClientCertificateIssuer(ca, key)
    credential_id = uuid4()
    issued = signer.issue(
        credential_id=credential_id,
        session_id=uuid4(),
        csr_pem=csr(),
        authorized_until=NOW + timedelta(minutes=10),
        now=NOW,
    )
    (tmp_path / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "client.pem").write_bytes(issued.certificate_pem)
    (tmp_path / "crl.pem").write_bytes(signer.revocation_list((), number=1, now=NOW))

    def verify(purpose: str) -> int:
        return subprocess.run(
            [
                openssl,
                "verify",
                "-attime",
                str(int(NOW.timestamp())),
                "-purpose",
                purpose,
                "-CAfile",
                "ca.pem",
                "-CRLfile",
                "crl.pem",
                "-crl_check",
                "client.pem",
            ],
            cwd=tmp_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode

    assert verify("sslclient") == 0
    assert verify("sslserver") != 0
    (tmp_path / "crl.pem").write_bytes(
        signer.revocation_list((RevokedCredential(credential_id, NOW),), number=2, now=NOW)
    )
    assert verify("sslclient") != 0
