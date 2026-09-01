# LLM API Client (Python)

A small command-line tool that sends a prompt to an LLM provider's API and
handles the realistic failure modes a support engineer needs to recognize:
authentication errors, rate limits, and server errors — with retries and
latency/token logging.

## Setup

1. Get a free API key from Google AI Studio: https://aistudio.google.com/apikey
   (Gemini has a generous free tier — no credit card needed to start.)

2. Install the one dependency:
   ```
   pip install requests
   ```

3. Set your key as an environment variable:
   ```
   # Mac/Linux
   export LLM_API_KEY="your-key-here"

   # Windows (PowerShell)
   $env:LLM_API_KEY="your-key-here"
   ```

## Run it

```
python llm_client.py "Explain what an API rate limit is in one sentence."
```

You'll see the model's reply plus metadata: latency in ms, tokens used, and
how many attempts it took.

## What it demonstrates (and how to talk about it in the interview)

| Concept | Where it's handled in the code |
|---|---|
| **Authentication** | `Authorization: Bearer` header built from an env var, never hardcoded |
| **401 Unauthorized** | Treated as non-retryable — a bad key won't fix itself on retry |
| **429 Rate limit** | Retried with exponential backoff; respects `Retry-After` header if the provider sends one |
| **5xx server errors** | Retried a limited number of times, since these are often transient |
| **Timeouts / connection errors** | Caught separately from HTTP error codes, also retried |
| **Latency** | Measured per request with `time.time()` around the call |
| **Token usage** | Read from the `usage` field the API returns, to show cost/consumption |

### If asked "walk me through a project you built"

A good structure: *"I built a small Python client that calls an LLM API
directly, so I could see firsthand what customers experience — including
the error cases. I specifically handled 401 differently from 429: a bad key
should fail immediately and tell the user to fix their credentials, but a
rate limit should be retried automatically with backoff, because it's often
temporary. That distinction is exactly the kind of thing I'd need to
recognize quickly in a support ticket."*

## Switching providers

The script uses the OpenAI-compatible `chat/completions` format. To switch
from Gemini to OpenAI, just change `BASE_URL` and `MODEL` at the top of
`llm_client.py` — the request/response handling code doesn't need to change.
This mirrors what an LLM API aggregation product (like LLMAPI.ai) does for
its customers: one integration shape, multiple providers underneath.

## Possible next steps (good to mention as "what I'd add next")

- Streaming responses (`stream: true`) instead of waiting for the full reply
- A `--provider` flag to switch providers without editing the file
- Logging results to a file/CSV to spot patterns over many requests
