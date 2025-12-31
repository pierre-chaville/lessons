"""Test script for transcript correction functionality"""
import sys
import logging
from sqlmodel import Session
from database import engine
from models import Lesson, Segment
from tasks import correct_transcript

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_lesson() -> int:
    """Create a test lesson with sample transcript"""
    with Session(engine) as session:
        lesson = Lesson(
            title="Test Lesson for Correction",
            filename="test.mp3",
            duration=60.0,
            transcript=[
                Segment(start=0.0, end=5.0, text="Bonjur, ceci est un test de transcripshon"),
                Segment(start=5.0, end=10.0, text="Il y a plusieur erreur dans ce texte"),
                Segment(start=10.0, end=15.0, text="Nous allon voir si l'IA peut les corijé"),
                Segment(start=15.0, end=20.0, text="C'est un exempl simple pour testé le systeme"),
                Segment(start=20.0, end=25.0, text="J'espair que sa fonctione bien"),
            ]
        )
        session.add(lesson)
        session.commit()
        session.refresh(lesson)
        logger.info(f"Created test lesson {lesson.id}")
        return lesson.id


def display_lesson_transcripts(lesson_id: int):
    """Display original and corrected transcripts"""
    with Session(engine) as session:
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            return
        
        print("\n" + "="*80)
        print(f"Lesson: {lesson.title}")
       
        if lesson.corrected_transcript:
            # Display metadata
            metadata = lesson.get_correction_metadata()
            if metadata:
                print("\n📊 CORRECTION METADATA:")
                print("-"*80)
                print(f"Provider: {metadata.provider}")
                print(f"Model: {metadata.model}")
                print(f"Temperature: {metadata.temperature}")
                print(f"Prompt: {metadata.prompt[:100]}...")
        else:
            print("No corrected transcript available")
        
        print("\n" + "="*80 + "\n")


def main():
    """Main test function"""
    if len(sys.argv) > 1:
        # Use provided lesson ID
        try:
            lesson_id = int(sys.argv[1])
            logger.info(f"Using existing lesson {lesson_id}")
        except ValueError:
            logger.error("Invalid lesson ID provided")
            sys.exit(1)
    else:
        # Create a test lesson
        logger.info("Creating test lesson...")
        lesson_id = create_test_lesson()
    
    # Display original transcript
    display_lesson_transcripts(lesson_id)
    
    # Run correction
    logger.info(f"Starting correction for lesson {lesson_id}...")
    print("\n🔄 Running correction (this may take a moment)...\n")
    
    success = correct_transcript(
        lesson_id=lesson_id,
        segments_per_group=100,  # Small groups for this test
        max_concurrency=10      # Low concurrency for testing
    )
    
    if success:
        logger.info("Correction completed successfully!")
        print("\n✅ Correction completed!\n")
        
        # Display corrected transcript
        display_lesson_transcripts(lesson_id)
    else:
        logger.error("Correction failed!")
        print("\n❌ Correction failed!\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

