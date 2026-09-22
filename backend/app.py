from fastapi import FastAPI

from backend.routes import profiles

app = FastAPI(title="savrr")

app.include_router(profiles.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
