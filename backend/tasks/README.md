# Tasks Module

This module contains utilities and tasks for processing lessons, including LLM-based operations.

## Modules

### `llm_utils.py`
Utility functions for working with LLM models via LangChain.

**Key Function:**
- `get_llm_model(task_name=None, temperature=None, model=None)` - Returns a configured ChatOpenAI or ChatAnthropic model based on the provider in config.yaml

### `transcribe.py`
Audio transcription using Faster Whisper.

**Key Functions:**
- `transcribe_lesson(lesson_id, session=None)` - Transcribe a lesson's audio file
- `transcribe_audio(audio_path, language=None, beam_size=5, vad_filter=True, initial_prompt=None)` - Low-level transcription function

### `correction.py`
Lesson transcript correction using LLM with parallel processing.

**Key Functions:**
- `correct_transcript(lesson_id, segments_per_group=10, max_concurrency=10, session=None)` - Synchronous correction function
- `correct_transcript_async(lesson_id, segments_per_group=10, max_concurrency=10, session=None)` - Async version

### `summary.py`
Lesson summary generation using LLM.

**Key Functions:**
- `generate_summary(lesson_id, use_corrected=True, session=None)` - Synchronous summary generation
- `generate_summary_async(lesson_id, use_corrected=True, session=None)` - Async version

## Usage Examples

### Audio Transcription

```python
from backend.tasks import transcribe_lesson

# Transcribe a lesson's audio file
success = transcribe_lesson(lesson_id=1)

if success:
    print("Transcription completed successfully!")
```

### Summary Generation

```python
from backend.tasks import generate_summary

# Generate summary using corrected transcript
success = generate_summary(lesson_id=1)

# Generate summary using original transcript
success = generate_summary(
    lesson_id=1,
    use_corrected=False
)

if success:
    print("Summary generated successfully!")
```

### Basic Correction

```python
from backend.tasks import correct_transcript

# Correct a lesson transcript
success = correct_transcript(
    lesson_id=1,
    segments_per_group=10,  # Process 10 segments at a time
    max_concurrency=10      # Run up to 10 parallel LLM calls
)

if success:
    print("Transcript corrected successfully!")
```

### Async Correction

```python
import asyncio
from backend.tasks import correct_transcript_async

async def main():
    success = await correct_transcript_async(
        lesson_id=1,
        segments_per_group=15,
        max_concurrency=5
    )
    print(f"Correction {'succeeded' if success else 'failed'}")

asyncio.run(main())
```

### Using with Background Tasks

To queue a transcription task:

```python
from backend.models import Task
from backend.database import engine
from sqlmodel import Session

with Session(engine) as session:
    task = Task(
        task_type="transcription",
        status="pending",
        parameters={
            "lesson_id": 1
        }
    )
    session.add(task)
    session.commit()
    print(f"Created transcription task {task.id}")
```

To queue a summary task:

```python
from backend.models import Task
from backend.database import engine
from sqlmodel import Session

with Session(engine) as session:
    task = Task(
        task_type="summary",
        status="pending",
        parameters={
            "lesson_id": 1,
            "use_corrected": True
        }
    )
    session.add(task)
    session.commit()
    print(f"Created summary task {task.id}")
```

To queue a correction task that will be processed by the worker:

```python
from backend.models import Task
from backend.database import engine
from sqlmodel import Session

with Session(engine) as session:
    task = Task(
        task_type="correction",
        status="pending",
        parameters={
            "lesson_id": 1,
            "segments_per_group": 10,
            "max_concurrency": 10
        }
    )
    session.add(task)
    session.commit()
    print(f"Created correction task {task.id}")
```

### Custom LLM Configuration

```python
from backend.tasks import get_llm_model

# Use with custom parameters
llm = get_llm_model(
    task_name='correction',  # Uses correction settings from config
    temperature=0.5,         # Override temperature
    model='gpt-4'           # Override model
)

# Use the LLM directly
response = llm.invoke("Your prompt here")
```

## Configuration

Both correction and summary functions use settings from `backend/data/config.yaml`:

```yaml
api_key: "your-api-key-here"
provider: OpenAI  # or Anthropic

correction:
  model: gpt-4o
  prompt: "Please correct the following transcript, fixing any errors while maintaining the original meaning and style."
  temperature: 0.3

summary:
  max_length: 300
  model: gpt-4o
  prompt: "Please provide a concise summary of the following lesson transcript."
  temperature: 0.7
```

## How It Works

1. **Grouping**: The transcript segments are split into groups of `segments_per_group` segments
2. **Parallel Processing**: Multiple groups are processed in parallel with a maximum of `max_concurrency` concurrent LLM calls
3. **Structured Output**: LangChain's structured output ensures the LLM returns properly formatted corrections with segment IDs
4. **Merging**: Corrected segments are merged back into the original order and saved to `lesson.corrected_transcript`
5. **Metadata**: The correction settings (model, temperature, prompt, provider) are saved to `lesson.correction_metadata`

## Parameters

### `segments_per_group`
- Number of segments to include in each LLM call
- **Default**: 10
- **Recommendation**: 5-15 segments depending on segment length and model context limits

### `max_concurrency`
- Maximum number of parallel LLM API calls
- **Default**: 10
- **Recommendation**: 5-15 depending on API rate limits and system resources
- Too high may hit rate limits; too low will be slower

## Error Handling

### Correction
- If an LLM call fails for a group, the original text is preserved for that group
- Errors are logged with full stack traces
- The function returns `False` if correction fails, allowing retry logic
- Database changes are rolled back on error
- Automatic retry with exponential backoff on rate limits (up to 5 attempts)

### Summary
- If summary generation fails, no summary is saved
- Errors are logged with full stack traces  
- The function returns `False` if generation fails, allowing retry logic
- Database changes are rolled back on error
- Automatic retry with exponential backoff on rate limits (up to 5 attempts)

