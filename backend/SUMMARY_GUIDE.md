# Summary Generation Guide

## Overview

The summary generation feature creates concise summaries of lesson transcripts using LLM models (OpenAI or Anthropic). It automatically uses the corrected transcript if available, or falls back to the original transcript.

## ✨ Features

✅ **Automatic Transcript Selection** - Uses corrected transcript when available, falls back to original  
✅ **Configurable Length** - Set maximum word count in config  
✅ **Retry Logic** - Automatic retry with exponential backoff on rate limits  
✅ **Metadata Tracking** - Saves model, temperature, and prompt used  
✅ **Multi-Provider** - Supports both OpenAI and Anthropic  
✅ **Async Support** - Both sync and async interfaces  
✅ **Error Recovery** - Graceful error handling with detailed logging  

## 🚀 Quick Start

### 1. Configuration

Make sure your `backend/data/config.yaml` is configured:

```yaml
api_key: "sk-your-api-key-here"
provider: OpenAI  # or Anthropic

summary:
  max_length: 300
  model: gpt-4o
  prompt: "Please provide a concise summary of the following lesson transcript."
  temperature: 0.7
```

### 2. Generate Summary

```python
from backend.tasks import generate_summary

# Generate summary for a lesson
success = generate_summary(lesson_id=1)

if success:
    print("Summary generated successfully!")
```

### 3. Test It

```bash
cd backend
python test_summary.py <lesson_id>
```

Options:
- `--use-original` - Use original transcript instead of corrected

## 📖 Usage Examples

### Basic Usage

```python
from backend.tasks import generate_summary

# Use corrected transcript (default)
success = generate_summary(lesson_id=1)

# Use original transcript
success = generate_summary(lesson_id=1, use_corrected=False)
```

### Async Usage

```python
import asyncio
from backend.tasks import generate_summary_async

async def main():
    success = await generate_summary_async(
        lesson_id=1,
        use_corrected=True
    )
    print(f"Summary generation {'succeeded' if success else 'failed'}")

asyncio.run(main())
```

### Background Task (Recommended for Production)

```python
from backend.models import Task
from backend.database import engine
from sqlmodel import Session

# Queue a summary task
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

# The worker will process it automatically
```

### With Custom Session

```python
from backend.tasks import generate_summary
from backend.database import engine
from sqlmodel import Session

with Session(engine) as session:
    # Generate summaries for multiple lessons in one session
    for lesson_id in [1, 2, 3, 4, 5]:
        success = generate_summary(
            lesson_id=lesson_id,
            session=session
        )
        if success:
            print(f"Summary generated for lesson {lesson_id}")
```

### Retrieve Generated Summary

```python
from backend.models import Lesson
from backend.database import engine
from sqlmodel import Session

with Session(engine) as session:
    lesson = session.get(Lesson, 1)
    
    if lesson.summary:
        print(f"Summary: {lesson.summary}")
        
        # Get metadata
        metadata = lesson.get_summary_metadata()
        if metadata:
            print(f"Model: {metadata.model}")
            print(f"Temperature: {metadata.temperature}")
```

## ⚙️ Configuration Options

### `max_length`
- Maximum number of words for the summary
- **Default**: 300
- **Type**: Integer
- The prompt automatically includes instructions to limit summary length

### `model`
- LLM model to use for generation
- **OpenAI examples**: `gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **Anthropic examples**: `claude-3-5-sonnet-20241022`, `claude-3-opus-20240229`

### `prompt`
- Instructions for the LLM
- **Default**: "Please provide a concise summary of the following lesson transcript."
- **Tips**: 
  - Be specific about what to include/exclude
  - Mention tone (formal, casual, etc.)
  - Specify structure if needed

### `temperature`
- Controls randomness/creativity
- **Range**: 0.0 to 2.0
- **Default**: 0.7
- **Lower (0.1-0.3)**: More focused and deterministic
- **Higher (0.7-1.0)**: More creative and varied

## 🔄 Workflow

```
1. Load Lesson from Database
   ↓
2. Choose Transcript (corrected → original)
   ↓
3. Combine all segment texts into one string
   ↓
4. Build prompt with summary instructions
   ↓
5. Call LLM with retry logic
   ↓
6. Save summary to lesson.summary
   ↓
7. Save metadata to lesson.summary_metadata
   ↓
