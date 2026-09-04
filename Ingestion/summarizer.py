import os
import time
from pathlib import Path
from dotenv import dotenv_values
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent.parent


def evaluate_and_summarize(topic_name: str, topic_desc: str, email_subject: str, email_body: str, api_key: str = None, return_diagnostics: bool = False):
    """
    Uses Google Gemini to judge genuine relevance and generate a structured summary in a single call.
    Accepts user's personal BYOK api_key, falling back to os.environ if set.
    Returns: 
      If return_diagnostics is False: (is_relevant: bool, summary_text: str | None)
      If return_diagnostics is True: (is_relevant: bool, summary_text: str | None, diagnostics: dict)
    """
    start_time = time.perf_counter()
    active_key = (api_key or os.environ.get("GOOGLE_API_KEY") or "").strip()
    
    if not active_key:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        fallback = (
            f"### Summary\n"
            f"(Notice: No Gemini API Key configured. Add your API Key in Profile & Topics -> AI API Key to enable AI summarization.)\n"
            f"Email: {email_subject}\n\n"
            f"### Content\n{email_body[:400]}..."
        )
        diag = {
            "status": "NO_API_KEY",
            "elapsed_ms": elapsed_ms,
            "raw_response": None,
            "reason": "No Gemini API Key provided or found in environment."
        }
        return (True, fallback, diag) if return_diagnostics else (True, fallback)

    try:
        client = genai.Client(api_key=active_key)
    except Exception as err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        fallback = f"### Summary\n(Notice: Could not initialize Gemini client: {err})\nEmail: {email_subject}\n\n### Content\n{email_body[:400]}..."
        diag = {
            "status": "CLIENT_INIT_ERROR",
            "elapsed_ms": elapsed_ms,
            "raw_response": str(err),
            "reason": f"Failed to initialize Google GenAI Client: {err}"
        }
        return (True, fallback, diag) if return_diagnostics else (True, fallback)

    prompt = f"""You are an intelligent email assistant.
The user is tracking the following topic:
Topic: "{topic_name}"
Description: "{topic_desc}"

Evaluate the following incoming email:
Subject: {email_subject}
Content:
{email_body[:4000]}

Instructions:
1. Determine if this email genuinely matches the topic above.
2. If it is NOT genuinely relevant (e.g. unrelated promo, generic news, or loose coincidence), respond with:
RELEVANT: NO

3. If it IS genuinely relevant, respond in this format:
RELEVANT: YES
### Summary
[2-3 clear sentences summarizing key details]

### Action Items & Takeaways
- [Bullet points of immediate takeaways, deadlines, or links]
"""

    try:
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        content = response.text.strip() if response.text else ""

        if content.upper().startswith("RELEVANT: NO"):
            diag = {
                "status": "REJECTED",
                "elapsed_ms": elapsed_ms,
                "raw_response": content,
                "reason": "Model determined email does not genuinely match the topic."
            }
            return (False, None, diag) if return_diagnostics else (False, None)

        summary_text = content
        if summary_text.upper().startswith("RELEVANT: YES"):
            summary_text = summary_text[len("RELEVANT: YES"):].strip()

        diag = {
            "status": "VERIFIED",
            "elapsed_ms": elapsed_ms,
            "raw_response": content,
            "reason": "Model verified relevance and generated summary."
        }
        return (True, summary_text, diag) if return_diagnostics else (True, summary_text)
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        print(f"Gemini LLM notice: {e}")
        fallback = f"### Summary\n(API Note: {e})\nEmail: {email_subject}\n\n### Content\n{email_body[:400]}..."
        diag = {
            "status": "API_ERROR",
            "elapsed_ms": elapsed_ms,
            "raw_response": str(e),
            "reason": f"API Error: {e}"
        }
        return (True, fallback, diag) if return_diagnostics else (True, fallback)
