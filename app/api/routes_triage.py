import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from app.core.config import settings
from app.core.guardrails import (
    anonymize_pii,
    evaluate_vital_red_flags,
    evaluate_bpjs_admin,
)
from app.rag.ingest import ingest_sops
from app.rag.retriever import retrieve_relevant_sops
from app.rag.prompts import SYSTEM_TRIAGE_PROMPT
from app.schemas.triage_schema import (
    Citation,
    PatientTriageRequest,
    PatientTriageResponse,
    TriageLevel,
)

router = APIRouter(prefix="/api/v1", tags=["MedTriage"])


def _build_local_fallback_triage(
    payload: PatientTriageRequest,
    clean_complaint: str,
    clean_history: str,
    forced_level: Optional[TriageLevel],
    vital_red_flags: List[str],
    citations: List[Citation],
) -> dict:
    """Fallback triase lokal gratis saat LLM API tidak tersedia / kuota habis."""
    text_lower = f"{clean_complaint} {clean_history}".lower()
    inferred_red_flags: List[str] = list(vital_red_flags)

    emergency_keywords = [
        "nyeri dada",
        "tertindih",
        "menjalar",
        "keringat dingin",
        "sesak napas",
        "tidak sadar",
        "pingsan",
        "kejang",
        "stroke",
        "pendarahan hebat",
    ]
    urgent_keywords = [
        "demam tinggi",
        "muntah terus",
        "nyeri hebat",
        "dehidrasi",
        "hipertensi",
        "tekanan darah tinggi",
        "luka terbuka",
    ]

    for kw in emergency_keywords:
        if kw in text_lower and f"Keluhan darurat terdeteksi: {kw}" not in inferred_red_flags:
            inferred_red_flags.append(f"Keluhan darurat terdeteksi: {kw}")

    if forced_level:
        level = forced_level
    elif any(kw in text_lower for kw in emergency_keywords):
        level = TriageLevel.EMERGENCY
    elif any(kw in text_lower for kw in urgent_keywords):
        level = TriageLevel.HIGH_URGENCY
    else:
        level = TriageLevel.STANDARD

    if level == TriageLevel.EMERGENCY:
        polyclinic = "Instalasi Gawat Darurat (IGD)"
        initial_steps = [
            "Segera arahkan pasien ke zona triase/resusitasi IGD tanpa antre poliklinik.",
            "Lakukan penilaian ulang tanda vital (TD, nadi, frekuensi napas, SpO2) dan pasang akses IV bila diindikasikan.",
            "Rekam EKG 12 sadapan dan beri oksigen sesuai indikasi klinis serta SOP IGD.",
        ]
    elif level == TriageLevel.HIGH_URGENCY:
        polyclinic = "Instalasi Gawat Darurat (IGD) / Poliklinik Prioritas"
        initial_steps = [
            "Prioritaskan pemeriksaan awal oleh perawat/dokter jaga dan pantau tanda vital berkala.",
            "Evaluasi riwayat penyakit penyerta/alergi serta kebutuhan pemeriksaan penunjang awal.",
        ]
    else:
        polyclinic = "Poliklinik Umum"
        initial_steps = [
            "Arahkan pasien ke pendaftaran rawat jalan dan poliklinik terkait.",
            "Catat tanda vital lengkap serta riwayat keluhan sebelum konsultasi dokter.",
        ]

    sop_ref = (
        f"Acuan SOP: {citations[0].document} ({citations[0].section})."
        if citations
        else "Evaluasi dilakukan menggunakan aturan klinis & guardrail lokal (mode fallback)."
    )

    summary = (
        f"[Mode Fallback Lokal - Tanpa LLM API] Pasien {payload.patient_alias} usia {payload.age} tahun "
        f"({payload.gender}) dengan keluhan utama: '{clean_complaint}'. Riwayat: {clean_history}. "
        f"Tingkat triase ditetapkan ke {level.value}. {sop_ref}"
    )

    follow_up_questions = [
        "Sejak kapan keluhan dirasakan dan apakah intensitasnya semakin memberat?",
        "Apakah ada gejala penyerta seperti sesak napas, pusing, mual/muntah, atau nyeri menjalar?",
        "Apakah pasien sedang mengonsumsi obat rutin atau memiliki alergi obat/makanan tertentu?",
    ]

    return {
        "triage_level": level.value,
        "recommended_polyclinic": polyclinic,
        "summary": summary,
        "red_flags_detected": inferred_red_flags,
        "recommended_initial_steps": initial_steps,
        "follow_up_questions": follow_up_questions,
    }


