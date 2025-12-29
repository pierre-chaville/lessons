# Transcript Correction Setup

## ✅ What Was Created

### Core Files
1. **`tasks/llm_utils.py`** - LLM model utility with OpenAI and Anthropic support
2. **`tasks/correction.py`** - Main correction logic with parallel processing
3. **`tasks/__init__.py`** - Module exports
4. **`tasks/README.md`** - Detailed documentation

### Testing & Examples
5. **`test_correction.py`** - Test script for correction functionality
6. **`worker.py`** (updated) - Integrated with background task processing

### Dependencies
7. **`requirements.txt`** (updated) - Added LangChain packages

## 🚀 Installation

### Step 1: Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This will install:
- `langchain-openai==0.2.14`
- `langchain-anthropic==0.3.8`

### Step 2: Configure API Key

Edit `backend/data/config.yaml` and add your API key:

```yaml
api_key: "sk-your-api-key-here"
provider: OpenAI  # or Anthropic
```

## 🧪 Testing

### Quick Test

Run the test script to create a sample lesson and correct it:

```bash
cd backend
python test_correction.py
```

This will:
1. Create a test lesson with intentional spelling errors
2. Run the correction process
3. Display before/after comparison
4. Show correction metadata

### Test with Existing Lesson

```bash
python test_correction.py <lesson_id>
```

## 📖 Usage

### Method 1: Direct Function Call

```python
from backend.tasks import correct_transcript

# Simple usage
success = correct_transcript(lesson_id=1)

# With custom parameters
success = correct_transcript(
    lesson_id=1,
    segments_per_group=10,  # Process 10 segments per LLM call
    max_concurrency=10      # Maximum 10 parallel API calls
)
```

### Method 2: Background Task (Recommended for Production)

```python
from backend.models import Task
from backend.database import engine
from sqlmodel import Session

# Create a correction task
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

# The worker will pick it up automatically
```

### Method 3: Async (for Integration in Async Code)

```python
import asyncio
from backend.tasks import correct_transcript_async

async def my_app():
    success = await correct_transcript_async(
        lesson_id=1,
        segments_per_group=10,
        max_concurrency=10
    )
    return success

asyncio.run(my_app())
```

## ⚙️ How It Works

1. **Load Transcript**: Reads `lesson.transcript` (list of Segment objects)
2. **Split into Groups**: Divides segments into groups of `segments_per_group`
3. **Parallel Processing**: Processes multiple groups concurrently (max `max_concurrency`)
4. **Structured Output**: Uses LangChain's structured output to ensure proper format
5. **Save Results**: Updates `lesson.corrected_transcript` and `lesson.correction_metadata`

## 🎛️ Configuration

All settings are in `backend/data/config.yaml`:

```yaml
api_key: "your-api-key"
provider: OpenAI  # or Anthropic

correction:
  model: gpt-4o
  prompt: "Please correct the following transcript, fixing any errors while maintaining the original meaning and style."
  temperature: 0.3
```

## 🔧 Parameters

### `segments_per_group` (default: 10)
- Number of segments to send to LLM in each call
- **Lower** = more API calls, better granularity, higher cost
- **Higher** = fewer API calls, faster, but may hit context limits
- **Recommended**: 5-15

### `max_concurrency` (default: 10)
- Maximum parallel LLM API calls
- **Lower** = slower but safer (won't hit rate limits)
- **Higher** = faster but may hit API rate limits
- **Recommended**: 5-15

## 📊 Features

✅ **Parallel Processing** - Process multiple segment groups simultaneously
✅ **Concurrency Control** - Semaphore-based rate limiting
✅ **Structured Output** - Guaranteed JSON format from LLM
✅ **Error Handling** - Falls back to original text on error
✅ **Metadata Tracking** - Saves model, temperature, prompt used
✅ **Multi-Provider** - Supports OpenAI and Anthropic
✅ **Async Support** - Both sync and async interfaces
✅ **Database Integration** - Works with existing SQLModel schema

## 🐛 Troubleshooting

### "API key not found in config"
- Make sure `api_key` is set in `config.yaml`

### Rate Limit Errors
- Reduce `max_concurrency` (try 5 or less)
- Increase delay between calls if needed

### Context Length Errors
- Reduce `segments_per_group` (try 5-8)
- Segments may be too long for the model

### Import Errors
- Make sure you've installed the requirements: `pip install -r requirements.txt`
- Check that you're in the correct Python environment

## 📝 Next Steps

1. ✅ Install dependencies
2. ✅ Configure API key
3. ✅ Run test script
4. ✅ Integrate into your application
5. Consider adding similar functionality for summary generation

## 🆘 Support

Check the detailed documentation in `tasks/README.md` for more examples and usage patterns.

