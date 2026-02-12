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

Run all services concurrently:
```bash
npm run dev
```

Or run individually:
- Frontend: `cd frontend && npm run dev`
- Backend: `npm run dev:backend`

### Build

```bash
npm run build
```

## Project Structure

```
lessons/
├── frontend/          # Vue 3 frontend source
├── backend/           # FastAPI backend
├── dist/             # Built frontend files
└── dist/             # Built frontend files
```

