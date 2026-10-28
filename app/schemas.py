from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import ConsultationStatus, Role


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    role: Role
    mfa_enabled: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DoctorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    specialty: str = Field(min_length=2, max_length=120)
    bio: str = Field(default="", max_length=4000)


class DoctorOut(DoctorCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class SlotCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class SlotOut(SlotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    doctor_id: str
    is_booked: bool


class BookingCreate(BaseModel):
    slot_id: str
    notes: str = Field(default="", max_length=4000)


class ConsultationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    doctor_id: str
    slot_id: str
    starts_at: datetime
    status: ConsultationStatus
    notes: str


class PrescriptionCreate(BaseModel):
    medicine: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=4000)
