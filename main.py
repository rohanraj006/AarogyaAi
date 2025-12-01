# main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates

# Routes
from routes import (
    user_routes, 
    report_routes, 
    doctor_routes, 
    connection_routes, 
    admin_routes, 
    appointment_routes, 
    ui_routes, 
    patient_routes, 
    ai_routes 
)

app = FastAPI(
    title="AarogyaAI",
    description="Medical AI Assistant",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include all routers
app.include_router(ui_routes.router, prefix="", tags=["UI"])
app.include_router(user_routes.router, prefix="/users", tags=["Users"])
app.include_router(report_routes.router, prefix="/reports", tags=["Reports"])
app.include_router(doctor_routes.router, prefix="/doctor", tags=["Doctor"])
app.include_router(connection_routes.router, prefix="/connections", tags=["Connections"])
app.include_router(admin_routes.router, prefix="/admin",tags=["Admin"])
app.include_router(appointment_routes.router, prefix="/appointments", tags=["Appointments"])
app.include_router(patient_routes.router, prefix="/patient", tags=["Patient"])
app.include_router(ai_routes.router, prefix="/ai", tags=["AI"]) # <--- Added this

@app.get("/")
def read_root():
    return {"message": "Aarogya AI Service Running"}