
# 🩺 Aarogya AI: Smart Medical Assistant

**Aarogya AI** is a sophisticated healthcare ecosystem built with **FastAPI** and **MongoDB**. It leverages **LLMs** (Google Gemini) and **Speech-to-Text** (Faster-Whisper) to automate clinical documentation, provide real-time patient support, and manage telemedicine workflows.

## 🚀 Key Features

### 🤖 AI Consultation & Intelligence

* **Clinical Assistant**: Powered by **Google Gemini**, providing context-aware medical insights for both doctors and patients.
* **Structured Report Parsing**: Converts raw medical dictations into structured JSON entities including medications, dosages, and diagnoses.
* **Voice-to-Text Transcription**: Integrated **Faster-Whisper** model for transcribing doctor-patient consultations.
* **Predictive Triage**: Analyzes patient symptoms to predict medical severity and suggest appropriate specializations.

### 🏥 Telemedicine & SOS

* **Automated Scheduling**: Integrates with **Google Calendar API** to generate **Google Meet** links for confirmed consultations.
* **Emergency SOS Protocol**: A one-tap emergency feature that notifies available responders and creates an instant live medical link.
* **Instant Care Console**: A "Blind Match" system connecting patients with online specialists in minutes.

### 📋 Patient Management

* **Wellness Plans**: AI-curated diet, habit, and exercise recommendations based on medical history.
* **Medical Record Vault**: Secure storage for prescriptions, immunizations, and uploaded reports.
* **Digital Prescriptions**: A specialized interface for doctors to save prescriptions directly to a patient's digital record.

---

## 🛠️ Detailed Tech Stack

* **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Asynchronous Python framework).
* **Database**: [MongoDB](https://www.mongodb.com/) (via **Motor** async driver).
* **Intelligence**: [Google Gemini AI](https://ai.google.dev/) (Clinical reasoning), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) (Transcription).
* **Frontend**: [Jinja2 Templates](https://jinja.palletsprojects.com/) (Server-side rendering), [HTMX](https://htmx.org/) (Partial updates), [Tailwind CSS](https://tailwindcss.com/) (Styling).
* **Integrations**: [Google Calendar/Meet API](https://developers.google.com/calendar).

---

## 📖 Usage Guide

### For Patients

1. **Onboarding**: Register and complete your medical profile, including allergies and existing conditions.
2. **Consultation**: Chat with **Aarogya Assistant** for health summaries or use the **Instant Care** hub to find a specialist.
3. **Wellness**: View your AI-generated health plan in the **Wellness Plan** section.
4. **Appointments**: Request time slots and join virtual calls directly from the **Appointments** dashboard.

### For Doctors

1. **Patient Search**: Locate patients using their unique **Aarogya ID** and send connection requests.
2. **Command Center**: Use the **AI Consultation Room** to chat with AI about a patient's context or dictate notes.
3. **Report Generation**: Use the **Dictation & Reports** tab to transcribe audio and generate a structured medical report with one click.
4. **Management**: Toggle your status between **Public/Private** and **Online/Busy** to manage incoming patient traffic.

---

## 🔗 API Overview (Core Endpoints)

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/ai/chat` | Send a medical query to the AI Assistant. |
| `POST` | `/doctor/patient/{id}/transcribe` | Transcribe medical audio files. |
| `POST` | `/appointments/request` | Request an appointment with a doctor. |
| `POST` | `/patient/emergency/alert` | Trigger the SOS emergency protocol. |
| `GET` | `/reports/my-reports` | Retrieve all medical reports for the user. |

---

## ⚙️ Environment Configuration

Ensure your `.env` file contains the following keys:

* `MONGO_URI`: Your MongoDB connection string.
* `GEMINI_API_KEY`: API key for Google Gemini services.
* `WHISPER_MODEL_SIZE`: Transcription model size (e.g., `tiny`, `base`, `small`).
* `SESSION_EXPIRATION_MINUTES`: Default is `1440` (24 hours).

---

## 🗺️ Future Roadmap

* **Offline Mode**: Local LLM integration for basic first-aid advice without internet access.
* **Wearable Sync**: Direct data ingestion from smartwatches and health bands.
* **Admin Panel**: A centralized dashboard for platform owners to authorize doctors and monitor SOS metrics.
* **Multi-Language Support**: Expanding AI interactions to regional languages for wider accessibility.

---

## 📜 License & Credits

Project developed by **Rohan K R**.
Contributions are welcome via Pull Requests.

*Disclaimer: Aarogya AI is an assistant tool and should not replace professional medical diagnosis.*
