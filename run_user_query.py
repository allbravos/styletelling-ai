# run_user_query.py
# This script processes a user query to find product recommendations.
# Updated to include context reporting for UI display.

import sqlite3
import json
import concurrent.futures
from utils.execute_prompt import execute_prompt
from utils.util_functions import to_int_safe

# Path to the SQLite database
DATABASE_PATH = "styletelling.sqlite"

# --- Constants (unchanged) ---
ATTRIBUTE_INFO = {
    "Material": {"attr_name": "material", "table": "material"},
    "Cor": {"attr_name": "color", "table": "color"},
    "Estrutura": {"attr_name": "structure", "table": "structure"},
    "Linha": {"attr_name": "line", "table": "line"},
    "Textura": {"attr_name": "texture", "table": "texture"},
    "Superfície": {"attr_name": "surface", "table": "surface"},
    "Mensagem": {"attr_name": "message", "table": "message_titles"},
}

PROMPT_MAPPING = {
    "Mensagem": "./prompts/prompt_1_att_mensagem.txt",
    "Linha": "./prompts/prompt_2_att_linha.txt",
    "Material": "./prompts/prompt_3_att_material.txt",
    "Estrutura": "./prompts/prompt_4_att_estrutura.txt",
    "Textura": "./prompts/prompt_5_att_textura.txt",
    "Superfície": "./prompts/prompt_6_att_superficie.txt",
    "Cor": "./prompts/prompt_7_att_cor.txt",
    "ContextAnalyzer": "./prompts/prompt_context_analyzer.txt"
}

# --- Exclusion rules (unchanged) ---
OCCASION_EXCLUSIONS = {
    ("FORMAL", "DIA", "CAMPO", "FESTA"): {"Material": ["Couro", "Jeans", "Malha | Retilínea"],
                                          "Superfície": ["Brilhante"]},
    ("FORMAL", "NOITE", "CAMPO", "FESTA"): {"Material": ["Couro", "Jeans", "Malha | Retilínea"]},
    ("INFORMAL", "DIA", "CIDADE", "ESPORTE"): {"Material": ["Couro", "Jeans", "Tecido festivo", "Tecido plano"]},
    ("INFORMAL", "DIA", "CIDADE", "LAZER"): {"Material": ["Couro", "Jeans", "Tecido festivo"]},
    ("INFORMAL", "DIA", "CIDADE", "ATIVIDADES DIA A DIA"): {"Material": ["Tecido festivo", "Tecido plano"]},
    ("INFORMAL", "NOITE", "CIDADE", "ESPORTE"): {"Material": ["Couro", "Jeans", "Tecido festivo", "Tecido plano"],
                                                 "Estrutura": ["Pesado | Estruturado"]},
    ("INFORMAL", "DIA", "PRAIA", "ESPORTE"): {"Material": ["Couro", "Tecido festivo", "Tecido plano"],
                                              "Estrutura": ["Pesado | Estruturado"]},
    ("INFORMAL", "DIA", "PRAIA", "LAZER"): {"Material": ["Couro", "Tecido festivo", "Tecido plano"]},
    ("INFORMAL", "DIA", "PRAIA", "FESTA"): {"Material": ["Couro", "Tecido festivo", "Tecido plano"]},
    ("INFORMAL", "DIA", "PRAIA", "ATIVIDADES DIA A DIA"): {"Material": ["Couro", "Jeans", "Tecido festivo"]},
    ("INFORMAL", "NOITE", "PRAIA", "LAZER"): {"Material": ["Couro", "Tecido festivo"],
                                              "Estrutura": ["Pesado | Estruturado"]},
    ("INFORMAL", "NOITE", "PRAIA", "FESTA"): {"Material": ["Couro", "Tecido festivo"]},
    ("INFORMAL", "DIA", "CAMPO", "ESPORTE"): {"Material": ["Tecido festivo"]},
    ("INFORMAL", "DIA", "CAMPO", "LAZER"): {"Material": ["Tecido festivo"]},
    ("INFORMAL", "DIA", "CAMPO", "FESTA"): {"Material": ["Tecido festivo"]},
    ("INFORMAL", "DIA", "CAMPO", "ATIVIDADES DIA A DIA"): {"Material": ["Tecido festivo", "Tecido plano"]},
    ("INFORMAL", "NOITE", "CAMPO", "LAZER"): {"Material": ["Tecido festivo"], "Estrutura": ["Pesado | Estruturado"]}
}

WEATHER_EXCLUSIONS = {
    "Hot": {"Estrutura": ["Pesado | Estruturado"]},
    "Cold": {"Estrutura": ["Leve | Fluido"]}
}


