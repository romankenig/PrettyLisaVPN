"""OpenVPN client PKI boundary; not wired into public session issuance.

The caller owns authorization, durable issuance/revocation records and delivery.
Client private keys never cross this boundary. Inject a signer only in a trusted
signing process; the API must not load production CA keys from node test bundles.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

SigningKey = rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey
MAX_CERTIFICATE_LIFETIME = timedelta(hours=1)
MAX_CRL_LIFETIME = timedelta(minutes=15)


class CredentialPolicyError(ValueError):
    """Closed diagnostic code only; never include CSR, PEM or provider output."""


@dataclass(frozen=True)
class ClientCertificate:
    credential_id: UUID
    session_id: UUID
    expires_at: datetime
    certificate_pem: bytes = field(repr=False)


@dataclass(frozen=True)
class RevokedCredential:
    credential_id: UUID
    revoked_at: datetime


class ClientCertificateIssuer(Protocol):
    def issue(
        self,
        *,
        credential_id: UUID,
        session_id: UUID,
        csr_pem: bytes,
        authorized_until: datetime,
        now: datetime,
    ) -> ClientCertificate: ...


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise CredentialPolicyError("INVALID_TIME")
    return value.astimezone(UTC).replace(microsecond=0)


def _strong_key(key: object) -> bool:
    if isinstance(key, rsa.RSAPublicKey):
        return 2048 <= key.key_size <= 4096 and key.public_numbers().e == 65537
    return isinstance(key, ec.EllipticCurvePublicKey) and isinstance(
        key.curve, (ec.SECP256R1, ec.SECP384R1)
    )


class X509ClientCertificateIssuer:
    """Pure signing adapter with injected CA; no network, filesystem or logging.

    A persistent ledger must allocate credential UUIDs and retain the exact issued
    certificate for retries. Reusing an ID with different input is forbidden by
    that ledger, not managed by this stateless adapter.
    """

    def __init__(self, ca: x509.Certificate, key: SigningKey) -> None:
        try:
            constraints = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
            usage = ca.extensions.get_extension_for_class(x509.KeyUsage).value
            if not constraints.ca or not usage.key_cert_sign or not usage.crl_sign:
                raise ValueError
            if not _strong_key(key.public_key()):
                raise ValueError
            encoding = serialization.Encoding.DER
            form = serialization.PublicFormat.SubjectPublicKeyInfo
            if ca.public_key().public_bytes(encoding, form) != key.public_key().public_bytes(
                encoding, form
            ):
                raise ValueError
            try:
                eku = ca.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            except x509.ExtensionNotFound:
                eku = None
            if eku is not None and ExtendedKeyUsageOID.CLIENT_AUTH not in eku:
                raise ValueError
        except (ValueError, x509.ExtensionNotFound, UnsupportedAlgorithm):
            raise CredentialPolicyError("INVALID_AUTHORITY") from None
        self._ca = ca
        self._key = key

    def _check_time(self, now: datetime) -> None:
        if not self._ca.not_valid_before_utc <= now < self._ca.not_valid_after_utc:
            raise CredentialPolicyError("AUTHORITY_EXPIRED_OR_NOT_YET_VALID")

    def issue(
        self,
        *,
        credential_id: UUID,
        session_id: UUID,
        csr_pem: bytes,
        authorized_until: datetime,
        now: datetime,
    ) -> ClientCertificate:
        now = _utc(now)
        self._check_time(now)
        deadline = min(
            _utc(authorized_until), now + MAX_CERTIFICATE_LIFETIME, self._ca.not_valid_after_utc
        )
        if deadline <= now or not credential_id.int or not session_id.int:
            raise CredentialPolicyError("INVALID_ISSUANCE")
        try:
            if len(csr_pem) > 16384 or csr_pem.count(b"-----BEGIN ") != 1:
                raise ValueError
            csr = x509.load_pem_x509_csr(csr_pem)
            if not csr.is_signature_valid or not _strong_key(csr.public_key()):
                raise ValueError
            if not isinstance(csr.signature_hash_algorithm, (hashes.SHA256, hashes.SHA384)):
                raise ValueError
        except (ValueError, UnsupportedAlgorithm):
            raise CredentialPolicyError("INVALID_CLIENT_CSR") from None
        # Ignore caller-controlled subject and extensions, including CA/serverAuth/SAN.
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(session_id))]))
            .issuer_name(self._ca.subject)
            .public_key(csr.public_key())
            .serial_number(credential_id.int)
            .not_valid_before(now)
            .not_valid_after(deadline)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(True, False, False, False, False, False, False, False, False),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self._key.public_key()),
                critical=False,
            )
            .sign(self._key, hashes.SHA256())
        )
        return ClientCertificate(
            credential_id,
            session_id,
            deadline,
            certificate.public_bytes(serialization.Encoding.PEM),
        )

    def revocation_list(
        self,
        revoked: tuple[RevokedCredential, ...],
        *,
        number: int,
        now: datetime,
    ) -> bytes:
        """Sign a full ledger snapshot; caller must publish monotonically on every node.

        CRL publication alone does not disconnect existing OpenVPN connections.
        Termination needs a node acknowledgement before quota/session cleanup.
        """
        now = _utc(now)
        self._check_time(now)
        if number < 0 or len({item.credential_id for item in revoked}) != len(revoked):
            raise CredentialPolicyError("INVALID_REVOCATION_SNAPSHOT")
        builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self._ca.subject)
            .last_update(now)
            .next_update(min(now + MAX_CRL_LIFETIME, self._ca.not_valid_after_utc))
            .add_extension(x509.CRLNumber(number), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self._key.public_key()),
                critical=False,
            )
        )
        for item in sorted(revoked, key=lambda item: item.credential_id.int):
            if not item.credential_id.int or _utc(item.revoked_at) > now:
                raise CredentialPolicyError("INVALID_REVOCATION_SNAPSHOT")
            builder = builder.add_revoked_certificate(
                x509.RevokedCertificateBuilder()
                .serial_number(item.credential_id.int)
                .revocation_date(_utc(item.revoked_at))
                .build()
            )
        return builder.sign(self._key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)
