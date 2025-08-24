# database_utils_sqlite.py
# This script has been adapted for use with Python's built-in sqlite3 library, instead of postgres lib

import sqlite3
import pandas as pd
import re

DATABASE_PATH = "../styletelling.sqlite"


# Database connection functions
def connect_to_db():
    """Establishes a connection to the SQLite database."""
    return sqlite3.connect(DATABASE_PATH)


def fetch_dict(conn, sql_query, columns, params=None, batch_size=1000):
    """
    Core generator function to fetch rows from a cursor and yield dictionaries.
    This function is generic and did not require changes.
    """
    cur = conn.cursor()

    # Execute the query
    if params:
        cur.execute(sql_query, params)
    else:
        cur.execute(sql_query)

    # Loop indefinitely to fetch batches of rows
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            # No more rows left, break the loop and the generator will stop
            break
        # Yield each row from the current batch
        for row in rows:
            yield dict(zip(columns, row))


def fetch(conn, table_name, columns=None, where=None, order_by=None, limit=None):
    """
    Fetches data from a specified table with optional filtering, ordering, and limiting.
    """
    if columns is None:
        columns = get_table_columns(conn, table_name)

    sql_query = f"SELECT {', '.join(columns)} FROM {table_name}"
    params = []

    if where:
        if isinstance(where, dict):
            # CORRECTED: Changed placeholder from %s to ? for SQLite
            where_clause = ' AND '.join([f"{key} = ?" for key in where.keys()])
            sql_query += f" WHERE {where_clause}"
            params.extend(where.values())
        else:
            # WARNING: Using a raw string for the 'where' clause is vulnerable to SQL injection.
            # It is safer to use a dictionary for the 'where' argument.
            sql_query += f" WHERE {where}"

    if order_by:
        sql_query += f" ORDER BY {order_by}"
    if limit is not None and limit > 0:
        sql_query += f" LIMIT {limit}"

    return fetch_dict(conn, sql_query, columns, params)


def fetch_first(conn, table_name, columns, where=None, order_by=None):
    """Fetches the first row from a specified table with optional filtering and ordering."""
    result = fetch(conn, table_name, columns, where=where, order_by=order_by, limit=1)
    return next(result, None)


def fetch_double_check(conn, input_table, output_table, id_column, columns, where_input=None, where_output=None,
                       limit=None):
    """
    Fetches data from input_table that does not exist in output_table.
    WARNING: This function constructs a query from raw strings and is highly vulnerable
             to SQL injection if the 'where' arguments are not carefully sanitized.
    """
    sql_query = f"SELECT {', '.join(columns)} FROM {input_table} WHERE "

    if where_input:
        sql_query += f"{where_input} AND "
    else:
        sql_query += "1=1 AND "

    sql_query += f"""
            NOT EXISTS (
                SELECT 1
                FROM {output_table}
                WHERE {output_table}.{id_column} = {input_table}.{id_column}
    """
    if where_output:
        sql_query += f" AND {where_output}"
    sql_query += ")"

    if limit is not None and limit > 0:
        sql_query += f" LIMIT {limit}"

    return fetch_dict(conn, sql_query, columns)


def execute_query(conn, sql, params=None):
    """
    Executes a SQL query (e.g., UPDATE, DELETE) with given parameters.
    """
    cur = conn.cursor()
    try:
        cur.execute(sql, params or [])
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Failed to execute query: {e}") from e


def query(conn, sql, clean_text=False):
    """Executes a SQL query and returns the results as a pandas DataFrame."""
    cur = conn.cursor()
    cur.execute(sql)
    columns = [desc[0] for desc in cur.description]
    data = cur.fetchall()
    df = pd.DataFrame(data, columns=columns)

    if clean_text:
        pattern = r'[\x00-\x1f\x7f-\x9f]|[\u200e\u200f\u202a-\u202e]'
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: re.sub(pattern, '', str(x)) if x is not None else x)
    return df


def insert(conn, table, columns, values):
    """
    Inserts a new row into the specified table and returns the last inserted row ID.
    CORRECTED: Rewritten to use '?' placeholders and 'cursor.lastrowid' for SQLite compatibility.
    """
    column_names = ', '.join(columns)
    placeholders = ', '.join(['?'] * len(values))
    insert_query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

    cur = conn.cursor()
    try:
        cur.execute(insert_query, values)
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Failed to insert row: {e}") from e


