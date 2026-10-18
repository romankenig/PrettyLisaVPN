"""SemVer 2.0 precedence, independent for each client platform."""

import re
from dataclasses import dataclass
from functools import total_ordering

_PATTERN = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


@total_ordering
@dataclass(frozen=True, eq=False)
class Version:
    release: tuple[int, int, int]
    prerelease: tuple[str, ...]

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = _PATTERN.fullmatch(value)
        if match is None or len(value) > 100:
            raise ValueError("Invalid SemVer")
        pre = tuple(match[4].split(".")) if match[4] else ()
        if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in pre):
            raise ValueError("Invalid numeric prerelease identifier")
        return cls((int(match[1]), int(match[2]), int(match[3])), pre)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.release, self.prerelease) == (other.release, other.prerelease)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self.release != other.release:
            return self.release < other.release
        if not self.prerelease or not other.prerelease:
            return bool(self.prerelease) and not other.prerelease
        for left, right in zip(self.prerelease, other.prerelease, strict=False):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.prerelease) < len(other.prerelease)
