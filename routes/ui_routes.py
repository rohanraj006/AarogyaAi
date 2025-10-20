# routes/ui_routes.py

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from security import get_current_authenticated_user # Dependency from security.py
from typing import Optional, Dict, Any
import datetime # Core Python module needed for templates

# Initialize Jinja2Templates (assuming 'templates' directory is set up relative to main.py)
templates = Jinja2Templates(directory="templates")
router = APIRouter()

# ----------------------------------------------------------------------
# UNIVERSAL DEPENDENCIES AND CONTEXT INJECTION
# ----------------------------------------------------------------------

# 1. Dependency to inject universal template context (fixes the datetime error)
async def get_base_template_context(request: Request) -> Dict[str, Any]:
    """Provides essential context variables for all templates using base.html."""
    return {
        "request": request,
        # FIX: Pass the datetime class explicitly under a safe name
        "datetime_cls": datetime.datetime, 
    }

# 2. Dependency to check if user is logged in but doesn't force authentication (for public pages)
async def get_optional_user(request: Request) -> Optional[dict]:
    try:
        # Tries to get the authenticated user; raises HTTPException if invalid session is found.
        # We catch the exception and return None instead of letting the app crash.
        return await get_current_authenticated_user(request)
    except HTTPException:
        return None

# ----------------------------------------------------------------------
# UI RENDERING ROUTES (GET requests)
# ----------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def home_page(
    current_user: Optional[dict] = Depends(get_optional_user),
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the Home page. Redirects logged-in users."""
    if current_user:
        # Redirect logged-in users immediately to their dashboard
        if current_user.get("user_type") == "doctor":
            return RedirectResponse("/doctor/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)
        
    context = {"title": "Aarogya AI - Home", **base_context}
    
    return templates.TemplateResponse("home.html", context)

@router.get("/users/login", response_class=HTMLResponse)
async def login_page(
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the login form page."""
    context = {"title": "User Login", **base_context}
    return templates.TemplateResponse("login.html", context)

@router.get("/users/register/patient", response_class=HTMLResponse)
async def register_patient_page(
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the patient registration form."""
    context = {"title": "Register as Patient", **base_context}
    return templates.TemplateResponse("register_patient.html", context)

@router.get("/users/register/doctor", response_class=HTMLResponse)
async def register_doctor_page(
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the doctor registration form."""
    context = {"title": "Register as Doctor", **base_context}
    return templates.TemplateResponse("register_doctor.html", context)

@router.get("/profile", response_class=HTMLResponse)
async def patient_dashboard_page(
    current_user: dict = Depends(get_current_authenticated_user),
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the Patient Dashboard/Profile (Protected)."""
    if current_user.get("user_type") != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    
    context = {"title": "Patient Dashboard", "user": current_user, **base_context}
    return templates.TemplateResponse("patient_dashboard.html", context)

@router.get("/doctor/dashboard", response_class=HTMLResponse)
async def doctor_dashboard_page(
    current_user: dict = Depends(get_current_authenticated_user),
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the Doctor Dashboard (Protected)."""
    if current_user.get("user_type") != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    
    context = {"title": "Doctor Dashboard", "user": current_user, **base_context}
    return templates.TemplateResponse("doctor_dashboard.html", context)

@router.get("/reports", response_class=HTMLResponse)
async def reports_page(
    current_user: dict = Depends(get_current_authenticated_user),
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the Reports (Upload/History) Page (Protected)."""
    context = {"title": "My Reports", "user": current_user, **base_context}
    return templates.TemplateResponse("reports.html", context)

@router.get("/appointments", response_class=HTMLResponse)
async def appointments_page(
    current_user: dict = Depends(get_current_authenticated_user),
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the Appointments Booking/Viewing Page (Protected)."""
    context = {"title": "Appointments", "user": current_user, **base_context}
    return templates.TemplateResponse("appointments.html", context)


@router.get("/ai/chat/widget", response_class=HTMLResponse)
async def get_ai_chat_widget(
    current_user: dict = Depends(get_current_authenticated_user),
    base_context: Dict[str, Any] = Depends(get_base_template_context)
):
    """Renders the partial HTML for the persistent chat widget (Protected)."""
    context = {"user": current_user, **base_context}
    return templates.TemplateResponse("ai_chat_widget.html", context)