def update(conn, table, data, condition):
    """
    Updates a row in the specified table based on the provided condition.
    CORRECTED: Changed placeholder from %s to ? for SQLite.
    """
    set_clause = ', '.join([f"{key} = ?" for key in data.keys()])
    where_clause = ' AND '.join([f"{key} = ?" for key in condition.keys()])
    update_query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
    values = list(data.values()) + list(condition.values())
    execute_query(conn=conn, sql=update_query, params=values)


def delete(conn, table, condition):
    """
    Deletes rows from the specified table based on the provided condition.
    CORRECTED: Changed placeholder from %s to ? for SQLite.
    """
    placeholders = ' AND '.join([f"{key} = ?" for key in condition.keys()])
    delete_query = f"DELETE FROM {table} WHERE {placeholders}"
    values = list(condition.values())
    execute_query(conn=conn, sql=delete_query, params=values)


def join(conn, main_table, join_table, main_table_id, columns, join_table_id=None, where=None, limit=None):
    """
    Performs an inner join between two tables and returns the specified columns.

    Args:
        conn: The database connection object.
        main_table: The name of the main table.
        join_table: The name of the table to join with the main table.
        main_table_id: The name of the joining column in the main table.
        columns: A list of column names to select from the joined tables.
        join_table_id: The name of the joining column in the join table.
                       If not provided, it is assumed to be the same as main_table_id.
        where: A dictionary representing the WHERE clause conditions.
               The keys and values will be used to construct the WHERE clause.
        limit: The maximum number of rows to fetch.

    Returns:
        A generator yielding dictionaries representing the fetched rows.
    """
    if join_table_id is None:
        join_table_id = main_table_id

    sql_query = f"""
        SELECT {', '.join(columns)}
        FROM {main_table}
        JOIN {join_table} ON {main_table}.{main_table_id} = {join_table}.{join_table_id}
    """

    params = []
    if where:
        # CORRECTED: Changed placeholder from %s to ? for SQLite
        where_clause = ' AND '.join([f"{main_table}.{key} = ?" for key in where.keys()])
        sql_query += f" WHERE {where_clause}"
        params = list(where.values())

    if limit is not None and limit > 0:
        sql_query += f" LIMIT {limit}"

    # The fetch_dict function will handle the query execution
    return fetch_dict(conn, sql_query, columns, params)


def insert_or_update(conn, table, columns, values, condition):
    """
    Inserts a new row or updates an existing row if a condition is met.
    """
    existing_record = fetch_first(conn, table, columns=['*'], where=condition)

    if existing_record:
        update_data = dict(zip(columns, values))
        update(conn, table, update_data, condition)
    else:
        insert(conn, table, columns, values)


def insert_or_ignore(conn, table, columns, values):
    """
    Inserts a new row into the specified table, ignoring conflicts.
    CORRECTED: Changed placeholder from %s to ? for SQLite.
    """
    column_names = ', '.join(columns)
    placeholders = ', '.join(['?'] * len(values))
    insert_query = f"INSERT OR IGNORE INTO {table} ({column_names}) VALUES ({placeholders})"
    execute_query(conn, insert_query, values)


def get_table_columns(conn, table_name):
    """
    Retrieve column names from the specified table using PRAGMA for SQLite.
    CORRECTED: Rewritten completely for SQLite compatibility.
    """
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    # The column name is the second item (index 1) in each returned row
    return [row[1] for row in cur.fetchall()]


def get_row_count(conn, table_name, where=None, params=None):
    """
    Returns the number of rows in a table, optionally with a WHERE clause.
    """
    sql_query = f"SELECT COUNT(*) FROM {table_name}"
    if where:
        sql_query += f" WHERE {where}"

    cur = conn.cursor()
    cur.execute(sql_query, params or [])
    return cur.fetchone()[0]

# REMOVED: get_column_lengths
# The function get_column_lengths was removed as it is incompatible with SQLite's
# data model. SQLite's column types (like TEXT) do not have a predefined maximum length.