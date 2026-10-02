import dataclasses

import pytest

from archimaid.domain.errors import InvalidEntity
from archimaid.domain.reference import (
    REFERENCE_KINDS,
    AvailabilityLevel,
    ConfidentialityLevel,
    FunctionCategory,
)


def test_registry_has_the_eight_catalogs():
    assert set(REFERENCE_KINDS) == {
        "confidentiality_level",
        "integrity_level",
        "availability_level",
        "traceability_level",
        "function_category",
        "usage_mode",
        "technology_type",
        "tech_standard_status",
    }


def test_value_objects_are_immutable():
    value = FunctionCategory(code="BUSINESS", label="Business")
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.label = "other"  # type: ignore[misc]


@pytest.mark.parametrize("code", ["", "  "])
def test_blank_code_is_rejected(code):
    with pytest.raises(InvalidEntity):
        FunctionCategory(code=code, label="Business")


def test_blank_label_is_rejected():
    with pytest.raises(InvalidEntity):
        FunctionCategory(code="BUSINESS", label=" ")


def test_levels_carry_a_rank():
    assert ConfidentialityLevel(code="LOW", label="Low", rank=1).rank == 1


def test_availability_hours_cannot_be_negative():
    with pytest.raises(InvalidEntity):
        AvailabilityLevel(code="LOW", label="Low", rank=1, rpo_hours=-1, rto_hours=0)
