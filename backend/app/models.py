"""Pydantic data models. Nothing here is persisted; models only describe request,
response and in-memory shapes."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .options import BUSINESS_TYPES, CATEGORIES, GENDERS, OCCUPATIONS, STATES

ShortStr = Annotated[str, StringConstraints(max_length=700)]

RuleField = Literal[
    "state", "occupation", "annual_income_lakh", "category", "age", "gender", "business_type", "other"
]
RuleOp = Literal["eq", "in", "not_in", "lte", "gte", "lt", "gt", "between", "other"]


class Rule(BaseModel):
    """One machine-checkable (or flagged) condition from a scheme."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    field: RuleField = "other"
    op: RuleOp = "other"
    value: Any = None
    text: str = Field("", max_length=700)


class Scheme(BaseModel):
    """Structured scheme as extracted from a government document."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = Field(..., min_length=1, max_length=250)
    authority: str = Field("", max_length=250)
    summary: str = Field("", max_length=3000)
    benefits: list[ShortStr] = Field(default_factory=list, max_length=30)
    eligibility: list[Rule] = Field(default_factory=list, max_length=40)
    exclusions: list[Rule] = Field(default_factory=list, max_length=40)
    documents: list[ShortStr] = Field(default_factory=list, max_length=40)
    how_to_apply: list[ShortStr] = Field(default_factory=list, max_length=30)
    source: str = Field("", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=20)
    warnings: list[ShortStr] = Field(default_factory=list, max_length=10)
    illustrative: bool = False
    official_sources: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _assign_rule_ids(self) -> "Scheme":
        for i, rule in enumerate(self.eligibility, 1):
            if not rule.id:
                rule.id = f"r{i}"
        for i, rule in enumerate(self.exclusions, 1):
            if not rule.id:
                rule.id = f"x{i}"
        return self


class Profile(BaseModel):
    """Anonymous demographic parameters. Closed set of fields on purpose:
    there is no free-text field, so names, phone numbers or addresses cannot be submitted."""

    model_config = ConfigDict(extra="forbid")

    state: Optional[str] = Field(None, max_length=60)
    occupation: Optional[Literal[tuple(OCCUPATIONS)]] = None  # type: ignore[valid-type]
    annual_income_lakh: Optional[float] = Field(None, ge=0, le=100000)
    category: Optional[Literal[tuple(CATEGORIES)]] = None  # type: ignore[valid-type]
    age: Optional[int] = Field(None, ge=0, le=120)
    gender: Optional[Literal[tuple(GENDERS)]] = None  # type: ignore[valid-type]
    business_type: Optional[Literal[tuple(BUSINESS_TYPES)]] = None  # type: ignore[valid-type]

    @field_validator("state")
    @classmethod
    def _known_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        for name in STATES:
            if name.lower() == v.strip().lower():
                return name
        raise ValueError("Unknown state or union territory")


class RuleResult(BaseModel):
    rule_id: str
    kind: Literal["eligibility", "exclusion"]
    text: str
    # pass  = this check is fine for the user
    # fail  = this check blocks eligibility
    # check = cannot be decided automatically; the user must confirm
    status: Literal["pass", "fail", "check"]
    reason: str = ""


class MatchResult(BaseModel):
    verdict: Literal["eligible", "ineligible", "conditional"]
    results: list[RuleResult]
    missing_optional: list[str] = Field(default_factory=list)


class MatchRequest(BaseModel):
    scheme: Scheme
    profile: Profile


class ExplainRequest(BaseModel):
    scheme: Scheme
    match: MatchResult
    language: str = "en"


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2500)
    language: str = "en"


class DiscoverRequest(BaseModel):
    level: Literal["national", "state"]
    state: Optional[str] = Field(None, max_length=60)
    query: str = Field("", max_length=300)

    @model_validator(mode="after")
    def _state_rules(self) -> "DiscoverRequest":
        if self.level == "state":
            match = next((n for n in STATES if self.state and n.lower() == self.state.strip().lower()), None)
            if not match:
                raise ValueError("Please choose a state")
            self.state = match
        else:
            self.state = None
        return self


class DetailsRequest(DiscoverRequest):
    name: str = Field(..., min_length=2, max_length=200)
    url: str = Field("", max_length=500)
