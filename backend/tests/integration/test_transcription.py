"""Integration test — audio transcription via Whisper."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlmodel import Session
from database import engine
from models import Lesson
from tasks import transcribe_lesson
from storage import s3_enabled, get_audio_object_key, download_audio_bytes

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def display_lesson_transcript(lesson_id: int):
    """Display lesson transcript information"""
    with Session(engine) as session:
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            return

        print("\n" + "=" * 80)
        print(f"Lesson: {lesson.title}")
        print("=" * 80)

        print(f"\n📁 Audio File: {lesson.filename}")
        print(f"📍 Storage Key: {get_audio_object_key(lesson_id, lesson.filename)}")

        # Check if audio file exists in storage
        if s3_enabled():
            audio_key = get_audio_object_key(lesson_id, lesson.filename)
            try:
                audio_bytes = download_audio_bytes(audio_key)
                print(
                    f"✅ Audio file exists in storage ({len(audio_bytes) / 1024 / 1024:.2f} MB)"
                )
            except Exception as e:
                print(f"❌ Audio file not found in storage: {e}")
        else:
            print(f"⚠️  S3 storage not configured")

        print("\n📝 TRANSCRIPT:")
        print("-" * 80)
        if lesson.transcript:
            print(f"✅ Transcript available: {len(lesson.transcript)} segments")

            # Display metadata
            metadata = lesson.get_transcript_metadata()
            if metadata:
                print("\n📊 TRANSCRIPT METADATA:")
                print("-" * 80)
                print(f"Provider: {metadata.provider}")
                print(f"Model: {metadata.model}")
                print(f"Language: {metadata.language}")

            # Display first few segments
            print("\n🎤 FIRST 5 SEGMENTS:")
            print("-" * 80)
            for i, seg in enumerate(lesson.transcript[:5], 1):
                if isinstance(seg, dict):
                    print(
                        f"{i}. [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text'][:100]}..."
                    )
                else:
                    print(
                        f"{i}. [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text[:100]}..."
                    )

            if len(lesson.transcript) > 5:
                print(f"\n... and {len(lesson.transcript) - 5} more segments")

            # Display duration
            if lesson.duration:
                minutes = int(lesson.duration // 60)
                seconds = int(lesson.duration % 60)
                print(f"\n⏱️  Total Duration: {minutes}m {seconds}s")
        else:
            print("❌ No transcript available")

        print("\n" + "=" * 80 + "\n")


def main():
    """Main test function"""
    if len(sys.argv) < 2:
        print("Usage: python test_transcription.py <lesson_id>")
        print("\nThis will transcribe the audio file for the specified lesson.")
        print("Make sure the audio file exists in data/audio/ directory.")
        sys.exit(1)

    try:
        lesson_id = int(sys.argv[1])
    except ValueError:
        logger.error("Invalid lesson ID provided")
        sys.exit(1)

    # Display lesson info before transcription
    display_lesson_transcript(lesson_id)

    # Check if S3 storage is enabled and audio file exists
    if not s3_enabled():
        logger.error("S3 storage is not configured")
        print("\n❌ Cannot transcribe: S3 storage is not configured!")
        print("   Please configure S3 environment variables.")
        sys.exit(1)

    with Session(engine) as session:
        lesson = session.get(Lesson, lesson_id)
        if not lesson:
            logger.error(f"Lesson {lesson_id} not found")
            sys.exit(1)

        audio_key = get_audio_object_key(lesson_id, lesson.filename)
        try:
            download_audio_bytes(audio_key)
        except Exception as e:
            logger.error(f"Audio file not found in storage: {audio_key} ({e})")
            print("\n❌ Cannot transcribe: Audio file not found in storage!")
            print(f"   Storage key: {audio_key}")
            print(f"   Error: {e}")
            sys.exit(1)

    # Run transcription
    logger.info(f"Starting transcription for lesson {lesson_id}...")
    print("\n🔄 Starting transcription (this may take several minutes)...")
    print("   The Whisper model will be loaded on first run (may take 30-60 seconds)")
    print("   Progress will be logged as segments are transcribed\n")

    success = transcribe_lesson(lesson_id=lesson_id)

    if success:
        logger.info("Transcription completed successfully!")
        print("\n✅ Transcription completed successfully!\n")

        # Display updated transcript
        display_lesson_transcript(lesson_id)
    else:
        logger.error("Transcription failed!")
        print("\n❌ Transcription failed!\n")
        print("Check the logs above for error details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
