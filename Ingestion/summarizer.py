import os
import re
import time
from pathlib import Path
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234/v1"
DEFAULT_LM_STUDIO_MODEL = "qwen/qwen3-1.7b"
DEFAULT_LM_STUDIO_API_KEY = "lm-studio"


def _normalize_base_url(url: str | None) -> str:
    """Ensures the endpoint URL has proper format and ends in /v1 for OpenAI compatibility."""
    endpoint = (url or os.environ.get("LM_STUDIO_URL") or DEFAULT_LM_STUDIO_URL).strip().rstrip("/")
    if not endpoint:
        endpoint = DEFAULT_LM_STUDIO_URL
    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
        endpoint = f"http://{endpoint}"
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    return endpoint


def _strip_reasoning_tags(content: str) -> str:
    """Strips <think>...</think> tags if produced by reasoning/deepseek/qwen3 models."""
    if not content:
        return ""
    # Remove complete <think>...</think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    # Remove lingering open <think> tag if output was cut off
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def test_lm_studio_connection(api_url: str = None, api_key: str = None, model: str = None) -> dict:
    """
    Tests connectivity to LM Studio (or any OpenAI-compatible server),
    retrieves the list of loaded models, and measures latency.
    """
    start_time = time.perf_counter()
    base_url = _normalize_base_url(api_url)
    key = (api_key or os.environ.get("LM_STUDIO_API_KEY") or DEFAULT_LM_STUDIO_API_KEY).strip()
    target_model = (model or os.environ.get("LM_STUDIO_MODEL") or DEFAULT_LM_STUDIO_MODEL).strip()

    try:
        client = OpenAI(base_url=base_url, api_key=key, timeout=5.0)
        models_response = client.models.list()
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        model_ids = [m.id for m in models_response.data] if hasattr(models_response, 'data') else []

        model_found = target_model in model_ids if model_ids else True

        return {
            "success": True,
            "latency_ms": elapsed_ms,
            "base_url": base_url,
            "models": model_ids,
            "target_model": target_model,
            "target_model_ready": model_found,
            "message": f"Successfully connected to LM Studio ({elapsed_ms}ms). Found {len(model_ids)} model(s)."
        }
    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return {
            "success": False,
            "latency_ms": elapsed_ms,
            "base_url": base_url,
            "models": [],
            "target_model": target_model,
            "target_model_ready": False,
            "message": f"Connection failed to {base_url}: {e}"
        }


def evaluate_and_summarize(
    topic_name: str,
    topic_desc: str,
    email_subject: str,
    email_body: str,
    api_url: str = None,
    model: str = None,
    api_key: str = None,
    return_diagnostics: bool = False
):
    """
    Uses LM Studio (OpenAI-compatible) to judge genuine relevance and generate a structured summary in a single call.
    Accepts user-specified api_url, model, and api_key, falling back to environment or defaults.
    Returns: 
      If return_diagnostics is False: (is_relevant: bool, summary_text: str | None)
      If return_diagnostics is True: (is_relevant: bool, summary_text: str | None, diagnostics: dict)
    """
    start_time = time.perf_counter()
    base_url = _normalize_base_url(api_url)
    active_model = (model or os.environ.get("LM_STUDIO_MODEL") or DEFAULT_LM_STUDIO_MODEL).strip()
    active_key = (api_key or os.environ.get("LM_STUDIO_API_KEY") or DEFAULT_LM_STUDIO_API_KEY).strip()

    try:
        client = OpenAI(base_url=base_url, api_key=active_key, timeout=35.0)
    except Exception as err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        diag = {
            "status": "CLIENT_INIT_ERROR",
            "elapsed_ms": elapsed_ms,
            "raw_response": str(err),
            "reason": f"Failed to initialize OpenAI client: {err}"
        }
        return (False, None, diag) if return_diagnostics else (False, None)

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
        response = client.chat.completions.create(
            model=active_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise, structured email analyst assistant. Follow the output format instructions strictly."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        raw_content = response.choices[0].message.content or ""
        content = _strip_reasoning_tags(raw_content).strip()

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
        print(f"LM Studio LLM notice ({active_model}): {e}")
        diag = {
            "status": "API_ERROR",
            "elapsed_ms": elapsed_ms,
            "raw_response": str(e),
            "reason": f"LM Studio Error: {e}"
        }
        return (False, None, diag) if return_diagnostics else (False, None)
