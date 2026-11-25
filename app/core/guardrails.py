import re
from typing import Tuple, List, Optional
from app.schemas.triage_schema import (
    PatientTriageRequest,
    TriageLevel,
    PaymentType,
    AdminGuidance,
)


def anonymize_pii(text: str) -> str:
    """Menyamarkan nomor NIK (16 digit) atau nomor telepon sebelum dikirim ke LLM."""
    text = re.sub(r"\b\d{16}\b", "[NIK_REDACTED]", text)
    text = re.sub(r"\b(\+62|62|0)8[1-9][0-9]{6,10}\b", "[PHONE_REDACTED]", text)
    return text


def evaluate_vital_red_flags(req: PatientTriageRequest) -> Tuple[Optional[TriageLevel], List[str]]:
    """
    Aturan klinis mutlak (hard-coded safety rules).
    Jika tanda vital melewati ambang kritis, sistem memaksa status EMERGENCY.
    """
    v = req.vitals
    red_flags: List[str] = []
    forced_level = None

    if v.spo2 is not None and v.spo2 < 90:
        red_flags.append(f"Hipoksia berat: SpO2 {v.spo2}% (< 90%)")
        forced_level = TriageLevel.EMERGENCY

    if v.systolic_bp is not None and (v.systolic_bp < 90 or v.systolic_bp >= 180):
        red_flags.append(f"Tekanan darah kritis: Sistolik {v.systolic_bp} mmHg")
        forced_level = TriageLevel.EMERGENCY

    if v.heart_rate is not None and (v.heart_rate < 45 or v.heart_rate > 130):
        red_flags.append(f"Denyut nadi ekstrem: {v.heart_rate} x/menit")
        forced_level = TriageLevel.EMERGENCY

    if v.respiratory_rate is not None and (v.respiratory_rate < 10 or v.respiratory_rate > 30):
        red_flags.append(f"Gangguan laju napas berat: {v.respiratory_rate} x/menit")
        forced_level = TriageLevel.EMERGENCY

    if v.gcs is not None and v.gcs <= 12:
        red_flags.append(f"Penurunan kesadaran signifikan: GCS {v.gcs}")
        forced_level = TriageLevel.EMERGENCY

    if v.temperature_c is not None and v.temperature_c >= 40.0:
        red_flags.append(f"Hiperpireksia: Suhu {v.temperature_c}°C")
        if forced_level != TriageLevel.EMERGENCY:
            forced_level = TriageLevel.HIGH_URGENCY

    return forced_level, red_flags


def evaluate_bpjs_admin(req: PatientTriageRequest, final_triage: TriageLevel) -> AdminGuidance:
    """Menentukan alur pendaftaran & penjaminan BPJS berdasarkan urgensi klinis."""
    admin = req.admin_info
    is_emergency = final_triage == TriageLevel.EMERGENCY or admin.is_emergency_criteria

    if admin.payment_type != PaymentType.BPJS:
        route = "Instalasi Gawat Darurat (IGD)" if is_emergency else "Pendaftaran Poliklinik Rawat Jalan"
        return AdminGuidance(
            service_route=route,
            bpjs_eligibility_note=f"Pasien menggunakan penjaminan {admin.payment_type.value}.",
            required_documents=["Kartu Identitas (KTP/KIA)", "Kartu Asuransi (jika ada)"],
        )

    if is_emergency:
        return AdminGuidance(
            service_route="IGD - Jalur Penjaminan Gawat Darurat BPJS (Tanpa Rujukan)",
            bpjs_eligibility_note=(
                "Memenuhi kriteria gawat darurat. Dijamin BPJS Kesehatan langsung di IGD "
                "tanpa memerlukan surat rujukan dari FKTP."
            ),
            required_documents=["KTP / Kartu Keluarga", "Kartu JKN-KIS / Mobile JKN"],
        )

    if admin.has_fk1_referral and not admin.referral_expired:
        return AdminGuidance(
            service_route="Loket SEP Rawat Jalan / Anjungan Mandiri (APM)",
            bpjs_eligibility_note="Rujukan FKTP aktif. Dapat diterbitkan Surat Eligibilitas Peserta (SEP) poliklinik.",
            required_documents=["Surat Rujukan FKTP Aktif", "KTP", "Kartu JKN-KIS / Bukti Antrean Mobile JKN"],
        )

    return AdminGuidance(
        service_route="Meja Informasi / Edukasi Rujukan FKTP",
        bpjs_eligibility_note=(
            "Kondisi stabil (non-gawat darurat) namun tidak memiliki rujukan FKTP aktif. "
            "Jika tetap mendaftar di poli RS tanpa rujukan, layanan tidak ditanggung BPJS (pasien umum)."
        ),
        required_documents=["Surat Rujukan dari Puskesmas/Klinik Pratama (FKTP) sebelum berobat"],
    )
