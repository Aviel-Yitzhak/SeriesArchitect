import time
import sys
import os

# Append current directory to sys.path to ensure imports work correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db_utils import fetch_query
from etl_processor import discover_series_ids, fetch_raw_data, save_to_db


def update_catalog_by_language(lang_code="en", pages=1):
    """
    Fetches new series from TMDB based on language.
    Useful for expanding the catalog (e.g., adding Korean or Spanish series).

    :param lang_code: Language code (e.g., 'es', 'he', 'ko').
    :param pages: Number of pages to scan (20 series per page).
    """
    print(f"--- Starting Catalog Update (Language: {lang_code}, Pages: {pages}) ---")

    # 1. Discovery Phase
    new_ids = discover_series_ids(lang_code=lang_code, pages=pages)
    print(f"Discovered {len(new_ids)} series IDs.")

    count = 0
    for tmdb_id in new_ids:
        # 2. ETL Execution Phase
        # Fetch raw data automatically handles status, country, and TBA logic
        data = fetch_raw_data(tmdb_id)
        if data:
            save_to_db(data)
            print(f"Saved: {data['title_en']}")
            count += 1
        time.sleep(0.1)  # Rate limiting for API

    print(f"--- Finished. Added/Updated {count} series. ---")


def run_maintenance_repair():
    """
    Iterates over all existing series in the database and updates them via TMDB.
    Essential for fixing data bugs (e.g., missing countries) and updating series status.
    """
    print("--- Starting Maintenance Repair Protocol ---")

    # 1. Fetch all existing IDs from DB
    query = "SELECT tmdb_id FROM series"
    rows = fetch_query(query)

    if not rows:
        print("Database is empty. Nothing to repair.")
        return

    total = len(rows)
    print(f"Found {total} series in database. Starting update...")

    for i, row in enumerate(rows):
        # Access by INDEX (0) because fetch_query returns Tuples in your db_utils
        tmdb_id = row[0]

        # Log progress every 10 items to avoid clutter
        if i % 10 == 0:
            print(f"Processing {i}/{total}...")

        # 2. Re-fetch and Save
        # This forces the ETL to re-process and apply all current logic fixes
        data = fetch_raw_data(tmdb_id)
        if data:
            save_to_db(data)

        time.sleep(0.1)

    print("--- Maintenance Complete. All series are up to date. ---")


if __name__ == "__main__":
    # Usage Examples:

    # 1. Expand Catalog (e.g., add top Spanish series):
    # update_catalog_by_language('es', pages=2)

    # 2. Maintain & Fix Existing Data:
    # run_maintenance_repair()
    run_maintenance_repair()