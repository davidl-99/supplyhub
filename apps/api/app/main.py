from fastapi import FastAPI

app = FastAPI(
    title="SupplyHub API",
    description="API para la plataforma B2B SupplyHub.",
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}