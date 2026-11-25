import requests
import streamlit as st

API_URL = "http://localhost:8000/api/v1"

st.set_page_config(page_title="MedTriage Copilot RS", layout="wide")
st.title("🏥 MedTriage & Clinical Copilot")
st.caption("Asisten Triase Klinis IGD, Rawat Jalan, & Verifikasi Alur BPJS Berbasis SOP RS")

with st.sidebar:
    st.header("Manajemen Knowledge Base")
    if st.button("🔄 Re-index Dokumen SOP"):
        try:
            res = requests.post(f"{API_URL}/sops/reindex", timeout=30)
            if res.ok:
                st.success(f"Berhasil mengindeks {res.json().get('indexed_chunks', 0)} bagian SOP.")
            else:
                st.error(f"Gagal melakukan indexing SOP ({res.status_code}): {res.text}")
        except requests.RequestException as exc:
            st.error(f"Tidak dapat terhubung ke backend API: {exc}")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("1. Input Triase & Pendaftaran")
    patient_alias = st.text_input("ID Anonim / No. Antrean", value="IGD-2026-001")
    c_age, c_gen = st.columns(2)
    age = c_age.number_input("Usia (tahun)", min_value=0, max_value=120, value=54)
    gender = c_gen.selectbox("Jenis Kelamin", ["L", "P"])

    chief_complaint = st.text_area(
        "Keluhan Utama",
        value="Nyeri dada seperti tertindih sejak 30 menit lalu, menjalar ke lengan kiri dan keringat dingin.",
    )
    medical_history = st.text_input("Riwayat Penyakit / Alergi", value="Hipertensi tidak terkontrol")

    st.markdown("**Tanda Vital (Vital Signs)**")
    v1, v2, v3 = st.columns(3)
    sbp = v1.number_input("Sistolik (mmHg)", value=155)
    dbp = v2.number_input("Diastolik (mmHg)", value=95)
    hr = v3.number_input("Nadi (x/mnt)", value=112)

    v4, v5, v6 = st.columns(3)
    rr = v4.number_input("Napas (x/mnt)", value=24)
    temp = v5.number_input("Suhu (°C)", value=36.8, step=0.1)
    spo2 = v6.number_input("SpO2 (%)", value=93)

    st.markdown("**Informasi Penjaminan / BPJS**")
    payment_type = st.selectbox("Jenis Penjamin", ["BPJS", "UMUM", "ASURANSI_SWASTA"])
    has_referral = st.checkbox("Membawa Surat Rujukan FKTP Aktif", value=False)
    referral_expired = st.checkbox("Rujukan Sudah Kedaluwarsa (>90 hari)", value=False)

    submit = st.button("Analisis Triase & Alur Layanan", type="primary", use_container_width=True)

with col2:
    st.subheader("2. Hasil Keputusan Klinis & Administrasi")
    if submit:
        payload = {
            "patient_alias": patient_alias,
            "age": int(age),
            "gender": gender,
            "chief_complaint": chief_complaint,
            "medical_history": medical_history,
            "vitals": {
                "systolic_bp": sbp,
                "diastolic_bp": dbp,
                "heart_rate": hr,
                "respiratory_rate": rr,
                "temperature_c": temp,
                "spo2": spo2,
                "gcs": 15,
            },
            "admin_info": {
                "payment_type": payment_type,
                "has_fk1_referral": has_referral,
                "referral_expired": referral_expired,
                "is_emergency_criteria": False,
            },
        }
        try:
            with st.spinner("Menganalisis tanda vital & mencocokkan SOP rumah sakit..."):
                resp = requests.post(f"{API_URL}/triage", json=payload, timeout=60)
        except requests.RequestException as exc:
            st.error(f"Gagal menghubungi server FastAPI di {API_URL}/triage: {exc}")
            st.stop()

        if resp.ok:
            data = resp.json()
            level = data.get("triage_level", "STANDARD")
            polyclinic = data.get("recommended_polyclinic", "Poliklinik Umum")

            if level == "EMERGENCY":
                st.error(f"🚨 TINGKAT TRIASE: {level} | Tujuan: {polyclinic}")
            elif level == "HIGH_URGENCY":
                st.warning(f"⚠️ TINGKAT TRIASE: {level} | Tujuan: {polyclinic}")
            else:
                st.success(f"✅ TINGKAT TRIASE: {level} | Tujuan: {polyclinic}")

            if data.get("guardrail_triggered"):
                st.info("🛡️ Clinical Safety Guardrail aktif: Status dinaikkan otomatis berdasarkan ambang tanda vital.")

            st.write("**Ringkasan Klinis:**", data.get("summary", ""))

            if data.get("red_flags_detected"):
                st.markdown("**🚩 Red Flags Terdeteksi:**")
                for rf in data["red_flags_detected"]:
                    st.markdown(f"- {rf}")

            st.markdown("**🩺 Langkah Awal Keperawatan (Sesuai SOP):**")
            for step in data.get("recommended_initial_steps", []):
                st.markdown(f"- {step}")

            st.markdown("**❓ Pertanyaan Anamnesis Lanjutan:**")
            for q in data.get("follow_up_questions", []):
                st.markdown(f"- {q}")

            st.divider()
            st.markdown("**🗂️ Panduan Administrasi & Penjaminan BPJS:**")
            admin = data.get("admin_guidance") or {}
            req_docs = admin.get("required_documents") or []
            st.write(f"- **Alur Layanan:** {admin.get('service_route', '-')}")
            st.write(f"- **Status Penjaminan:** {admin.get('bpjs_eligibility_note', '-')}")
            st.write(f"- **Dokumen Wajib:** {', '.join(req_docs) if req_docs else '-'}")

            st.divider()
            st.markdown("**📚 Sitasi Dokumen SOP RS:**")
            for cit in data.get("citations", []):
                with st.expander(f"{cit.get('document', 'SOP')} — {cit.get('section', 'Umum')}"):
                    st.write(cit.get("snippet", ""))

            if data.get("clinical_disclaimer"):
                st.caption(data["clinical_disclaimer"])
        else:
            st.error(f"Terjadi kesalahan (HTTP {resp.status_code}): {resp.text}")