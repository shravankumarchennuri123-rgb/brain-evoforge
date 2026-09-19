"""Development bootstrap for Google Colab.

Colab is for setup and smoke testing only. It is not an always-on service host.
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

print("BRAIN-EvoForge source path ready:", ROOT)
print("Set WQ_BRAIN_EMAIL and WQ_BRAIN_PASSWORD as environment variables before discovery.")
print("Then run: python -m wq_evo discover")
print("For 24/7 service, deploy the same project to an always-on VM/VPS with Docker/systemd.")
