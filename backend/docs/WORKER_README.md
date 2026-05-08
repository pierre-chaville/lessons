# Background Task Worker

## Overview

The worker is a background process that polls the database for pending tasks and processes them.

The worker now runs as a **separate process** from FastAPI:
- `main.py` serves API requests only
- `run_worker.py` starts the background worker process

This isolation prevents worker memory leaks or crashes from taking down the API process.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend  │────▶│  FastAPI     │────▶│   Database   │
│   (Vue.js)  │     │  (main.py)   │     │  (SQLite)    │
└─────────────┘     └──────────────┘     └──────┬───────┘
                                                 │
                                                 ▼
                                         ┌──────────────┐
                                         │    Worker    │
                                         │  (worker.py) │
                                         └──────────────┘
```

## How It Works

1. **Polling**: The worker polls the database every 5 seconds for pending tasks
2. **Processing**: When a task is found, it:
   - Updates status to "running"
   - Records start time
   - Processes the task based on its type
   - Updates status to "completed" or "failed"
   - Records end time and duration
3. **Types**: Currently supports three task types:
   - `transcription` - Audio transcription
   - `correction` - Transcript correction
   - `summary` - Summary generation

## Running the Worker

Start the worker as its own process:
```bash
cd backend
.\venv\Scripts\Activate.ps1  # Activate virtual environment
python run_worker.py
```

Run the API separately (different terminal/process):
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 10000
```

### Render deployment

Use two services from the same codebase:
- Web service (API): `uvicorn main:app --host 0.0.0.0 --port 10000`
- Worker service: `python run_worker.py`

## Creating Test Tasks

### Via API
```bash
# Create a test transcription task
curl -X POST http://localhost:8000/tasks/test/transcription

# Create a test correction task
curl -X POST http://localhost:8000/tasks/test/correction

# Create a test summary task
curl -X POST http://localhost:8000/tasks/test/summary
```

### Via Frontend
Navigate to the Processing page to view all tasks and their statuses.

## Task Lifecycle

```
pending ──▶ running ──▶ completed
                  │
                  └────▶ failed
```

1. **pending**: Task created, waiting to be processed
2. **running**: Worker is currently processing the task
3. **completed**: Task finished successfully
4. **failed**: Task encountered an error

## Worker Logs

The worker outputs logs to stdout/stderr:
- Info messages: Task status changes, processing events
- Error messages: Exceptions, failures

When running via Electron, logs are prefixed with `[Worker]` in the console.

## Graceful Shutdown

The worker handles shutdown signals (SIGINT, SIGTERM) gracefully:
- Completes the current task if possible
- Cleans up resources
- Exits cleanly

## Future Enhancements

The current implementation is a skeleton. Future additions will include:
- Actual transcription logic (Whisper integration)
- LLM-based correction and summarization
- Task retry logic
- Task priority queues
- Multiple worker support
- Progress reporting
- Task cancellation

## File Structure

```
backend/
├── worker.py           # Main worker implementation
├── run_worker.py       # Worker process entrypoint
├── models.py           # Task model definition
├── crud.py             # Database operations
└── main.py             # FastAPI app (API only, no embedded worker)
```

## Monitoring

Tasks can be monitored in real-time through:
1. **Frontend**: Navigate to Processing page (auto-refreshes every 5s)
2. **API**: GET `/tasks` endpoint
3. **Logs**: Worker console output

## Troubleshooting

### Worker not starting
- Check that Python virtual environment is activated
- Verify `worker.py` exists in backend directory
- Run `python run_worker.py` directly and inspect traceback/logs

### Tasks stuck in "running"
- Worker might have crashed mid-processing
- Restart the worker
- Consider adding task timeout logic

### No tasks being processed
- Check worker is running (look for logs)
- Verify database connection
- Check task status (should be "pending")

