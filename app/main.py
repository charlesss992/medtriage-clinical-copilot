from fastapi import FastAPI
from app.api.routes_triage import router as triage_router

app = FastAPI(
    title="MedTriage & Clinical Copilot API",
    description="Sistem pendukung keputusan triase IGD, rawat jalan, dan verifikasi BPJS berbasis RAG & Guardrails.",
    version="1.0.0",
)

app.include_router(triage_router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}