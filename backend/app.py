from fastapi import FastAPI

app = FastAPI(title="savrr")


@app.get("/health")
async def health():
    return {"status": "ok"}
