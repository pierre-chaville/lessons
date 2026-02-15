"""Integration test — configuration management."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import yaml
    print("[OK] PyYAML is installed")
except ImportError as e:
    print("[WARNING] PyYAML is NOT installed properly:", str(e))
    print("[INFO] Will use JSON fallback")

try:
    import config
    print("[OK] Config module imported successfully")
    print(f"     Using format: {'YAML' if config.HAS_YAML else 'JSON'}")
    print(f"     Config file: {config.CONFIG_FILE}")

    # Test loading config
    cfg = config.load_config()
    print("[OK] Config loaded successfully")
    print(f"     Provider: {cfg.get('provider')}")
    print(f"     Whisper model: {cfg.get('whisper', {}).get('model_size')}")
    print(f"     Language: {cfg.get('transcribe', {}).get('language')}")

    # Test getting specific value
    model_size = config.get_config_value('whisper.model_size')
    print(f"[OK] Get specific value: whisper.model_size = {model_size}")

    print("\n[SUCCESS] All tests passed!")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
