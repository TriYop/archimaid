import re
from dataclasses import dataclass

from archimaid.domain.errors import InvalidEntity

CODE_PATTERN = re.compile(r"[A-Z0-9_]+")


@dataclass(frozen=True, kw_only=True)
class ReferenceValue:
    code: str
    label: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not CODE_PATTERN.fullmatch(self.code):
            raise InvalidEntity("code must contain only A-Z, 0-9 and underscore")
        if not self.label.strip():
            raise InvalidEntity("label must not be blank")


@dataclass(frozen=True, kw_only=True)
class RankedValue(ReferenceValue):
    rank: int


@dataclass(frozen=True, kw_only=True)
class AvailabilityLevel(RankedValue):
    rpo_hours: int
    rto_hours: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.rpo_hours < 0 or self.rto_hours < 0:
            raise InvalidEntity("rpo_hours and rto_hours must not be negative")


class ConfidentialityLevel(RankedValue):
    pass


class IntegrityLevel(RankedValue):
    pass


class TraceabilityLevel(RankedValue):
    pass


class FunctionCategory(ReferenceValue):
    pass


class UsageMode(ReferenceValue):
    pass


class TechnologyType(ReferenceValue):
    pass


class TechStandardStatus(ReferenceValue):
    pass


REFERENCE_KINDS: dict[str, type[ReferenceValue]] = {
    "confidentiality_level": ConfidentialityLevel,
    "integrity_level": IntegrityLevel,
    "availability_level": AvailabilityLevel,
    "traceability_level": TraceabilityLevel,
    "function_category": FunctionCategory,
    "usage_mode": UsageMode,
    "technology_type": TechnologyType,
    "tech_standard_status": TechStandardStatus,
}
