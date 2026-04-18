from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import records, schemas, queues, datasets, cleaning

app = FastAPI(title="Annotation Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


app.include_router(records.router, prefix="/api/records", tags=["records"])
app.include_router(schemas.router, prefix="/api/schemas", tags=["schemas"])
app.include_router(queues.router, prefix="/api/queues", tags=["queues"])
app.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
app.include_router(cleaning.router, prefix="/api/cleaning", tags=["cleaning"])
