# config_manager.py
"""
Handles loading and saving the application's configuration (categories, rules, history)
to a JSON file. Provides default settings if the file is missing or corrupted.
"""

import json
import os

CONFIG_FILE = "clipboard_manager_config.json"

# --- Configuration Loading ---

def load_config():
    """Loads categories, rules, and history from the JSON config file.
    Returns default categories if loading fails.
    """
    if not os.path.exists(CONFIG_FILE):
        print(f"Config file {CONFIG_FILE} not found. Initializing defaults.")
        return initialize_default_categories()

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)

        if not isinstance(loaded_data, dict):
            print("Error: Config file format is invalid (not a dictionary). Initializing defaults.")
            return initialize_default_categories()

        # Validate and sanitize loaded data
        categories = {}
        for cat, data in loaded_data.items():
            if isinstance(data, dict):
                categories[cat] = {
                    "rules": data.get("rules", []),
                    "history": data.get("history", []),
                    "pinned_history": data.get("pinned_history", [])
                }
            else:
                print(f"Warning: Malformed entry for category '{cat}' in config. Resetting.")
                categories[cat] = {"rules": [], "history": [], "pinned_history": []}

        print(f"Configuration loaded from {CONFIG_FILE}")

    except json.JSONDecodeError:
        print(f"Error decoding JSON from {CONFIG_FILE}. Initializing defaults.")
        return initialize_default_categories()
    except Exception as e:
        print(f"An unexpected error occurred during config load: {e}")
        return initialize_default_categories()

    # Ensure the essential 'Uncategorized' category exists
    if "Uncategorized" not in categories:
        categories["Uncategorized"] = {"rules": [], "history": [], "pinned_history": []}

    return categories

def initialize_default_categories():
    """Returns a dictionary with predefined default categories and rules."""
    print("Initialized with default categories.")
    return {
        "Uncategorized": {"rules": [], "history": [], "pinned_history": []},
        "Code": {"rules": ["def ", "class ", "import ", "function(", "=>", "{", "}"], "history": [], "pinned_history": []},
        "Links": {"rules": [r"regex:https?://", r"regex:www\\."], "history": [], "pinned_history": []},
        "Text": {"rules": [], "history": [], "pinned_history": []} # Catch-all for general text if needed
    }

# --- Configuration Saving ---

def save_config(categories_data):
    """Saves the provided categories data (rules and history) to the JSON file."""
    data_to_save = {}
    for cat_name, cat_data in categories_data.items():
        # Ensure only serializable data (rules, history, pinned_history) is saved
        data_to_save[cat_name] = {
            "rules": cat_data.get("rules", []),
            "history": cat_data.get("history", []),
            "pinned_history": cat_data.get("pinned_history", [])
        }

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        print(f"Configuration saved to {CONFIG_FILE}")
        return True # Success
    except Exception as e:
        print(f"Error saving configuration to {CONFIG_FILE}: {e}")
        return False # Failure
