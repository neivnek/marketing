import sys
import logging
from core.gemini_pool import generate_content_with_pool
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING, stream=sys.stdout)

load_dotenv()

try:
    print("Testing gemini pool...")
    res = generate_content_with_pool(["Xin chào"])
    print("Success! Response:", res.text)
except Exception as e:
    print(f"FAILED: {e}")
