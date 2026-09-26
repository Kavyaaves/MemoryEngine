"""Structured-output schemas for AI calls."""

from typing import Literal

from pydantic import BaseModel, Field


class ImageDescription(BaseModel):
    caption: str = ""
    people_count: int = 0
    objects: list[str] = Field(default_factory=list)
    scene: str | None = None
    text_in_image: str | None = None
    event_clues: list[str] = Field(default_factory=list)
    place_guess: str | None = None

    def as_text(self) -> str:
        parts = [self.caption]
        if self.scene:
            parts.append(f"Scene: {self.scene}.")
        if self.objects:
            parts.append("Objects: " + ", ".join(self.objects) + ".")
        if self.event_clues:
            parts.append("Event clues: " + ", ".join(self.event_clues) + ".")
        if self.place_guess:
            parts.append(f"Possibly at: {self.place_guess} (AI-inferred).")
        if self.text_in_image:
            parts.append(f"Text in image: {self.text_in_image}")
        return " ".join(p for p in parts if p)


Intent = Literal["lookup", "temporal", "count", "person", "address", "media", "summary", "multi_hop", "chit_chat"]


class QueryAnalysis(BaseModel):
    intent: Intent = "lookup"
    people: list[str] = Field(default_factory=list)
    time_start: str | None = Field(default=None, description="YYYY-MM-DD or null")
    time_end: str | None = Field(default=None, description="YYYY-MM-DD or null")
    temporal_order: Literal["first", "last"] | None = None
    address_speaker: Literal["self", "them"] | None = Field(
        default=None, description='for intent=address: "self" = how the user addresses the person, '
                                  '"them" = how the person addresses the user')
    modality: list[Literal["text", "image", "audio", "video"]] = Field(default_factory=lambda: ["text"])
    rewritten_queries: list[str] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)


class EvidenceVerdict(BaseModel):
    sufficient: bool
    confidence: Literal["high", "medium", "low", "none"] = "low"
    alternative_queries: list[str] = Field(default_factory=list)


# ---- fine-tuning phase (app/finetuning/) ----

class TaggedMessage(BaseModel):
    id: int = Field(description="the message's number in the batch, e.g. 3 for [3]")
    address_words: list[str] = Field(description="words used to address the other person, as written")


class AddressTags(BaseModel):
    """The address-tagger's output: only the messages that contain address words are listed."""

    messages: list[TaggedMessage] = Field(default_factory=list)


# ---- evaluation only (app/evaluation/) ----

class GeneratedQuestion(BaseModel):
    usable: bool = Field(description="false if the memory is too short or generic for a question")
    question: str = ""
    reference_answer: str = ""


class AnswerVerdict(BaseModel):
    correctness: Literal["correct", "partial", "wrong"]
    grounded: bool
    explanation: str = ""
