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
        
        # Check for transcripts
        has_original = bool(lesson.transcript)
        has_corrected = bool(lesson.corrected_transcript)
        
        print(f"\n📄 Transcript Status:")
        print("-"*80)
        print(f"Original transcript: {'✅ Available' if has_original else '❌ Not available'}")
        print(f"Corrected transcript: {'✅ Available' if has_corrected else '❌ Not available'}")
        
        if has_original or has_corrected:
            transcript = lesson.corrected_transcript if has_corrected else lesson.transcript
            total_chars = sum(
                len(seg['text'] if isinstance(seg, dict) else seg.text)
                for seg in transcript
            )
            print(f"Segments: {len(transcript)}")
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
        
        # Show a preview of the transcript
        if has_original or has_corrected:
            print("\n📖 TRANSCRIPT PREVIEW (first 3 segments):")
            print("-"*80)
            transcript = lesson.corrected_transcript if has_corrected else lesson.transcript
            for i, seg in enumerate(transcript[:3], 1):
                if isinstance(seg, dict):
                    text = seg['text']
                else:
                    text = seg.text
                preview = text[:100] + "..." if len(text) > 100 else text
                print(f"{i}. {preview}")
        
        print("\n" + "="*80 + "\n")


def main():
    """Main test function"""
    if len(sys.argv) < 2:
        print("Usage: python test_summary.py <lesson_id> [--use-original]")
        print("\nOptions:")
        print("  --use-original    Use original transcript instead of corrected")
        sys.exit(1)
    
    try:
        lesson_id = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid lesson ID provided")
        sys.exit(1)
    
    # Check for use_original flag
    use_corrected = '--use-original' not in sys.argv
    
    # Display lesson info before summary
    display_lesson_summary(lesson_id)
    
    # Generate summary
    logger.info(f"Generating summary for lesson {lesson_id}...")
    transcript_type = "corrected" if use_corrected else "original"
    print(f"\n🔄 Generating summary using {transcript_type} transcript (this may take a moment)...\n")
    
    success = generate_summary(
        lesson_id=lesson_id,
        use_corrected=use_corrected
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

