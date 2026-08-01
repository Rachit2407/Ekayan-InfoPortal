import os
import google.generativeai as genai

# Get the key exactly like scraper.py does
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

# If it's still the default, try reading from scraper.py to find it
if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
    try:
        with open("scraper.py", "r", encoding="utf-8") as f:
            for line in f:
                if "GEMINI_API_KEY = " in line and "YOUR_GEMINI_API_KEY_HERE" not in line:
                    # Extract the string inside quotes
                    parts = line.split('"') if '"' in line else line.split("'")
                    if len(parts) >= 3:
                        GEMINI_API_KEY = parts[1]
                        break
    except Exception as e:
        print(f"Could not parse scraper.py: {e}")

print(f"Using API Key: {GEMINI_API_KEY[:6]}...{GEMINI_API_KEY[-4:] if len(GEMINI_API_KEY) > 10 else ''}")

try:
    genai.configure(api_key=GEMINI_API_KEY)
    print("\nListing available models:")
    print("-" * 40)
    models = genai.list_models()
    for m in models:
        print(f"- {m.name} (supports: {m.supported_generation_methods})")
    print("-" * 40)
    print("Success listing models!")
except Exception as e:
    print(f"\n❌ Error listing models: {e}")
