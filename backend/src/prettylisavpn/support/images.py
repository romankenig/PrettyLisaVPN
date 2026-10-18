"""Decode bounded raster images, then rebuild pixels without client metadata."""

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from prettylisavpn.support.domain import SupportError

FILE_BYTES = 5 * 1024 * 1024
TOTAL_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 12_000_000


@dataclass(frozen=True)
class Screenshot:
    data: bytes
    media_type: str
    extension: str


def clean_image(data: bytes, media_type: str) -> Screenshot:
    try:
        if not data or len(data) > FILE_BYTES:
            raise ValueError
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                expected = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
                if expected.get(probe.format or "") != media_type:
                    raise ValueError
                if (
                    probe.width * probe.height > MAX_PIXELS
                    or max(probe.size) > 8192
                    or getattr(probe, "n_frames", 1) != 1
                ):
                    raise ValueError
                probe.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = "RGBA" if "A" in oriented.getbands() else "RGB"
                pixels = oriented.convert(mode)
                clean = Image.frombytes(mode, pixels.size, pixels.tobytes())
                output = BytesIO()
                clean.save(output, format="PNG")
                result = output.getvalue()
                if len(result) > FILE_BYTES:
                    raise ValueError
                return Screenshot(result, "image/png", "png")
    except (
        ValueError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise SupportError("ATTACHMENT_REJECTED", 422) from None
