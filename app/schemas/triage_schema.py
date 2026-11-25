from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TriageLevel(str, Enum):
    EMERGENCY = "EMERGENCY"
    HIGH_URGENCY = "HIGH_URGENCY"
    STANDARD = "STANDARD"


class PaymentType(str, Enum):
    BPJS = "BPJS"
    UMUM = "UMUM"
    ASURANSI_SWASTA = "ASURANSI_SWASTA"


class VitalSigns(BaseModel):
    systolic_bp: Optional[int] = Field(None, ge=40, le=300, description="Tekanan darah sistolik (mmHg)")
    diastolic_bp: Optional[int] = Field(None, ge=20, le=200, description="Tekanan darah diastolik (mmHg)")
    heart_rate: Optional[int] = Field(None, ge=20, le=250, description="Denyut nadi (x/menit)")
    respiratory_rate: Optional[int] = Field(None, ge=5, le=60, description="Laju napas (x/menit)")
    temperature_c: Optional[float] = Field(None, ge=30.0, le=43.0, description="Suhu tubuh (°C)")
    spo2: Optional[int] = Field(None, ge=50, le=100, description="Saturasi oksigen (%)")
    gcs: Optional[int] = Field(15, ge=3, le=15, description="Glasgow Coma Scale (3-15)")


class AdminBPJSInfo(BaseModel):
    payment_type: PaymentType = PaymentType.BPJS
    has_fk1_referral: bool = Field(False, description="Apakah membawa surat rujukan FKTP (Puskesmas/Klinik)?")
    referral_expired: bool = Field(False, description="Apakah masa berlaku rujukan (>90 hari) sudah habis?")
    is_emergency_criteria: bool = Field(False, description="Indikasi gawat darurat sesuai kriteria BPJS")


class PatientTriageRequest(BaseModel):
    patient_alias: str = Field(..., description="Inisial/ID anonim pasien (tanpa NIK/nama lengkap demi privasi)")
    age: int = Field(..., ge=0, le=120)
    gender: str = Field(..., pattern="^(L|P)$")
    chief_complaint: str = Field(..., min_length=5, description="Keluhan utama pasien")
    medical_history: Optional[str] = Field(None, description="Riwayat penyakit kronis / alergi obat")
    vitals: VitalSigns
    admin_info: AdminBPJSInfo = AdminBPJSInfo()


class Citation(BaseModel):
    document: str
    section: str
    snippet: str


class AdminGuidance(BaseModel):
    service_route: str
    bpjs_eligibility_note: str
    required_documents: List[str]


class PatientTriageResponse(BaseModel):
    triage_level: TriageLevel
    recommended_polyclinic: str
    summary: str
    red_flags_detected: List[str]
    recommended_initial_steps: List[str]
    follow_up_questions: List[str]
    admin_guidance: AdminGuidance
    citations: List[Citation]
    guardrail_triggered: bool = False
    clinical_disclaimer: str = (
        "PERINGATAN: Hasil ini merupakan pendukung keputusan klinis & administrasi berbasis AI. "
        "Penetapan triase akhir, diagnosis, dan tindakan medis wajib dilakukan oleh dokter/perawat berlisensi."
    )
