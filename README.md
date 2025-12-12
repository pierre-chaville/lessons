# Lessons Manager

A desktop application for managing lessons with audio transcription and summaries.

## Tech Stack

- **Electron**: Desktop shell and window management
- **Frontend**: Vue 3 (script setup), Vite, Tailwind CSS, Headless UI, Heroicons, vue-i18n
- **Backend**: FastAPI with SQLModel and SQLite database

## Setup

### Prerequisites

- Node.js (v18 or higher)
- Python 3.8+

### Installation

1. Install Node dependencies:
```bash
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
- Frontend: `npm run dev:frontend`
- Backend: `npm run dev:backend`
- Electron: `npm run dev:electron`

### Build

```bash
npm run build
```

## Project Structure

```
lessons/
├── electron/          # Electron main process
├── frontend/          # Vue 3 frontend source
├── backend/           # FastAPI backend
├── dist/             # Built frontend files
└── dist-electron/    # Built Electron application
```

