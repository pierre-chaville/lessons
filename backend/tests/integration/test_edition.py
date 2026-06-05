"""Integration test — transcript edition via LLM."""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlmodel import Session
from database import engine
from models import Lesson
from services import edit_transcript
import crud

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def display_lesson_edition(lesson_id: int):
    """Display lesson details and edited transcript"""
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
        has_edited = bool(lesson.edited_transcript)

        print(f"\n📄 Transcript Status:")
        print("-"*80)
        print(f"Original transcript: {'✅ Available' if has_original else '❌ Not available'}")
        print(f"Corrected transcript: {'✅ Available' if has_corrected else '❌ Not available'}")
        print(f"Edited transcript: {'✅ Available' if has_edited else '❌ Not available'}")

        if has_original or has_corrected:
            transcript = lesson.corrected_transcript if has_corrected else lesson.transcript
            total_chars = sum(
                len(seg['text'] if isinstance(seg, dict) else seg.text)
                for seg in transcript
            )
            print(f"Source segments: {len(transcript)}")
            print(f"Total characters: {total_chars:,}")

        # Display edited transcript
        if has_edited:
            print(f"\n📝 EDITED TRANSCRIPT:")
            print("-"*80)
            print(f"Edited parts: {len(lesson.edited_transcript)}")

            # Collect all sources from lesson_source table
            db_sources = crud.get_lesson_sources(session, lesson_id)
            all_sources = db_sources
            print(f"Total sources: {len(all_sources)}")

            # Display metadata
            metadata = lesson.get_edited_metadata()
            if metadata:
                print("\n📊 EDITION METADATA:")
                print("-"*80)
                print(f"Provider: {metadata.provider}")
                print(f"Model: {metadata.model}")
                print(f"Temperature: {metadata.temperature}")
                if metadata.prompt:
                    prompt_preview = metadata.prompt[:150]
                    if len(metadata.prompt) > 150:
                        prompt_preview += "..."
                    print(f"Prompt: {prompt_preview}")

            # Display first few edited parts
            print("\n📖 EDITED PARTS PREVIEW (first 3 parts):")
            print("-"*80)
            # Group DB sources by paragraph_index
            sources_by_para: dict[int, list] = {}
            for s in db_sources:
                sources_by_para.setdefault(s.paragraph_index, []).append(s)

            for i, part_dict in enumerate(lesson.edited_transcript[:3]):
                if isinstance(part_dict, dict):
                    start = part_dict.get("start", 0)
                    end = part_dict.get("end", 0)
                    text = part_dict.get("text", "")
                else:
                    start = part_dict.start
                    end = part_dict.end
                    text = part_dict.text

                para_sources = sources_by_para.get(i, [])
                print(f"\n[{i + 1}] Part ({start:.1f}s - {end:.1f}s):")
                text_preview = text[:200] + "..." if len(text) > 200 else text
                print(f"    {text_preview}")
                if para_sources:
                    print(f"    Sources: {len(para_sources)}")
                    for j, src in enumerate(para_sources[:2], 1):
                        print(f"      [{j}] {src.type or 'N/A'}: {src.work or 'N/A'} {src.ref or 'N/A'}")
                    if len(para_sources) > 2:
                        print(f"      ... and {len(para_sources) - 2} more")
        else:
            print("\n⚠️  No edited transcript available")

        # Show a preview of the source transcript
        if has_original or has_corrected:
            print("\n📖 SOURCE TRANSCRIPT PREVIEW (first 3 segments):")
            print("-"*80)
            transcript = lesson.corrected_transcript if has_corrected else lesson.transcript
            for i, seg in enumerate(transcript[:3], 1):
                if isinstance(seg, dict):
                    start = seg.get("start", 0)
                    end = seg.get("end", 0)
                    text = seg.get("text", "")
                else:
                    start = seg.start
                    end = seg.end
                    text = seg.text
                preview = text[:100] + "..." if len(text) > 100 else text
                print(f"{i}. [{start:.1f}s - {end:.1f}s] {preview}")

        print("\n" + "="*80 + "\n")


def main():
    """Main test function"""
    if len(sys.argv) < 2:
        print("Usage: python test_edition.py <lesson_id> [words_per_group] [max_concurrency]")
        print("\nOptions:")
        print("  lesson_id           ID of the lesson to edit")
        print("  words_per_group     Target words per group (default: 1000)")
        print("  max_concurrency      Maximum concurrent LLM calls (default: 10)")
        print("\nExample:")
        print("  python test_edition.py 5 1000 5")
        sys.exit(1)

    try:
        lesson_id = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid lesson ID provided")
        sys.exit(1)

    # Parse optional parameters
    words_per_group = 1000
    max_concurrency = 10

    if len(sys.argv) >= 3:
        try:
            words_per_group = int(sys.argv[2])
        except ValueError:
            logger.warning(f"Invalid words_per_group, using default: {words_per_group}")

    if len(sys.argv) >= 4:
        try:
            max_concurrency = int(sys.argv[3])
        except ValueError:
            logger.warning(f"Invalid max_concurrency, using default: {max_concurrency}")

    # Display lesson info before edition
    print("\n🔍 BEFORE EDITION:")
    display_lesson_edition(lesson_id)

    # Run edition
    logger.info(f"Starting edition for lesson {lesson_id}...")
    print(f"\n🔄 Running edition (this may take a moment)...")
    print(f"   - Words per group: {words_per_group}")
    print(f"   - Max concurrency: {max_concurrency}")
    print(f"   - Processing transcript text without timestamps\n")

    success = edit_transcript(
        lesson_id=lesson_id,
        words_per_group=words_per_group,
        max_concurrency=max_concurrency
    )

    if success:
        logger.info("Edition completed successfully!")
        print("\n✅ Edition completed!\n")

        # Display updated lesson with edited transcript
        print("\n🔍 AFTER EDITION:")
        display_lesson_edition(lesson_id)
    else:
        logger.error("Edition failed!")
        print("\n❌ Edition failed!\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
