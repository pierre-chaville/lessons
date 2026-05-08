# Lessons Manager

A web application for managing lessons with audio transcription and summaries.

## Tech Stack

- **Frontend**: Vue 3 (script setup), Vite, Tailwind CSS, Headless UI, Heroicons, vue-i18n
- **Backend**: FastAPI with SQLModel and SQLite database

## Setup

### Prerequisites

- Node.js (v18 or higher)
- Python 3.8+

### Installation

1. Install Node dependencies:
```bash
cd frontend
npm install
```

2. Set up Python virtual environment and install backend dependencies:
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Unix/MacOS:
source venv/bin/activate

pip install -r requirements.txt
cd ..
```

### Development

Run services individually:

- Frontend:
```bash
cd frontend
npm run dev
```

- Backend API (FastAPI only):
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 10000 --reload
```

- Background worker (separate process):
```bash
cd backend
python run_worker.py
```

The worker is intentionally decoupled from FastAPI so worker memory leaks/crashes do not impact API availability.

### Deployment (Render)

Create two services from the same repository:

- Web service (API): `uvicorn main:app --host 0.0.0.0 --port 10000`
- Worker service: `python run_worker.py`

Both services should use the same environment variables and connect to the same database.

### Build

```bash
npm run build
```

## Project Structure

```
lessons/
├── frontend/         # Vue 3 frontend source
└── backend/          # FastAPI API + standalone worker
```

