# execute_prompt.py
import ast
import json
import re
import string
import time

from utils.database_utils import connect_to_db, join
from llm_utils import call_model
from util_functions import load_prompt


SYSTEM_MESSAGE = 'Act as an style specialist.'

# Configuration
# MODEL = "gpt-4o"
# MODEL = "gemini-2.5-flash"
MODEL = "deepseek-v3"

INPUT_TABLE = 'organizations'
TABLE_ID = 'mutua_id'

# Initialize global variables for tracking tokens and time
start_time = time.perf_counter()


def parse_api_response(response, row_index):
    try:
        content = response.choices[0].message.content

        # Detect CSV format: check if the first line contains at least one ";" or ","
        first_line = content.split("\n")[0]
        if ";" in first_line or "," in first_line or "csv" in first_line:
            print(f"Detected CSV response for row {row_index + 1}. Returning as is.")
            return content  # Return the raw CSV text

        # Remove Markdown code block syntax
        content = content.replace("```json\n", "").replace("\n```", "").strip()
        # Remove newline characters and extra spaces within the JSON string
        content = content.replace("\n", "")
        # Remove control characters from the JSON string
        content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)
        # Replace special double quotation marks with standard double quotation marks
        content = content.replace('“', '"').replace('”', '"')

        try:
            # Extract only the JSON part
            json_content = extract_json(content)
            response_data = json.loads(json_content)
        except (SyntaxError, ValueError):
            # If the response is not a valid Python literal, try to fix it by adding double quotes around property names
            json_content = extract_json(content)
            json_content = re.sub(r"(\w+):", r'"\1":', json_content)
            # Remove backslashes before underscores and any other escaped characters
            json_content = re.sub(r"\\(.)", r"\1", json_content)
            response_data = ast.literal_eval(json_content)

        return response_data

    except (SyntaxError, ValueError) as e:
        print(f"Error parsing API response for row {row_index + 1}: {e}")
        print(f"Response content: {content}")
        return None
    except AttributeError as e:
        if "object has no attribute 'message'" in str(e):
            raise ValueError("The API response does not contain the expected 'message' attribute.")
        else:
            raise e
    except Exception as e:
        print(f"Error parsing API response for row {row_index + 1}: {e}")
        return None


def extract_json(content):
    # Find the JSON-like content within the string
    match = re.search(r'(\{.*\})', content, re.DOTALL)
    if match:
        return match.group(1)
    else:
        raise ValueError("No valid JSON structure found in the content.")


def resolve_table_column_params(row, prompt_template):
    formatter = string.Formatter()
    params = [field_name for _, field_name, _, _ in formatter.parse(prompt_template) if field_name]
    with connect_to_db() as conn:
        for param in params:
            if '.' in param:
                table_name, column_name = param.split('.')
                join_result = join(conn, INPUT_TABLE, table_name, TABLE_ID, [column_name], limit=1)
                join_data = next(join_result, {})
                prompt_template = prompt_template.replace(f"{{{param}}}", str(join_data.get(column_name, '')))
    return prompt_template


def prepare_prompt(row, prompt_template):
    prompt = resolve_table_column_params(row, prompt_template)
    template_keys = [key for _, key, _, _ in string.Formatter().parse(prompt) if key is not None]
    missing_keys = [key for key in template_keys if key not in row]
    if missing_keys:
        print("Missing keys in row:", missing_keys)
    return prompt.format(**row)


def execute_prompt(row, prompt_template=None, prompt_template_path=None, api_model=MODEL, row_index=0):
    if not api_model:
        api_model = MODEL

    try:
        if prompt_template is None and prompt_template_path is None:
            raise ValueError("Either prompt_template or prompt_template_path must be provided.")

        if prompt_template is None:
            prompt_template = load_prompt(prompt_template_path)

        prompt = prepare_prompt(row, prompt_template)
        print("INPUT", {"row_index": row_index + 1, "prompt": prompt})

        messages = [
            {"role": "system", "content": "You are a fashion expert with knowledge in AI and semiotics."},
            {"role": "user", "content": prompt}
        ]
        response = call_model(messages, api_model)
        # Check if the response is valid before parsing
        if response is None:
            print(f"Failed to get a response from the model for row {row_index + 1}. Skipping.")
            return None

        response_data = parse_api_response(response, row_index)
        print("OUTPUT:")
        print(response_data)

        return response_data
    except Exception as e:
        print(f"Error executing prompt for row {row_index + 1}", e)
        return None


def start_conversation(row, prompt_template, model=MODEL, temperature=1):

    if not model:
        model = MODEL

    prompt = prepare_prompt(row, prompt_template)
    conversation_context = [{"role": "system", "content": "You are an Environmental Analyst."}]
    conversation_context, response = add_message(conversation_context, "user", prompt, model, temperature)

    return conversation_context, response


def add_message(conversation_context, role, new_message, model=MODEL, temperature=1):
    global conversation_interaction_count
    if not model:
        model = MODEL
    conversation_context.append({"role": role, "content": new_message})
    response = call_model(conversation_context, model=model, temperature=temperature)
    if response:
        assistant_message = response.choices[0].message.content
        conversation_context.append({"role": "assistant", "content": assistant_message})

        # Use the global variable for the interaction count (part number)
        # from utils.logging_utils import save_prompt
        # save_prompt("conversation", output_text=assistant_message)

        # Increment the interaction count after logging
        conversation_interaction_count += 1
    return conversation_context, response