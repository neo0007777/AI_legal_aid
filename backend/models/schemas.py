from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime


# ─── Auth ────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: Optional[str] = "user"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    email: str
    role: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Workflow / Todo ──────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    document_type: Optional[str] = None
    is_required: Optional[bool] = True
    order_index: Optional[int] = 0
    due_date: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: str
    workflow_id: str
    title: str
    description: Optional[str]
    document_type: Optional[str]
    is_completed: bool
    is_required: bool
    order_index: int
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowCreate(BaseModel):
    title: str
    company_a: Optional[str] = None
    company_b: Optional[str] = None
    description: Optional[str] = None


class WorkflowResponse(BaseModel):
    id: str
    user_id: str
    title: str
    company_a: Optional[str]
    company_b: Optional[str]
    description: Optional[str]
    status: str
    created_at: datetime
    tasks: Optional[List[TaskResponse]] = []

    class Config:
        from_attributes = True


class GenerateWorkflowRequest(BaseModel):
    title: str
    company_a: Optional[str] = None
    company_b: Optional[str] = None
    work_description: str


# ─── Compliance ───────────────────────────────────────

class ComplianceAlertResponse(BaseModel):
    id: str
    title: str
    description: str
    law_area: str
    severity: str
    source_url: Optional[str]
    fetched_at: datetime

    class Config:
        from_attributes = True


class ComplianceCheckRequest(BaseModel):
    description: str


class ComplianceCheckResponse(BaseModel):
    is_compliant: bool
    issues: List[str]
    recommendations: List[str]
    relevant_laws: List[str]


# ─── Documents ────────────────────────────────────────

class SearchSource(BaseModel):
    filename: str
    category: str
    score: float


class DraftRequest(BaseModel):
    description: str
    category: Optional[str] = None
    n_results: Optional[int] = 5
    structured_input: Optional[dict] = None    # Structured field data from frontend
    template_id: Optional[str] = None          # Template ID (e.g. "bail", "rent")


class DraftResponse(BaseModel):
    description: str
    draft: str
    sources: List[SearchSource]
    review: Optional[dict] = None              # 2-pass review report
    fact_manifest: Optional[dict] = None       # What was provided vs. missing
    provenance_report: Optional[dict] = None   # Provenance of each assertion
    procedural_posture: Optional[dict] = None  # Verified procedural posture & governing provision
    ground_traceability: Optional[List[dict]] = None # Internal ground-by-ground verification record
    statute_verification: Optional[dict] = None # Statutory provision audit against India Code


class StatuteVerificationRequest(BaseModel):
    draft_text: str
    category: Optional[str] = None


class ContradictionRequest(BaseModel):
    document_a: str
    document_b: str


class ContradictionPoint(BaseModel):
    clause: str
    party_a_position: str
    party_b_position: str
    suggested_resolution: str


class ContradictionResponse(BaseModel):
    total_contradictions: int
    contradictions: List[ContradictionPoint]
    overall_compatibility: str


# ─── Case Search ─────────────────────────────────────

class LiveCase(BaseModel):
    title: str
    link: str
    snippet: str
    source: str
    keywords: List[str] = []


class CaseSearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 5


class CaseSearchResponse(BaseModel):
    query: str
    answer: str
    sources: List[SearchSource]
    live_cases: List[LiveCase]


class KeywordSearchRequest(BaseModel):
    keyword: str
    n_results: Optional[int] = 5


# ─── Legal Aid ────────────────────────────────────────

class LegalAidRequest(BaseModel):
    question: str
    n_results: Optional[int] = 3
    structure_mode: Optional[str] = None  # standard | executive_brief | irac | bullet_points | custom
    custom_instructions: Optional[str] = None
    save_to_memory: Optional[bool] = False


class LegalAidMemoryRequest(BaseModel):
    structure_mode: str = "standard"  # standard | executive_brief | irac | bullet_points | custom
    structure_title: Optional[str] = "Standard Judicial"
    custom_instructions: Optional[str] = None


class LegalAidMemoryResponse(BaseModel):
    structure_mode: str
    structure_title: str
    custom_instructions: Optional[str] = None
    updated_at: Optional[datetime] = None


class LegalAidResponse(BaseModel):
    question: str
    answer: str
    sources: List[SearchSource]
    requires_upgrade: Optional[bool] = False
    upgrade_tier: Optional[str] = None
    applied_structure_mode: Optional[str] = "standard"
    applied_structure_title: Optional[str] = "Standard Judicial"
    memory_active: Optional[bool] = False
    custom_instructions: Optional[str] = None


# ─── Correction Memory & Translation ──────────────────

class FlagCorrectionRequest(BaseModel):
    correct_output: str  # "Verified" | "Mismatch" | "Not found in indexed corpus"
    note: Optional[str] = None


class RenderLanguageRequest(BaseModel):
    language: str  # "hindi" | "hinglish"