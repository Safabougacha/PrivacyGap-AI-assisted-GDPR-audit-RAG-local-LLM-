"""Step 4 - The exact shape of every answer we accept from the LLM.

Pydantic checks types and allowed values. If the model returns something
else, validation fails and the engine asks again instead of trusting it.
"""
from typing import Literal

from pydantic import BaseModel, Field


class DataOpinion(BaseModel):
    """LLM second opinion on the DATA (compared with the keyword rule)."""
    health_or_sex_life: bool
    data_description: str = Field(description="short legal wording of the data")


class PolicyMatch(BaseModel):
    """LLM points to ONE commitment of the policy, with an exact quote (or NONE)."""
    commitment: str = Field(description="'P1', 'P2'... or 'NONE'")
    quote: str = Field(default="", description="exact words copied from that commitment")


class Writeup(BaseModel):
    """LLM-written justification and recommendation, grounded in passages."""
    justification: str
    recommendation: str


class FlowResult(BaseModel):
    """Everything kept for one audited flow (report + evaluation)."""
    flow_id: str
    flow: dict
    special_category: bool
    special_reason: str
    llm_opinion: DataOpinion
    needs_human_review: bool          # rule and LLM disagree on the data type
    contradicts_policy: bool
    policy_reference: str
    policy_explanation: str
    risk_level: Literal["high", "medium", "low"]
    risk_reasons: list[str]
    cited_articles: list[int]         # articles concerned AND found by retrieval
    retrieval_misses: list[int]       # articles concerned but NOT retrieved
    retrieved_articles: list[int]
    justification: str
    recommendation: str
    seconds: float
