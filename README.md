# MedTriage & Clinical Copilot

Sistem pendukung keputusan triase klinis IGD, rawat jalan, dan verifikasi alur administrasi BPJS Kesehatan berbasis **RAG (Retrieval-Augmented Generation)** dan **Clinical Safety Guardrails**.

## Fitur Utama
- **Hybrid Clinical Triage:** Kombinasi *rule-based guardrails* untuk tanda vital kritis dan sintesis LLM berbasis SOP rumah sakit.
- **RAG SOP Rumah Sakit:** Indexing dokumen SOP (`.md` & `.pdf`) ke ChromaDB dengan sitasi dokumen sumber.
- **Alur Administrasi & BPJS:** Rekomendasi otomatis jalur pendaftaran (IGD tanpa rujukan vs Loket SEP Rawat Jalan) serta daftar dokumen wajib.
- **Privasi Data (PII Masking):** Penyamaran otomatis NIK dan nomor telepon sebelum pemrosesan AI.

## Cara Menjalankan
1. Salin `.env.example` menjadi `.env` dan isi `OPENAI_API_KEY`.
2. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
3. Jalankan indexing dokumen SOP:
   ```bash
   python -m app.rag.ingest
   ```
4. Jalankan unit test:
   ```bash
   pytest
   ```
5. Jalankan API & Antarmuka Petugas:
   ```bash
   uvicorn app.main:app --reload --port 8000
   streamlit run ui/streamlit_app.py
   ```
   Atau gunakan Docker:
   ```bash
   docker-compose up --build
   ```