@router.post("/sops/reindex")
def reindex_sops():
    """Endpoint untuk memuat ulang dokumen SOP ke dalam Vector Database."""
    try:
        total = ingest_sops()
        return {"status": "success", "indexed_chunks": total}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal reindex SOP ({type(exc).__name__}): {exc}")


@router.post("/triage", response_model=PatientTriageResponse)
def run_patient_triage(payload: PatientTriageRequest):
    try:
        clean_complaint = anonymize_pii(payload.chief_complaint or "")
        clean_history = anonymize_pii(payload.medical_history or "Tidak ada")

        forced_level, vital_red_flags = evaluate_vital_red_flags(payload)

        search_query = (
            f"Keluhan: {clean_complaint}. Riwayat: {clean_history}. "
            f"Vital: {payload.vitals.model_dump()}"
        )
        try:
            citations = retrieve_relevant_sops(search_query, top_k=3) or []
        except Exception:
            citations = []

        sop_context = (
            "\n\n".join(
                [f"[{c.document} - {c.section}]: {c.snippet}" for c in citations]
            )
            or "Tidak ada SOP spesifik ditemukan."
        )

        llm_data = None
        if settings.openai_api_key and settings.openai_api_key.startswith("sk-"):
            client = OpenAI(api_key=settings.openai_api_key)
            user_prompt = f"""
Data Pasien:
- Alias/Antrean: {payload.patient_alias}
- Usia/Gender: {payload.age} tahun / {payload.gender}
- Keluhan Utama: {clean_complaint}
- Riwayat Penyakit: {clean_history}
- Tanda Vital: {payload.vitals.model_dump()}
- Red Flags Vital Terdeteksi Sistem: {vital_red_flags}

Referensi SOP Rumah Sakit:
{sop_context}
"""
            try:
                completion = client.chat.completions.create(
                    model=settings.llm_model,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": SYSTEM_TRIAGE_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                llm_data = json.loads(completion.choices[0].message.content)
            except Exception:
                llm_data = None

        if not isinstance(llm_data, dict):
            llm_data = _build_local_fallback_triage(
                payload=payload,
                clean_complaint=clean_complaint,
                clean_history=clean_history,
                forced_level=forced_level,
                vital_red_flags=vital_red_flags,
                citations=citations,
            )

        raw_level = str(llm_data.get("triage_level", "STANDARD")).upper()
        llm_level = (
            TriageLevel(raw_level)
            if raw_level in TriageLevel._value2member_map_
            else TriageLevel.STANDARD
        )
        final_level = llm_level
        guardrail_triggered = False

        priority_rank = {
            TriageLevel.STANDARD: 1,
            TriageLevel.HIGH_URGENCY: 2,
            TriageLevel.EMERGENCY: 3,
        }

        if forced_level and priority_rank[forced_level] > priority_rank[llm_level]:
            final_level = forced_level
            guardrail_triggered = True

        combined_red_flags = list(
            dict.fromkeys(vital_red_flags + (llm_data.get("red_flags_detected") or []))
        )
        admin_guidance = evaluate_bpjs_admin(payload, final_level)

        return PatientTriageResponse(
            triage_level=final_level,
            recommended_polyclinic=(
                "Instalasi Gawat Darurat (IGD)"
                if final_level == TriageLevel.EMERGENCY
                else llm_data.get("recommended_polyclinic", "Poliklinik Umum")
            ),
            summary=llm_data.get("summary", ""),
            red_flags_detected=combined_red_flags,
            recommended_initial_steps=llm_data.get("recommended_initial_steps") or [],
            follow_up_questions=llm_data.get("follow_up_questions") or [],
            admin_guidance=admin_guidance,
            citations=citations,
            guardrail_triggered=guardrail_triggered,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")