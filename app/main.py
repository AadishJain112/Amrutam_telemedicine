import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import AuditLog, AvailabilitySlot, Consultation, ConsultationStatus, Doctor, IdempotencyKey, Prescription, Role, User
from app.schemas import BookingCreate, ConsultationOut, DoctorCreate, DoctorOut, LoginRequest, PrescriptionCreate, SlotCreate, SlotOut, Token, UserCreate, UserOut
from app.security import create_access_token, get_current_user, hash_password, require_roles, verify_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("telemedicine")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=get_settings().app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    logger.info("%s %s %s %.2fms", request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    return response


def audit(db: Session, actor_id: str | None, action: str, resource_type: str, resource_id: str, metadata: dict | None = None):
    db.add(AuditLog(actor_id=actor_id, action=action, resource_type=resource_type, resource_id=resource_id, metadata_json=json.dumps(metadata or {})))


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}


@app.post("/v1/auth/register", response_model=UserOut, status_code=201, tags=["auth"])
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password), role=Role.patient)
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user.id, "user.registered", "user", user.id)
    db.commit()
    return user


@app.post("/v1/auth/login", response_model=Token, tags=["auth"])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return Token(access_token=create_access_token(user))


@app.post("/v1/doctors", response_model=DoctorOut, status_code=201, tags=["doctors"])
def create_doctor(payload: DoctorCreate, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    doctor_user = User(email=f"doctor-{payload.name.lower().replace(' ', '-')}-{user.id[:8]}@internal", password_hash=hash_password("temporary-disabled-account"), role=Role.doctor, is_active=False)
    db.add(doctor_user)
    db.flush()
    doctor = Doctor(user_id=doctor_user.id, name=payload.name, specialty=payload.specialty, bio=payload.bio)
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    audit(db, user.id, "doctor.created", "doctor", doctor.id)
    db.commit()
    return doctor


@app.get("/v1/doctors", response_model=list[DoctorOut], tags=["doctors"])
def search_doctors(specialty: str | None = Query(default=None, max_length=120), db: Session = Depends(get_db)):
    query = select(Doctor).order_by(Doctor.name)
    if specialty:
        query = query.where(Doctor.specialty.ilike(f"%{specialty}%"))
    return list(db.scalars(query).all())


@app.post("/v1/doctors/{doctor_id}/slots", response_model=SlotOut, status_code=201, tags=["booking"])
def create_slot(doctor_id: str, payload: SlotCreate, user: User = Depends(require_roles(Role.doctor)), db: Session = Depends(get_db)):
    doctor = db.get(Doctor, doctor_id)
    if not doctor or doctor.user_id != user.id:
        raise HTTPException(status_code=404, detail="Doctor not found")
    slot = AvailabilitySlot(doctor_id=doctor_id, starts_at=payload.starts_at, ends_at=payload.ends_at)
    db.add(slot)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Overlapping or duplicate slot") from exc
    db.refresh(slot)
    return slot


@app.get("/v1/doctors/{doctor_id}/slots", response_model=list[SlotOut], tags=["booking"])
def list_slots(doctor_id: str, db: Session = Depends(get_db)):
    return list(db.scalars(select(AvailabilitySlot).where(AvailabilitySlot.doctor_id == doctor_id, AvailabilitySlot.is_booked.is_(False)).order_by(AvailabilitySlot.starts_at)).all())


@app.post("/v1/consultations", response_model=ConsultationOut, status_code=201, tags=["booking"])
def book_consultation(payload: BookingCreate, request: Request, user: User = Depends(require_roles(Role.patient)), db: Session = Depends(get_db)):
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    if len(idempotency_key) > 255:
        raise HTTPException(status_code=400, detail="Idempotency-Key is too long")
    previous = db.scalar(select(IdempotencyKey).where(IdempotencyKey.user_id == user.id, IdempotencyKey.key == idempotency_key))
    if previous:
        return db.get(Consultation, previous.consultation_id)
    slot = db.scalar(select(AvailabilitySlot).where(AvailabilitySlot.id == payload.slot_id).with_for_update())
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.is_booked:
        raise HTTPException(status_code=409, detail="Slot is already booked")
    slot.is_booked = True
    consultation = Consultation(patient_id=user.id, doctor_id=slot.doctor_id, slot_id=slot.id, starts_at=slot.starts_at, notes=payload.notes)
    db.add(consultation)
    db.flush()
    db.add(IdempotencyKey(user_id=user.id, key=idempotency_key, consultation_id=consultation.id))
    audit(db, user.id, "consultation.booked", "consultation", consultation.id, {"idempotency_key": idempotency_key})
    db.commit()
    db.refresh(consultation)
    return consultation


@app.get("/v1/consultations", response_model=list[ConsultationOut], tags=["consultations"])
def list_consultations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(Consultation)
    if user.role == Role.patient:
        query = query.where(Consultation.patient_id == user.id)
    elif user.role == Role.doctor:
        query = query.where(Consultation.doctor_id == user.doctor.id if user.doctor else False)
    return list(db.scalars(query.order_by(Consultation.starts_at.desc())).all())


@app.post("/v1/consultations/{consultation_id}/prescriptions", status_code=201, tags=["consultations"])
def prescribe(consultation_id: str, payload: PrescriptionCreate, user: User = Depends(require_roles(Role.doctor)), db: Session = Depends(get_db)):
    consultation = db.get(Consultation, consultation_id)
    if not consultation or not user.doctor or consultation.doctor_id != user.doctor.id:
        raise HTTPException(status_code=404, detail="Consultation not found")
    prescription = Prescription(consultation_id=consultation_id, **payload.model_dump())
    db.add(prescription)
    consultation.status = ConsultationStatus.completed
    audit(db, user.id, "prescription.created", "consultation", consultation_id)
    db.commit()
    return {"id": prescription.id, "status": "created"}
