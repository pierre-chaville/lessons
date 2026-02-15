"""Integration test — source verification against Sefaria API + LLM."""
import sys
import logging
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlmodel import Session
from database import engine
from models import Lesson
from schemas import Source
from tasks.sources import verify_lesson_sources_async

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def display_lesson_sources(lesson_id: int):
    """Display lesson details and sources"""
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
            print("\n⚠️  No edited transcript available. Sources are only available in edited transcripts.")
            print("="*80 + "\n")
            return

        # Collect all sources
        all_sources = []
        for part_dict in lesson.edited_transcript:
            if isinstance(part_dict, dict) and part_dict.get("sources"):
                for source_dict in part_dict["sources"]:
                    all_sources.append(Source(**source_dict))
            elif hasattr(part_dict, "sources") and part_dict.sources:
                for source in part_dict.sources:
                    if isinstance(source, dict):
                        all_sources.append(Source(**source))
                    else:
                        all_sources.append(source)

        print(f"Total sources found: {len(all_sources)}")

        if len(all_sources) == 0:
            print("\n⚠️  No sources found in edited transcript.")
            print("="*80 + "\n")
            return

        # Display sources
        print("\n📚 SOURCES:")
        print("-"*80)
        for i, source in enumerate(all_sources, 1):
            print(f"\n[{i}] Source:")
            print(f"  Type: {source.type or 'N/A'}")
            print(f"  Work: {source.work or 'N/A'}")
            print(f"  Reference: {source.ref or 'N/A'}")
            print(f"  Slug: {source.standard_slug or 'N/A'}")
            print(f"  Original Text: {source.original_text[:100] if source.original_text and len(source.original_text) > 100 else source.original_text or 'N/A'}...")
            print(f"  Translation Text: {source.translation_text[:100] if source.translation_text and len(source.translation_text) > 100 else source.translation_text or 'N/A'}...")

            # Display verification status if available
            if source.slug_retrieved is not None:
                print(f"\n  🔍 Verification Status:")
                print(f"    Slug Retrieved: {'✅' if source.slug_retrieved else '❌'}")
                verification_status = source.verification_status
                if verification_status:
                    status_display = {
                        "exactly_found": "✅ Exactly Found",
                        "paraphrase_or_similar": "✅ Paraphrase/Similar",
                        "partially_found": "⚠️ Partially Found",
                        "not_found": "❌ Not Found",
                        "reference_exists_but_text_differs": "⚠️ Wrong Reference"
                    }.get(verification_status, f"⏳ {verification_status}")
                    print(f"    Verification Status: {status_display}")
                else:
                    print(f"    Verification Status: ⏳ Not verified")
                if source.verification_confidence is not None:
                    print(f"    Confidence: {source.verification_confidence:.2f}")
                if source.verification_explanation:
                    explanation_preview = source.verification_explanation[:150]
                    if len(source.verification_explanation) > 150:
                        explanation_preview += "..."
                    print(f"    Explanation: {explanation_preview}")
                if source.matched_text:
                    matched_preview = source.matched_text[:100]
                    if len(source.matched_text) > 100:
                        matched_preview += "..."
                    print(f"    Matched Text: {matched_preview}")

        # Summary statistics
        if any(s.slug_retrieved is not None for s in all_sources):
            retrieved_count = sum(1 for s in all_sources if s.slug_retrieved)
            found_count = sum(1 for s in all_sources if s.verification_status and s.verification_status in ["exactly_found", "paraphrase_or_similar", "partially_found"])
            print("\n📊 VERIFICATION SUMMARY:")
            print("-"*80)
            print(f"Total sources: {len(all_sources)}")
            print(f"Slugs retrieved: {retrieved_count}/{len(all_sources)}")
            print(f"Citations found: {found_count}/{len(all_sources)}")
            if retrieved_count > 0:
                success_rate = (found_count / retrieved_count) * 100
                print(f"Success rate: {success_rate:.1f}%")

        print("\n" + "="*80 + "\n")


async def main_async():
    """Main async test function"""
    if len(sys.argv) < 2:
        print("Usage: python test_check_sources.py <lesson_id>")
        print("\nThis script verifies sources in a lesson's edited transcript")
        print("by fetching text from Sefaria API and checking with LLM.")
        sys.exit(1)

    try:
        lesson_id = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid lesson ID provided")
        sys.exit(1)

    # Display lesson info before verification
    print("\n🔍 BEFORE VERIFICATION:")
    display_lesson_sources(lesson_id)

    # Verify sources
    logger.info(f"Starting source verification for lesson {lesson_id}...")
    print(f"\n🔄 Verifying sources (this may take a moment)...\n")
    print("   - Fetching text from Sefaria API")
    print("   - Checking citations with LLM")
    print("   - Processing sources in parallel (max 10 concurrent)\n")

    success = await verify_lesson_sources_async(lesson_id=lesson_id)

    if success:
        logger.info("Source verification completed successfully!")
        print("\n✅ Source verification completed!\n")

        # Display updated lesson with verification results
        print("\n🔍 AFTER VERIFICATION:")
        display_lesson_sources(lesson_id)
    else:
        logger.error("Source verification failed!")
        print("\n❌ Source verification failed!\n")
        sys.exit(1)


def main():
    """Main entry point"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
