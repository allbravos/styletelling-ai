# util_functions.py
import os
import re
import time
import pandas as pd

# util_functions.py  (add near the top)
def to_int_safe(value, default=0):
    """
    Convert value to int robustly:
    - accepts int/float/'10'/'10.0'/' 10 '/None/''
    - falls back to default on error
    """
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if s == "":
            return default
        # allow "10.0" etc.
        return int(float(s))
    except Exception:
        return default


def detect_separator(file_path):
    """Detect the CSV separator of the file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        first_line = file.readline()
        if ";" in first_line and "," not in first_line:
            return ";"
        else:
            return ","


def load_dataframe(file_path, start_row, number_of_executions):
    """Load the file into a pandas DataFrame. The function can handle both CSV and Excel files."""
    # Check the file extension
    file_extension = os.path.splitext(file_path)[1]

    # If it's a CSV file, detect the separator and load it into a DataFrame
    if file_extension.lower() in ['.csv']:
        separator = detect_separator(file_path)
        if number_of_executions == 0:
            df = pd.read_csv(file_path, delimiter=separator, skiprows=range(1, start_row))
        else:
            df = pd.read_csv(file_path, delimiter=separator, skiprows=range(1, start_row)).head(number_of_executions)
    # If it's an Excel file, load it into a DataFrame
    elif file_extension.lower() in ['.xls', '.xlsx']:
        if number_of_executions == 0:
            df = pd.read_excel(file_path, engine='openpyxl', skiprows=range(1, start_row))  # engine is optional, depending on your version of pandas
        else:
            df = pd.read_excel(file_path, engine='openpyxl', skiprows=range(1, start_row)).head(number_of_executions)
    else:
        raise ValueError(f"Unsupported file type: {file_extension}. The file must be a .csv or .xlsx/.xls format.")

    return df


def load_prompt(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:  # Specify utf-8 encoding here
        return file.read().strip()


def load_taxonomy(filepath: str) -> str:
    return load_prompt(filepath)  # Since the logic is the same, we can reuse the load_prompt function


def save_to_csv(dataframe: pd.DataFrame, filepath: str) -> None:
    dataframe.to_csv(filepath, index=False)


def save_to_excel(dataframe: pd.DataFrame, filepath: str) -> None:
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        dataframe.to_excel(writer, sheet_name='Scores', index=False)


def convert_csv_to_excel(csv_file_path: str, excel_file_path: str) -> None:

    # Read the CSV into a DataFrame
    dataframe = load_dataframe(csv_file_path, 1, 0)

    # Save the DataFrame to an Excel file
    with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
        dataframe.to_excel(writer, sheet_name='Data', index=False)


def extract_params_from_text(text):
    pattern = r"\{(\w+)\}"
    columns = re.findall(pattern, text)
    return list(set(columns))  # Remove duplicates


def print_separator():
    print("\n" + "-"*50 + "\n")


def formatted_print(content, title=None):
    print_separator()
    if title:
        print(title)
    print(content)


def print_time_stats(start_time, current_iteration, total_iterations):
    # Calculate elapsed time with higher precision
    elapsed_time = time.perf_counter() - start_time

    # Avoid division by zero and inaccurate early estimates
    if current_iteration > 0:
        avg_time_per_iteration = elapsed_time / current_iteration
    else:
        avg_time_per_iteration = elapsed_time

    remaining_iterations = total_iterations - current_iteration
    estimated_remaining_time = avg_time_per_iteration * remaining_iterations

    # Calculate hours, minutes, and seconds for a more precise estimate
    hours, rem = divmod(estimated_remaining_time, 3600)
    minutes, seconds = divmod(rem, 60)

    # Calculate elapsed hours, minutes, and seconds
    elapsed_hours, rem_elapsed = divmod(elapsed_time, 3600)
    elapsed_minutes, elapsed_seconds = divmod(rem_elapsed, 60)

    # Assuming print_separator is a function that prints a line separator
    print_separator()

    # Display the current iteration, total, average time, elapsed time, and estimated remaining time
    print(f"Processing organization {current_iteration + 1} of {total_iterations}.\n"
          f"Average time per organization: {avg_time_per_iteration:.2f} seconds.\n"
          f"Elapsed time: {int(elapsed_hours)} hours, {int(elapsed_minutes)} minutes, {elapsed_seconds:.2f} seconds.\n"
          f"Estimated time remaining: {int(hours)} hours, {int(minutes)} minutes, {seconds:.2f} seconds.")
