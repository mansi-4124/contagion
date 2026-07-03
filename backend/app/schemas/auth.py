from uuid import UUID
from typing import Optional
from pydantic import BaseModel, EmailStr


class CompleteSignupRequest(BaseModel):
    company_name: str
    industry: Optional[str] = None
    country: Optional[str] = None
    full_name: Optional[str] = None


class CompleteSignupResponse(BaseModel):
    company_id: UUID
    user_id: UUID
    dataset_namespace: str
    already_existed: bool