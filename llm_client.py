"""
llm_client.py
A small command-line client for calling an LLM provider's API.

Why this project exists:
It demonstrates the exact things a Technical Support Specialist for an LLM API
product needs to understand hands-on:
  - Authentication with an API key
  - Request/response structure
  - Handling errors (401 unauthorized, 429 rate limit, 500/503 server errors)
  - Retrying failed requests with backoff (important for 429s)
  - Measuring latency
  - Counting tokens used (roughly) and estimating cost

This script uses the OpenAI-compatible chat completions format, which works
with:
  - OpenAI directly            (https://api.openai.com/v1)
  - Google Gemini (OpenAI-compat endpoint)
                                (https://generativelanguage.googleapis.com/v1beta/openai)
  - Many other providers that mimic the OpenAI API shape

You only need to change the BASE_URL and MODEL to switch providers - the
request/response handling code stays identical. That's exactly the kind of
thing an LLM API aggregator (like LLMAPI.ai) is built to smooth over for
customers.
"""

import os
import sys
import time
import json
import argparse
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Put your key in an environment variable instead of hardcoding it.
#   export LLM_API_KEY="your-key-here"        (Mac/Linux)
#   setx LLM_API_KEY "your-key-here"           (Windows, then restart terminal)
API_KEY = os.environ.get("LLM_API_KEY")

# Pick ONE provider by uncommenting it. Both speak the same OpenAI-style API.

# --- Option A: Google Gemini (free tier, get a key at aistudio.google.com) --
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
MODEL = "gemini-2.0-flash"

# --- Option B: OpenAI ---------------------------------------------------
# BASE_URL = "https://api.openai.com/v1"
# MODEL = "gpt-4o-mini"

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2  # doubles each retry: 2s, 4s, 8s...


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------
def call_llm(prompt: str, model: str = MODEL) -> dict:
    """
    Sends a single prompt to the LLM API and returns useful metadata:
    the model's reply, how long it took, and how many tokens were used.

    This is where the "support engineer" logic lives: every failure mode
    is handled explicitly and explained, rather than just crashing.
    """
    if not API_KEY:
        raise RuntimeError(
            "No API key found. Set the LLM_API_KEY environment variable first."
        )

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    attempt = 0
    while attempt <= MAX_RETRIES:
        attempt += 1
        start_time = time.time()

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
        except requests.exceptions.Timeout:
            print(f"[attempt {attempt}] Request timed out after 30s.")
            if attempt > MAX_RETRIES:
                raise
            _wait_before_retry(attempt)
            continue
        except requests.exceptions.ConnectionError as e:
            print(f"[attempt {attempt}] Connection error: {e}")
            if attempt > MAX_RETRIES:
                raise
            _wait_before_retry(attempt)
            continue

        elapsed_ms = round((time.time() - start_time) * 1000)

        # ---- Handle each status code the way a support engineer should ----
        if response.status_code == 200:
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return {
                "reply": reply,
                "latency_ms": elapsed_ms,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "attempts": attempt,
            }

        elif response.status_code == 401:
            # Not retryable - the key itself is wrong. Retrying won't help.
            raise PermissionError(
                "401 Unauthorized: the API key is missing, invalid, or expired. "
                "Check that LLM_API_KEY is set correctly."
            )

        elif response.status_code == 429:
            # Rate limit - THIS is retryable, with backoff.
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"[attempt {attempt}] 429 Rate limited. Waiting {wait}s before retrying...")
            if attempt > MAX_RETRIES:
                raise RuntimeError("Rate limited repeatedly - gave up after max retries.")
            time.sleep(wait)
            continue

        elif response.status_code in (500, 502, 503, 504):
            # Server-side/provider issue - also worth retrying a few times.
            print(f"[attempt {attempt}] Server error {response.status_code}. Retrying...")
            if attempt > MAX_RETRIES:
                raise RuntimeError(
                    f"Provider kept returning {response.status_code} after {MAX_RETRIES} retries."
                )
            _wait_before_retry(attempt)
            continue

        else:
            # Anything else (400 bad request, 404, etc.) - not retryable,
            # surface the provider's error message directly.
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise RuntimeError(f"Unexpected error {response.status_code}: {detail}")

    raise RuntimeError("Exhausted retries without success.")


def _wait_before_retry(attempt: int) -> None:
    wait = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
    time.sleep(wait)


# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Minimal LLM API client with error handling.")
    parser.add_argument("prompt", help="The prompt to send to the model.")
    parser.add_argument("--model", default=MODEL, help=f"Model name (default: {MODEL})")
    args = parser.parse_args()

    try:
        result = call_llm(args.prompt, model=args.model)
    except PermissionError as e:
        print(f"\nAUTH ERROR: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print("\n--- Response ---")
    print(result["reply"])
    print("\n--- Metadata ---")
    print(json.dumps(
        {k: v for k, v in result.items() if k != "reply"},
        indent=2,
    ))


if __name__ == "__main__":
    main()
