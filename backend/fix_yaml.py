"""Script to fix the corrupted PyYAML installation"""
import shutil
import subprocess
import sys
from pathlib import Path

venv_site_packages = Path(__file__).parent / "venv" / "Lib" / "site-packages"

print("=" * 60)
print("Fixing corrupted PyYAML installation")
print("=" * 60)

# Find and remove corrupted yaml directories
yaml_dirs = [
    venv_site_packages / "yaml",
    venv_site_packages / "~yyaml",
    venv_site_packages / "_yaml",
]

for yaml_dir in yaml_dirs:
    if yaml_dir.exists():
        print(f"\nRemoving: {yaml_dir}")
        try:
            if yaml_dir.is_dir():
                shutil.rmtree(yaml_dir)
            else:
                yaml_dir.unlink()
            print(f"  [OK] Removed")
        except Exception as e:
            print(f"  [ERROR] Failed: {e}")

# Remove PyYAML egg-info directories
for item in venv_site_packages.glob("*yaml*.dist-info"):
    print(f"\nRemoving: {item}")
    try:
        shutil.rmtree(item)
        print(f"  [OK] Removed")
    except Exception as e:
        print(f"  [ERROR] Failed: {e}")

print("\n" + "=" * 60)
print("Now reinstalling PyYAML...")
print("=" * 60)

# Reinstall PyYAML
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "pyyaml"])
    print("\n[OK] PyYAML reinstalled successfully!")
except Exception as e:
    print(f"\n[ERROR] Failed to reinstall PyYAML: {e}")
    print("\nPlease run manually: pip install pyyaml")

print("\n" + "=" * 60)
print("Testing import...")
print("=" * 60)

try:
    import yaml
    print("[OK] PyYAML import successful!")
except ImportError as e:
    print(f"[ERROR] Still can't import PyYAML: {e}")
    print("\nThe system will continue to use JSON format for config.")

