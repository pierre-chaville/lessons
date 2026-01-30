"""Test script for summary generation functionality"""
import sys
import logging
from sqlmodel import Session
from database import engine
from models import Lesson
from tasks import generate_summary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def display_lesson_summary(lesson_id: int):
    """Display lesson details and summary"""
    with Session(engine) as session:
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            return
        
        print("\n" + "="*80)
        print(f"Lesson: {lesson.title}")
        print("="*80)
        
        # Check for edited transcript
        has_edited = bool(lesson.edited_transcript)
        
        print(f"\n📄 Edited Transcript Status:")
        print("-"*80)
        print(f"Edited transcript: {'✅ Available' if has_edited else '❌ Not available'}")
        
        if has_edited:
            edited_transcript = lesson.edited_transcript
            total_chars = sum(
                len(part['text'] if isinstance(part, dict) else part.text)
                for part in edited_transcript
            )
            print(f"Edited parts: {len(edited_transcript)}")
            print(f"Total characters: {total_chars:,}")
        
        # Display summary
        print("\n📝 SUMMARY:")
        print("-"*80)
        if lesson.summary:
            print(lesson.summary)
            print(f"\nSummary length: {len(lesson.summary)} characters, {len(lesson.summary.split())} words")
            
            # Display metadata
            metadata = lesson.get_summary_metadata()
            if metadata:
                print("\n📊 SUMMARY METADATA:")
                print("-"*80)
                print(f"Provider: {metadata.provider}")
                print(f"Model: {metadata.model}")
                print(f"Temperature: {metadata.temperature}")
                if metadata.prompt:
                    print(f"Prompt: {metadata.prompt[:100]}...")
        else:
            print("No summary available")
        
    # Show a preview of the edited transcript
    if has_edited:
        print("\n📖 EDITED TRANSCRIPT PREVIEW (first 3 parts):")
        print("-"*80)
        for i, part in enumerate(edited_transcript[:3], 1):
            if isinstance(part, dict):
                text = part.get('text', '')
            else:
                text = part.text
            preview = text[:200] + "..." if len(text) > 200 else text
            print(f"{i}. {preview}")
        
        print("\n" + "="*80 + "\n")


def main():
    """Main test function"""
    if len(sys.argv) < 2:
        print("Usage: python test_summary.py <lesson_id> [prompt_name]")
        print("\nOptions:")
        print("  prompt_name     Name of the prompt to use (optional)")
        sys.exit(1)
    
    try:
        lesson_id = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid lesson ID provided")
        sys.exit(1)
    
    # Optional prompt name
    prompt_name = sys.argv[2] if len(sys.argv) >= 3 else None
    
    # Display lesson info before summary
    display_lesson_summary(lesson_id)
    
    # Generate summary
    logger.info(f"Generating summary for lesson {lesson_id}...")
    print("\n🔄 Generating summary from edited transcript (this may take a moment)...\n")
    
    success = generate_summary(
        lesson_id=lesson_id,
        prompt_type=prompt_name
    )
    
    if success:
        logger.info("Summary generated successfully!")
        print("\n✅ Summary generated successfully!\n")
        
        # Display updated lesson with summary
        display_lesson_summary(lesson_id)
    else:
        logger.error("Summary generation failed!")
        print("\n❌ Summary generation failed!\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

