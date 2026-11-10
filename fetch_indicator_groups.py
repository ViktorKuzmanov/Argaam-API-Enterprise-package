"""Pull all macroeconomic indicator groups and save them to data/macroeconomic/indicator_groups.json.

Run:  python fetch_indicator_groups.py
"""
from argaam_client import fetch_and_save

if __name__ == "__main__":
    data, file = fetch_and_save("indicator_groups")
    count = len(data) if isinstance(data, list) else len(data.get("data", data)) if isinstance(data, dict) else "?"
    print(f"Saved {count} items to {file}")