8. Commit to database
```

## 🛡️ Error Handling & Retry Logic

### Automatic Retry
- **Maximum attempts**: 5
- **Initial delay**: 1 second
- **Exponential backoff**: 1s → 2s → 4s → 8s → 16s → 32s (max 60s)
- **Jitter**: ±10% randomness to prevent thundering herd

### Rate Limit Detection
Automatically detects and retries on:
- "rate limit" errors
- HTTP 429 status codes
- "too many requests" errors
- "quota exceeded" errors

### Example Retry Sequence
```
Attempt 1: Rate limit error → Wait 1.0s
Attempt 2: Rate limit error → Wait 2.1s
Attempt 3: Rate limit error → Wait 3.9s
Attempt 4: Rate limit error → Wait 8.2s
Attempt 5: Success! ✅
```

## 🧪 Testing

### Test Script

The `test_summary.py` script provides comprehensive testing:

```bash
# Generate summary for lesson 12
python test_summary.py 12

# Use original transcript instead of corrected
python test_summary.py 12 --use-original
```

The script will:
1. Show lesson details and transcript status
2. Display transcript preview
3. Generate the summary
4. Show the complete summary
5. Display summary metadata

### Example Output

```
================================================================================
Lesson: Introduction to Machine Learning
================================================================================

📄 Transcript Status:
--------------------------------------------------------------------------------
Original transcript: ✅ Available
Corrected transcript: ✅ Available
Segments: 42
Total characters: 3,245

🔄 Generating summary using corrected transcript (this may take a moment)...

✅ Summary generated successfully!

📝 SUMMARY:
--------------------------------------------------------------------------------
This lesson introduces the fundamental concepts of machine learning, 
including supervised and unsupervised learning approaches. We explore 
common algorithms like linear regression and decision trees, and discuss 
practical applications in real-world scenarios.

Summary length: 234 characters, 36 words

📊 SUMMARY METADATA:
--------------------------------------------------------------------------------
Provider: OpenAI
Model: gpt-4o
Temperature: 0.7
Prompt: Please provide a concise summary of the following lesson transcript...
```

## 🔧 Troubleshooting

### "API key not found in config"
**Solution**: Add your API key to `config.yaml`:
```yaml
api_key: "sk-your-api-key-here"
```

### "Lesson has no transcript to summarize"
**Solution**: 
- Make sure the lesson has been transcribed first
- Check if `lesson.transcript` or `lesson.corrected_transcript` exists

### Rate Limit Errors
**Solution**:
- The retry logic should handle this automatically
- If persisting, wait a few minutes before retrying
- Consider upgrading your API plan for higher limits

### Summary Too Long/Short
**Solution**: Adjust `max_length` in config:
```yaml
summary:
  max_length: 500  # Increase for longer summaries
```

### Summary Quality Issues
**Solution**: Adjust the prompt and temperature:
```yaml
summary:
  prompt: "Provide a detailed summary focusing on key concepts and takeaways."
  temperature: 0.3  # Lower for more focused output
```

## 📊 Database Schema

The summary is stored in the `lesson` table:

```python
lesson.summary              # The generated summary text (str)
lesson.summary_metadata     # Metadata about generation (dict)
```

Metadata includes:
- `provider`: OpenAI or Anthropic
- `model`: Model used (e.g., gpt-4o)
- `temperature`: Temperature setting
- `prompt`: Full prompt used

## 🎯 Best Practices

1. **Always correct first**: Generate summary from corrected transcript for better quality
2. **Tune the prompt**: Customize for your specific use case
3. **Set appropriate length**: Balance detail with conciseness
4. **Use background tasks**: For production, queue tasks instead of direct calls
5. **Monitor costs**: Longer transcripts = more tokens = higher costs
6. **Cache summaries**: Don't regenerate unnecessarily

## 🔗 Integration Example

Complete workflow from transcription to summary:

```python
from backend.tasks import correct_transcript, generate_summary

lesson_id = 1

# Step 1: Correct the transcript
print("Correcting transcript...")
if correct_transcript(lesson_id, segments_per_group=10, max_concurrency=5):
    print("✅ Correction complete")
    
    # Step 2: Generate summary from corrected transcript
    print("Generating summary...")
    if generate_summary(lesson_id, use_corrected=True):
        print("✅ Summary complete")
    else:
        print("❌ Summary failed")
else:
    print("❌ Correction failed")
```

## 📚 Related Features

- **Correction**: `correct_transcript()` - Correct transcription errors
- **LLM Utils**: `get_llm_model()` - Get configured LLM model
- **Worker**: Background task processing for async operations

## 💡 Tips

- **Preview before full run**: Test on a single lesson first
- **Batch processing**: Use background tasks for multiple lessons
- **Cost optimization**: Use cheaper models for drafts, better models for final
- **Error logs**: Check logs for detailed error information
- **Metadata**: Always save metadata for reproducibility

---

For more details, see `tasks/README.md` and `tasks/summary.py`.

