import os

"""
Run this script ONCE to see which models are available on your Groq account.
Usage: python check_models.py
"""
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)
models = client.models.list()

print("\n=== ALL AVAILABLE GROQ MODELS ===\n")
vision_models = []
text_models = []

for m in sorted(models.data, key=lambda x: x.id):
    print(f"  {m.id}")
    mid = m.id.lower()
    if any(x in mid for x in ["vision", "scout", "maverick", "llava", "llama-4"]):
        vision_models.append(m.id)
    elif any(x in mid for x in ["llama", "gemma", "mixtral"]):
        text_models.append(m.id)

print("\n=== VISION-CAPABLE MODELS ===")
for m in vision_models:
    print(f"  {m}")

print("\n=== TEXT MODELS ===")
for m in text_models:
    print(f"  {m}")

print("\n✅ Copy the correct model IDs and update evaluator.py lines 15-16")
