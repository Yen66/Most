from enum import StrEnum


class Unit(StrEnum):
    PIECE = "шт"
    METER = "м"
    LINEAR_METER = "п.м."
    SQUARE_METER = "м2"
    CUBIC_METER = "м3"
    UNIT = "ед."


class ContractType(StrEnum):
    GOVERNMENT = "government"
    COMMERCIAL = "commercial"
    UNKNOWN = "unknown"


class SourceType(StrEnum):
    DOCUMENT = "document"
    USER_INPUT = "user_input"
    REFERENCE = "reference"
    ESTIMATE = "estimate"
    ASSUMPTION = "assumption"
    CALCULATED = "calculated"


class Confidence(StrEnum):
    EXACT = "exact"
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"
    ASSUMPTION = "assumption"


class NoteType(StrEnum):
    PERIOD = "period"
    RESOURCE_PLAN = "resource_plan"
    REVERSE_SCHEME = "reverse_scheme"
    WORK_REGIME = "work_regime"
