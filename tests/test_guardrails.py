from app.core.guardrails import evaluate_vital_red_flags, anonymize_pii, evaluate_bpjs_admin
from app.schemas.triage_schema import (
    PatientTriageRequest,
    VitalSigns,
    AdminBPJSInfo,
    TriageLevel,
    PaymentType,
)


def test_hypoxia_triggers_emergency():
    req = PatientTriageRequest(
        patient_alias="TEST-01",
        age=60,
        gender="L",
        chief_complaint="Sesak napas sejak pagi",
        vitals=VitalSigns(spo2=86, systolic_bp=120, heart_rate=105),
    )
    level, flags = evaluate_vital_red_flags(req)
    assert level == TriageLevel.EMERGENCY
    assert any("Hipoksia" in f for f in flags)


def test_bpjs_emergency_bypasses_referral():
    req = PatientTriageRequest(
        patient_alias="TEST-02",
        age=45,
        gender="P",
        chief_complaint="Nyeri dada hebat",
        vitals=VitalSigns(spo2=88),
        admin_info=AdminBPJSInfo(payment_type=PaymentType.BPJS, has_fk1_referral=False),
    )
    admin = evaluate_bpjs_admin(req, TriageLevel.EMERGENCY)
    assert "Tanpa Rujukan" in admin.service_route


def test_pii_anonymization():
    raw = "Pasien NIK 3273012345678901 dengan nomor HP 081234567890"
    cleaned = anonymize_pii(raw)
    assert "3273012345678901" not in cleaned
    assert "081234567890" not in cleaned
