# llm_utils.py
import time
import os
from openai import OpenAI, APIError, RateLimitError, AuthenticationError
from config.config import API_KEY

# Number of tokens in one million
TOKENS_PER_MILLION = 1_000_000

# Global counters for usage and cost tracking
total_input_tokens = 0
total_output_tokens = 0
total_cost = 0.0
num_api_calls = 0

last_input_tokens = 0
last_output_tokens = 0
last_cost = 0.0

# Supported model configurations
MODELS = {
    "gpt-5-mini": {
        "provider": "openai",
        "model_name": "gpt-5-mini",
        "cost_per_million": {"input": 0.25, "output": 2.0}
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "cost_per_million": {"input": 0.15, "output": 0.6}
    },
    "deepseek-v3": {
        "provider": "deepseek",
        "model_name": "deepseek-chat",
        "endpoint": "https://api.deepseek.com/v1",
        "cost_per_million": {"input": 0.27, "output": 1.1}
    },
    "gemini-2.5-flash": {
        "provider": "google",
        "model_name": "models/gemini-2.5-flash",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "cost_per_million": {"input": 0.40, "output": 0.60}
    }
}

# Default model to use
current_model = "deepseek-v3"


def call_model(messages, model=current_model, response_format=None, retry=False, temperature=1):
    """
    Send a chat completion request to the specified model using the OpenAI library.
    Automatically picks the endpoint based on model provider configuration.
    Tracks token usage and cost using per-million-token rates.
    """
    global total_input_tokens, total_output_tokens, total_cost, num_api_calls
    global last_input_tokens, last_output_tokens, last_cost, current_model

    current_model = model

    if model not in MODELS:
        available = ", ".join(MODELS.keys())
        raise ValueError(f"Invalid model '{model}'. Available models: {available}")

    info = MODELS[model]
    provider = info["provider"]
    model_name = info["model_name"]
    endpoint = info.get("endpoint")

    # Use the single global API_KEY
    api_key = API_KEY
    if not api_key or api_key == "...":
        raise ValueError(f"API_KEY is not set. Please add your API key for the '{provider}' provider to the script.")

    try:
        if endpoint:
            # Use the custom endpoint for DeepSeek or Google
            client = OpenAI(api_key=api_key, base_url=endpoint)
        else:
            # Use the default OpenAI endpoint
            client = OpenAI(api_key=api_key)

        params = {"model": model_name, "messages": messages, "temperature": temperature}
        if response_format:
            params["response_format"] = response_format

        response = client.chat.completions.create(**params)

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        last_input_tokens = input_tokens
        last_output_tokens = output_tokens

        rates = info["cost_per_million"]
        cost_in = input_tokens * (rates["input"] / TOKENS_PER_MILLION)
        cost_out = output_tokens * (rates["output"] / TOKENS_PER_MILLION)
        last_cost = cost_in + cost_out

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_cost += last_cost
        num_api_calls += 1

        return response

    except AuthenticationError:
        print(f"Authentication failed. Check if the API_KEY is correct for the '{provider}' provider.")
    except RateLimitError:
        print(f"Rate limit exceeded for {provider}. Try again later.")
    except APIError as e:
        print(f"API error from {provider}: {str(e)}")
    except Exception as e:
        print(f"An unexpected error occurred with {provider}: {str(e)}")
        if not retry:
            print("Retrying in 1 second...")
            time.sleep(1)
            return call_model(messages, model, response_format, retry=True, temperature=temperature)
        else:
            print("Retry failed. No further attempts.")
            return None


def print_costs():
    """
    Log the accumulated cost metrics.
    """
    if num_api_calls == 0:
        print("No API calls made yet.")
        return

    avg_cost = total_cost / num_api_calls
    print(f"\n--- Cost Summary ---")
    print(f"Total cost: $ {total_cost:.6f}")
    print(f"Total API calls: {num_api_calls}")
    print(f"Average cost per call: $ {avg_cost:.6f}")
    print(f"Total input tokens: {total_input_tokens}")
    print(f"Total output tokens: {total_output_tokens}")
    print(f"--------------------\n")


# --- ADD: small helper to read the prompt file ---
def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# --- ADD: bench-friendly wrapper (non-breaking) ---
def execute_prompt(
    api_model: str,           # alias from bench (e.g., "deepseek-v3")
    prompt_file: str,         # path to system/prefix prompt
    user_query: str,          # the actual query
    *,
    model_id: str | None = None,   # explicit model id for OpenAI-compatible calls
    api_key: str | None = None,    # provider-specific key
    base_url: str | None = None,   # provider/base endpoint (OpenAI-compatible)
    defaults: dict | None = None,  # temperature, max_tokens, top_p, etc.
    **_,
) -> str:
    """
    Minimal contract for bench.py, without changing the rest of the app:
    - Returns a string (final text)
    - Updates last_input_tokens, last_output_tokens, last_cost
    - Uses OpenAI-compatible path if model_id/base_url/api_key are given
    - Otherwise falls back to existing call_model(...) path used by your app
    """

    # reset per-call globals; bench may compute cost from pricing
    global last_input_tokens, last_output_tokens, last_cost
    last_input_tokens = 0
    last_output_tokens = 0
    last_cost = 0.0

    system_text = _read_text(prompt_file)
    defaults = defaults or {}

    # Messages (works for both paths)
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_query},
    ]

    # --- Path A: explicit OpenAI-compatible call (bench uses this) ---
    if model_id or base_url or api_key:
        client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("TOGETHER_API_KEY"),
            base_url=base_url or None,
        )
        params = {
            "model": model_id or api_model,   # prefer explicit id
            "messages": messages,
        }
        # map common generation params
        if "temperature" in defaults: params["temperature"] = defaults["temperature"]
        if "max_tokens"  in defaults: params["max_tokens"]  = defaults["max_tokens"]
        if "top_p"       in defaults: params["top_p"]       = defaults["top_p"]

        resp = client.chat.completions.create(**params)
        text = (resp.choices[0].message.content or "").strip()

        # usage (if provider returns it)
        if getattr(resp, "usage", None):
            try:
                last_input_tokens  = int(resp.usage.prompt_tokens or 0)
                last_output_tokens = int(resp.usage.completion_tokens or 0)
            except Exception:
                pass
        # last_cost intentionally left at 0.0; bench will compute from pricing
        return text

    # --- Path B: legacy path through your existing call_model (keeps app behavior) ---
    # Choose a temperature fallback consistent with current behavior
    temperature = defaults.get("temperature", 0.8)
    response = call_model(messages, model=api_model, temperature=temperature)
    if response is None:
        return ""  # maintain graceful failure

    # Extract text like the rest of your app
    try:
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""
