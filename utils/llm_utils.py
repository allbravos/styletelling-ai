# llm_utils.py
import time
import os
from openai import OpenAI, APIError, RateLimitError, AuthenticationError

# --- API Key ---
# Place the API key for the service you want to use (OpenAI, DeepSeek, Google) here.
API_KEY = 'sk-3f6fb6901cd04b238c9c974b1e067311'

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
    "gpt-4o": {
        "provider": "openai",
        "model_name": "gpt-4o",
        "cost_per_million": {"input": 5.0, "output": 15.0}
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


def call_model(messages, model=current_model, response_format=None, retry=False, temperature=0.8):
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
