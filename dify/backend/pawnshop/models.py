"""Bounded, strict wire contracts. Model proposals never carry service identity."""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator, model_validator

Identity = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256, strip_whitespace=True)]
CardText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=250)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Card(StrictModel):
    name: CardText
    appearance: CardText
    trait: CardText
    meaning: CardText
    inscription: CardText
    quest: CardText


class Proposal(StrictModel):
    action: Literal["appraise", "correct", "pawn", "revisit", "shelf", "retrieve", "chat"]
    item_id: Annotated[str, StringConstraints(strict=True, max_length=256)] = ""
    expected_version: Annotated[StrictInt, Field(ge=0)] = 0
    reply: Annotated[str, StringConstraints(strict=True, max_length=2000)] = ""
    reported_event: Annotated[str, StringConstraints(strict=True, max_length=600)] = ""
    card: Card | None = None

    @model_validator(mode="after")
    def reported_event_is_revisit_only(self):
        if self.reported_event and self.action != "revisit":
            raise ValueError("reported_event is only valid for revisit")
        # The pinned remember API limits text to 8192 UTF-8 bytes. Leave room
        # for immutable event identity, notices and the actual Source citation.
        card_bytes = len(self.card.model_dump_json().encode("utf-8")) if self.card else 0
        event_bytes = len(json.dumps(self.reported_event, ensure_ascii=False).encode("utf-8")) - 2
        if card_bytes + event_bytes > 6500:
            raise ValueError("card and reported_event exceed memory byte budget")
        return self


class PrepareRequest(StrictModel):
    user_id: Identity
    conversation_id: Identity
    turn_id: Identity
    query: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=6000)]


class ActRequest(StrictModel):
    user_id: Identity
    turn_id: Identity
    proposal: Proposal

    @field_validator("proposal", mode="before")
    @classmethod
    def decode_proposal(cls, value):
        if isinstance(value, str):
            if len(value.encode("utf-8")) > 18000:
                raise ValueError("proposal too large")
            try:
                value = json.loads(value)
            except (ValueError, RecursionError) as error:
                raise ValueError("proposal must contain exactly one JSON object") from error
        if not isinstance(value, (dict, Proposal)):
            raise ValueError("proposal must be an object")
        return value