def analyze_single_attribute(attr_name, user_query_row):
    """Analyzes a single attribute by calling the LLM (unchanged)."""
    if attr_name not in PROMPT_MAPPING:
        return None
    prompt_path = PROMPT_MAPPING[attr_name]
    return execute_prompt(user_query_row, prompt_template_path=prompt_path)


def normalize_attribute_name(raw_attr):
    """Handles cases like "Linha | Forma" by taking the part before '|' (unchanged)."""
    return raw_attr.split('|')[0].strip()


def search_products_with_details(detailed_results, category_name=None, limit=3):
    """Finds and ranks products based on style attributes (unchanged)."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    triples = []
    if not detailed_results:
        conn.close()
        return []

    for block in detailed_results:
        key = normalize_attribute_name(block.get("attribute", ""))
        info = ATTRIBUTE_INFO.get(key)
        if not info:
            continue

        cur.execute("SELECT id FROM attributes WHERE name = ?", (info["attr_name"],))
        row = cur.fetchone()
        if not row:
            continue
        attr_id = row["id"]

        for i in (1, 2, 3):
            val_id, val_score = block.get(f"value_{i}_id"), block.get(f"value_{i}_score")
            if val_id is not None and val_score is not None:
                triples.append((attr_id, to_int_safe(val_id), to_int_safe(val_score)))

    if not triples:
        conn.close()
        return []

    case_parts, params = [], []
    for att_id, val_id, score in triples:
        case_parts.append("WHEN attribute_id = ? AND value_id = ? THEN score * ?")
        params.extend([att_id, val_id, score])
    case_sql = f"CASE {' '.join(case_parts)} ELSE 0 END"

    ranked_subq = f"SELECT product_id, SUM({case_sql}) AS relevance_score FROM products_taxonomy GROUP BY product_id"

    where_clause = ""
    if category_name:
        where_clause = "WHERE p.category = ?"
        params.append(category_name)

    final_sql = f"""
      SELECT p.product_id, p.name, p.price, p.image_url, p.category, p.description, ranked.relevance_score
      FROM ({ranked_subq}) AS ranked
      JOIN products p ON p.product_id = ranked.product_id
      {where_clause} ORDER BY ranked.relevance_score DESC LIMIT ?
    """
    params.append(limit)

    cur.execute(final_sql, params)
    rows = cur.fetchall()
    conn.close()

    product_list = []
    for r in rows:
        product_dict = dict(r)
        price_val = product_dict.get('price')
        if isinstance(price_val, (int, float)):
            price_in_reais = price_val / 100.0
            product_dict['price'] = f"R$ {price_in_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        product_list.append(product_dict)

    return product_list


def process_user_query_streaming(user_query, category_score_threshold=6):
    """
    Enhanced generator function that processes the user query and yields
    status updates and results at each step, including context analysis.
    """

    # === Step 1: Analyze Occasion and Weather ===
    yield {"status": "progress", "message": "➡️ Step 1/6: Analyzing occasion and weather..."}
    context_prompt_path = PROMPT_MAPPING["ContextAnalyzer"]
    context_row = {"user_query": user_query}
    context_results = execute_prompt(context_row, prompt_template_path=context_prompt_path)

    # Fallback to an empty context if the prompt fails
    if not context_results:
        context_results = {"occasion": {}, "weather": {}}

    # NEW: Yield context results for UI display
    yield {"status": "context_result", "data": context_results}

    # Pass the full context to subsequent prompts
    row_with_context = {
        "user_query": user_query,
        "query_context": json.dumps(context_results, ensure_ascii=False)
    }

    # === Step 2: Get top 5 attributes ===
    yield {"status": "progress", "message": "➡️ Step 2/6: Selecting the most relevant style attributes..."}
    prompt_0_path = "./prompts/prompt_0_attribute_selection.txt"
    attribute_results = execute_prompt(row_with_context, prompt_template_path=prompt_0_path)
    if not attribute_results:
        yield {"status": "error", "message": "Failed to get initial attribute selection."}
        return

    top_attributes_from_prompt = [attribute_results.get(f"att_{i}") for i in range(1, 6) if
                                  attribute_results.get(f"att_{i}")]
    yield {
        "status": "intermediate_result",
        "type": "attributes",
        "data": top_attributes_from_prompt
    }

    # === Step 3: Analyze each selected attribute in parallel ===
    yield {"status": "progress", "message": "➡️ Step 3/6: Analyzing each attribute in detail..."}
    detailed_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_attribute = {executor.submit(analyze_single_attribute, attr, row_with_context): attr for attr in
                               top_attributes_from_prompt}
        for future in concurrent.futures.as_completed(future_to_attribute):
            try:
                result = future.result()
                if result:
                    detailed_results.append(result)
            except Exception as e:
                print(f"An exception occurred: {e}")

    if not detailed_results:
        yield {"status": "error", "message": "Could not get detailed attribute values."}
        return

    # === Step 4: Apply Exclusion Rules ===
    yield {"status": "progress", "message": "➡️ Step 4/6: Applying occasion and weather exclusion rules..."}

    # Get current context
    occ = context_results.get("occasion", {})
    weather = context_results.get("weather", {})
    occasion_key = (occ.get("formality"), occ.get("time"), occ.get("location"), occ.get("activity"))
    climate = weather.get("climate")

    # Get relevant exclusion rules
    occasion_rules = OCCASION_EXCLUSIONS.get(occasion_key, {})
    weather_rules = WEATHER_EXCLUSIONS.get(climate, {})

    filtered_detailed_results = []
    for result_block in detailed_results:
        attr_name = normalize_attribute_name(result_block["attribute"])

        # Combine exclusions for the current attribute
        exclusions = set(occasion_rules.get(attr_name, []))
        exclusions.update(weather_rules.get(attr_name, []))

        if not exclusions:
            filtered_detailed_results.append(result_block)
            continue

        # Rebuild the value block, excluding filtered items
        new_values = []
        for i in range(1, 4):
            value_name = result_block.get(f"value_{i}_name")
            if value_name and value_name not in exclusions:
                new_values.append({
                    "id": result_block.get(f"value_{i}_id"),
                    "name": value_name,
                    "score": result_block.get(f"value_{i}_score"),
                    "justification": result_block.get(f"value_{i}_justification")
                })

        if new_values:
            new_block = {"attribute": result_block["attribute"]}
            for i, val in enumerate(new_values, 1):
                new_block[f"value_{i}_id"] = val["id"]
                new_block[f"value_{i}_name"] = val["name"]
                new_block[f"value_{i}_score"] = val["score"]
                new_block[f"value_{i}_justification"] = val["justification"]
            filtered_detailed_results.append(new_block)

    # === Step 5: Select relevant product categories ===
    yield {"status": "progress", "message": "➡️ Step 5/6: Identifying relevant product categories..."}
    VALUE_SCORE_THRESHOLD = 7
    fashion_attributes_list = []
    for res in filtered_detailed_results:  # Use filtered results
        attr_name = res.get("attribute")
        if not attr_name: continue
        if res.get("value_1_name"):
            fashion_attributes_list.append(f'{attr_name}: {res.get("value_1_name")}')
        if res.get("value_2_name") and isinstance(res.get("value_2_score"), int) and res.get(
                "value_2_score") >= VALUE_SCORE_THRESHOLD:
            fashion_attributes_list.append(f'{attr_name}: {res.get("value_2_name")}')

    category_prompt_row = {"user_query": user_query,
                           "fashion_attributes": json.dumps(fashion_attributes_list, ensure_ascii=False)}
    category_results = execute_prompt(category_prompt_row, prompt_template_path="./prompts/prompt_look_composer.txt")

    relevant_categories = []
    if category_results:
        for i in range(1, 6):
            cat_name = category_results.get(f'cat_{i}')
            cat_score = category_results.get(f'cat_{i}_score')
            if cat_name and isinstance(cat_score, int) and cat_score > category_score_threshold:
                relevant_categories.append(cat_name)

    yield {
        "status": "intermediate_result",
        "type": "categories",
        "data": relevant_categories
    }

    if not relevant_categories:
        yield {"status": "final_message", "message": "No relevant product categories found for this query."}
        return

    # === Step 6: Find top 3 products for each category ===
    yield {"status": "progress", "message": "➡️ Step 6/6: Searching for top products..."}
    product_recommendations = {}
    for category in relevant_categories:
        products = search_products_with_details(detailed_results=filtered_detailed_results, category_name=category,
                                                limit=3)  # Use filtered results
        product_recommendations[category] = products

    # === Final Step: Yield the complete results ===
    yield {"status": "final_result", "data": product_recommendations}


if __name__ == '__main__':
    import pprint

    test_query = "Vou para um casamento de dia no campo"

    print(f"--- Running query: '{test_query}' ---")
    results_generator = process_user_query_streaming(test_query)
    final_results = {}
    for result in results_generator:
        pprint.pprint(result)
        if result.get("status") == "final_result":
            final_results = result.get("data")

    print("\n--- FINAL RESULTS (as returned by the function) ---")
    pprint.pprint(final_results)