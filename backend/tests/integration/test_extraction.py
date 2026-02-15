"""Integration test — source extraction via LLM."""
import sys
import logging
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlmodel import Session
from database import engine
from models import Lesson
from schemas import Source
from tasks.extract_sources import extract_sources_async

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def display_lesson_extraction(lesson_id: int):
    """Display lesson details and extracted sources"""
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

        print(f"\n📄 Transcript Status:")
        print("-"*80)
        print(f"Edited transcript: {'✅ Available' if has_edited else '❌ Not available'}")

        if not has_edited:
            print("\n⚠️  No edited transcript available. Sources can only be extracted from edited transcripts.")
            print("   Please run edition first using test_edition.py")
            print("="*80 + "\n")
            return

        # Collect all sources
        all_sources = []
        parts_with_sources = 0
        for part_dict in lesson.edited_transcript:
            if isinstance(part_dict, dict):
                sources = part_dict.get("sources", [])
            else:
                sources = part_dict.sources if hasattr(part_dict, "sources") else []

            if sources:
                parts_with_sources += 1
                for source_dict in sources:
                    if isinstance(source_dict, dict):
                        all_sources.append(Source(**source_dict))
                    else:
                        all_sources.append(source_dict)

        print(f"Edited parts: {len(lesson.edited_transcript)}")
        print(f"Parts with sources: {parts_with_sources}")
        print(f"Total sources found: {len(all_sources)}")

        # Display metadata
        metadata = lesson.get_edited_metadata()
        if metadata:
            print("\n📊 EXTRACTION METADATA:")
            print("-"*80)
            print(f"Provider: {metadata.provider}")
            print(f"Model: {metadata.model}")
            print(f"Temperature: {metadata.temperature}")
            if metadata.prompt:
                prompt_preview = metadata.prompt[:150]
                if len(metadata.prompt) > 150:
                    prompt_preview += "..."
                print(f"Prompt: {prompt_preview}")

        if len(all_sources) == 0:
            print("\n⚠️  No sources found in edited transcript.")
            print("="*80 + "\n")
            return

        # Display sources grouped by edited part
        print("\n📚 EXTRACTED SOURCES:")
        print("-"*80)
        source_index = 1
        for part_idx, part_dict in enumerate(lesson.edited_transcript, 1):
            if isinstance(part_dict, dict):
                sources = part_dict.get("sources", [])
                text = part_dict.get("text", "")
            else:
                sources = part_dict.sources if hasattr(part_dict, "sources") else []
                text = part_dict.text if hasattr(part_dict, "text") else ""

            if sources:
                print(f"\n📝 Part {part_idx} ({len(sources)} source{'s' if len(sources) > 1 else ''}):")
                text_preview = text[:150] + "..." if len(text) > 150 else text
                print(f"   Text: {text_preview}")
                print(f"   Sources:")
                for source in sources:
                    if isinstance(source, dict):
                        src_type = source.get("type", "N/A")
                        src_work = source.get("work", "N/A")
                        src_ref = source.get("ref", "N/A")
                        src_slug = source.get("standard_slug", "N/A")
                        src_cited = source.get("cited_excerpt", "N/A")
                        src_conf = source.get("confidence")
                    else:
                        src_type = source.type or "N/A"
                        src_work = source.work or "N/A"
                        src_ref = source.ref or "N/A"
                        src_slug = source.standard_slug or "N/A"
                        src_cited = source.cited_excerpt or "N/A"
                        src_conf = source.confidence

                    print(f"     [{source_index}] {src_type}: {src_work} {src_ref}")
                    if src_slug != "N/A":
                        print(f"         Slug: {src_slug}")
                    if src_cited != "N/A":
                        cited_preview = src_cited[:100] + "..." if len(src_cited) > 100 else src_cited
                        print(f"         Cited excerpt: \"{cited_preview}\"")
                    if src_conf is not None:
                        conf_color = "🟢" if src_conf >= 0.7 else "🟡" if src_conf >= 0.4 else "🔴"
                        print(f"         Confidence: {conf_color} {src_conf:.2f}")
                    source_index += 1

        # Summary statistics
        print("\n📊 EXTRACTION SUMMARY:")
        print("-"*80)
        print(f"Total edited parts: {len(lesson.edited_transcript)}")
        print(f"Parts with sources: {parts_with_sources}")
        print(f"Total sources extracted: {len(all_sources)}")

        # Group by type
        type_counts = {}
        for source in all_sources:
            src_type = source.type or "Unknown"
            type_counts[src_type] = type_counts.get(src_type, 0) + 1

        if type_counts:
            print(f"\nSources by type:")
            for src_type, count in sorted(type_counts.items()):
                print(f"  - {src_type}: {count}")

        # Confidence statistics
        confidences = [s.confidence for s in all_sources if s.confidence is not None]
        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            high_conf = sum(1 for c in confidences if c >= 0.7)
            print(f"\nConfidence statistics:")
            print(f"  - Average: {avg_conf:.2f}")
            print(f"  - High confidence (≥0.7): {high_conf}/{len(confidences)}")

        print("\n" + "="*80 + "\n")


async def main_async():
    """Main async test function"""
    if len(sys.argv) < 2:
        print("Usage: python test_extraction.py <lesson_id> [max_concurrency]")
        print("\nThis script extracts sources from a lesson's edited transcript.")
        print("\nOptions:")
        print("  lesson_id        ID of the lesson to extract sources from")
        print("  max_concurrency  Maximum concurrent LLM calls (default: 10)")
        print("\nExample:")
        print("  python test_extraction.py 5 5")
        sys.exit(1)

    try:
        lesson_id = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid lesson ID provided")
        sys.exit(1)

    # Parse optional parameters
    max_concurrency = 10
    if len(sys.argv) >= 3:
        try:
            max_concurrency = int(sys.argv[2])
        except ValueError:
            logger.warning(f"Invalid max_concurrency, using default: {max_concurrency}")

    # Display lesson info before extraction
    print("\n🔍 BEFORE EXTRACTION:")
    display_lesson_extraction(lesson_id)

    # Extract sources
    logger.info(f"Starting source extraction for lesson {lesson_id}...")
    print(f"\n🔄 Extracting sources (this may take a moment)...")
    print(f"   - Max concurrency: {max_concurrency}")
    print(f"   - Processing edited parts in parallel")
    print(f"   - Using LLM to identify and extract sources\n")

    success = await extract_sources_async(
        lesson_id=lesson_id,
        max_concurrency=max_concurrency
    )

    if success:
        logger.info("Source extraction completed successfully!")
        print("\n✅ Source extraction completed!\n")

        # Display updated lesson with extracted sources
        print("\n🔍 AFTER EXTRACTION:")
        display_lesson_extraction(lesson_id)
    else:
        logger.error("Source extraction failed!")
        print("\n❌ Source extraction failed!\n")
        sys.exit(1)


def main():
    """Main entry point"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
