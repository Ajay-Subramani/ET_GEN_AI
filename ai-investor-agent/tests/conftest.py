from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure unit tests never attempt external LLM / agent calls (Ollama, Gemini, etc.).
# Individual tests can opt back in by overriding env vars explicitly.
os.environ["APP_ENV"] = "test"
