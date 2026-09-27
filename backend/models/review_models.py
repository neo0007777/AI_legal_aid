from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ReviewRequest(BaseModel):
    draft: str = Field(..., description="Raw text of the legal draft to review")
    document_type: Optional[str] = Field(None, description="Optional pre-classified document type")


class MissingField(BaseModel):
    placeholder: str
    description: str
    line_number: Optional[int] = None


class ReviewIssue(BaseModel):
    id: str
    category: str  # "critical", "warning", "suggestion"
    title: str
    description: str
    location: Optional[str] = None
    suggested_fix: Optional[str] = None


class ReviewResponse(BaseModel):
    document_type: str
    overall_score: int
    risk_level: str  # "Low", "Medium", "High"
    summary: str
    critical: List[ReviewIssue] = []
    warnings: List[ReviewIssue] = []
    suggestions: List[ReviewIssue] = []
    missing_sections: List[str] = []
    missing_fields: List[MissingField] = []
    extracted_text: Optional[str] = None


class FixRequest(BaseModel):
    draft: str = Field(..., description="Original draft text to fix")
    issues: List[Dict[str, Any]] = Field(default=[], description="Detected issues to fix")
    missing_sections: List[str] = Field(default=[], description="Missing sections to insert")
    missing_fields: List[Dict[str, Any]] = Field(default=[], description="Missing placeholders to address")


class FixResponse(BaseModel):
    corrected_draft: str
    changes_made: List[str] = []
