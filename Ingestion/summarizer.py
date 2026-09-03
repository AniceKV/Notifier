import os
from pathlib import Path
from dotenv import dotenv_values
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent.parent


def evaluate_and_summarize(topic_name: str, topic_desc: str, email_subject: str, email_body: str, api_key: str = None):
    """
    Uses Google Gemini to judge genuine relevance and generate a structured summary in a single call.
    Accepts user's personal BYOK api_key, falling back to os.environ if set.
    Returns: (is_relevant: bool, summary_text: str | None)
    """
    active_key = (api_key or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not active_key:
        return True, (
            f"### Summary\n"
            f"(Notice: No Gemini API Key configured. Add your API Key in Profile & Topics -> AI API Key to enable AI summarization.)\n"
            f"Email: {email_subject}\n\n"
            f"### Content\n{email_body[:400]}..."
        )

    try:
        client = genai.Client(api_key=active_key)
    except Exception as err:
        return True, f"### Summary\n(Notice: Could not initialize Gemini client: {err})\nEmail: {email_subject}\n\n### Content\n{email_body[:400]}..."

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
        content = response.text.strip() if response.text else ""

        if content.upper().startswith("RELEVANT: NO"):
            return False, None

        summary_text = content
        if summary_text.upper().startswith("RELEVANT: YES"):
            summary_text = summary_text[len("RELEVANT: YES"):].strip()

        return True, summary_text
    except Exception as e:
        print(f"Gemini LLM notice: {e}")
        fallback = f"### Summary\n(API Note: {e})\nEmail: {email_subject}\n\n### Content\n{email_body[:400]}..."
        return True, fallback
