# app_gui.py
import tkinter
import tkinter.messagebox
import customtkinter as ctk
import clipboard
import threading
import sys
import os

# Import core components
import config_manager
from clipboard_handler import ClipboardHandler

# Imports for system tray functionality
from pystray import MenuItem as item
import pystray
from PIL import Image

# Configuration constants
HISTORY_LIMIT_PER_CATEGORY = 50
TRAY_ICON_PATH = "icon.png"
WINDOW_ICON_PATH = "my_icon.ico"

# Helper to get resource path for bundled application
def resource_path(relative_path):
    """Get absolute path to resource, works for development and bundled apps."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Use current directory if not bundled
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class ClipboardManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Clipboard Category Manager")
        self.geometry("850x650")

        # Attempt to set window icon
        try:
            icon_full_path = resource_path(WINDOW_ICON_PATH)
            self.iconbitmap(icon_full_path)
        except Exception as e:
            print(f"Warning: Could not set window icon '{WINDOW_ICON_PATH}': {e}")

        # --- Application Data ---
        # Load configuration (categories, rules, history)
        self.categories = config_manager.load_config()
        # Dictionary to hold references to UI elements for each category (e.g., scroll frames)
        self.ui_elements = {}

        # --- UI Setup ---
        self.selected_category_var = ctk.StringVar(value="")
        self._build_ui()

        # Initialize UI state based on loaded data
        self.update_category_tabs()
        self.update_category_dropdown()
        self.update_all_history_displays()
        self._select_initial_category()

        # Create help overlay frame (initially hidden)
        self.create_help_overlay()

        # --- Clipboard Monitoring ---
        # Initialize and start the clipboard monitoring thread
        self.clipboard_handler = ClipboardHandler(
            categories_ref=self.categories,
            process_callback=self._schedule_process_clipboard # Callback to process in main thread
        )
        self.clipboard_handler.start_monitoring()
        self.status_label.configure(text="Status: Monitoring Clipboard")

        # --- System Tray Setup ---
        self.tray_icon = None
        self.setup_tray_icon()
        # Run the tray icon loop in a separate thread to avoid blocking the main UI
        threading.Thread(target=self.run_tray_icon, daemon=True).start()

        # --- Window Protocol ---
        # Change window close behavior to hide instead of quit
        self.protocol("WM_DELETE_WINDOW", self.hide_window_to_tray)

    def _build_ui(self):
        """Configures the main window layout and creates UI widgets."""
        self.grid_columnconfigure(0, weight=1) # Left management frame
        self.grid_columnconfigure(1, weight=3) # Right display frame
        self.grid_rowconfigure(0, weight=1)

        # Left Frame (Category Management)
        self.left_frame = ctk.CTkFrame(self, width=250, corner_radius=10)
        self.left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.left_frame.grid_columnconfigure(0, weight=1)
        self.left_frame.grid_columnconfigure(1, weight=0)
        self.left_frame.grid_rowconfigure(10, weight=1) # Push status label down

        ctk.CTkLabel(self.left_frame, text="Manage Categories", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=(20,5), pady=(20, 10), sticky="w")
        ctk.CTkButton(self.left_frame, text="?", width=25, command=self.show_help_overlay).grid(row=0, column=1, padx=(5, 20), pady=(20, 10), sticky="e")

        # Category Creation Widgets
        self.entry_new_category = ctk.CTkEntry(self.left_frame, placeholder_text="New Category Name")
        self.entry_new_category.grid(row=1, column=0, columnspan=2, padx=20, pady=5, sticky="ew")
        ctk.CTkButton(self.left_frame, text="Add Category", command=self.add_category).grid(row=2, column=0, columnspan=2, padx=20, pady=10)

        # Category Selection & Deletion Widgets
        ctk.CTkLabel(self.left_frame, text="Edit Rules For:").grid(row=3, column=0, columnspan=2, padx=20, pady=(15, 0), sticky="w")
        self.category_dropdown = ctk.CTkOptionMenu(self.left_frame, variable=self.selected_category_var,
                                                   values=[], command=self.update_rule_display)
        self.category_dropdown.grid(row=4, column=0, padx=(20, 5), pady=5, sticky="ew")
        ctk.CTkButton(self.left_frame, text="Delete", width=60, fg_color="red", hover_color="darkred",
                      command=self.delete_selected_category).grid(row=4, column=1, padx=(5, 20), pady=5, sticky="e")

        # Rule Management Widgets
        ctk.CTkLabel(self.left_frame, text="Category Rules (Keywords or regex:pattern)").grid(row=5, column=0, columnspan=2, padx=20, pady=(10, 0), sticky="w")
        self.entry_new_rule = ctk.CTkEntry(self.left_frame, placeholder_text="Enter rule (e.g., 'def ' or 'regex:^http')")
        self.entry_new_rule.grid(row=6, column=0, columnspan=2, padx=20, pady=5, sticky="ew")
        ctk.CTkButton(self.left_frame, text="Add Rule", command=self.add_rule).grid(row=7, column=0, columnspan=2, padx=20, pady=5)

        # Rule Display Frame
        self.rule_display_frame = ctk.CTkScrollableFrame(self.left_frame, label_text="Current Rules")
        self.rule_display_frame.grid(row=8, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")
        self.rule_display_frame.grid_columnconfigure(0, weight=1)

        # Save Button
        ctk.CTkButton(self.left_frame, text="Save Config", command=self.trigger_save_config).grid(row=9, column=0, columnspan=2, padx=20, pady=(20, 10))

        # Status Label
        self.status_label = ctk.CTkLabel(self.left_frame, text="Status: Initializing...", anchor="w")
        self.status_label.grid(row=11, column=0, columnspan=2, padx=20, pady=(10, 10), sticky="sew")

        # Right Frame (History Display)
        self.right_frame = ctk.CTkFrame(self, corner_radius=10)
        self.right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(0, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Tab view for categories
        self.tab_view = ctk.CTkTabview(self.right_frame, corner_radius=10)
        self.tab_view.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

    def _select_initial_category(self):
        """Selects the first category in the dropdown and updates the rule display."""
        available_categories = self.category_dropdown.cget("values")
        if available_categories:
             self.selected_category_var.set(available_categories[0])
        else:
             self.selected_category_var.set("")
        self.update_rule_display()

    # --- Help Overlay Functions ---
    def create_help_overlay(self):
        """Creates the help overlay frame, initially hidden."""
        self.help_overlay_frame = ctk.CTkFrame(self, corner_radius=15, border_width=2)
        self.help_overlay_frame.grid_columnconfigure(0, weight=1)
        self.help_overlay_frame.grid_rowconfigure(1, weight=1)

        help_title_label = ctk.CTkLabel(self.help_overlay_frame, text="How to Use Clipboard Manager", font=ctk.CTkFont(size=18, weight="bold"))
        help_title_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10))

        help_text_frame = ctk.CTkScrollableFrame(self.help_overlay_frame, corner_radius=10)
        help_text_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="nsew")
        help_text_frame.grid_columnconfigure(0, weight=1)

        help_text = """
Welcome to the Clipboard Category Manager!

This app automatically monitors your clipboard and sorts copied text into categories based on rules you define.

How it works:

1.  Categories (Left Panel):
    * Use the 'New Category Name' box and 'Add Category' button to create folders (tabs on the right) for your clipboard items.
    * Select a category from the dropdown menu ('Edit Rules For:') to manage its rules.
    * Click 'Delete' next to the dropdown to remove the selected category (cannot delete 'Uncategorized').

2.  Category Rules (Left Panel):
    * Rules determine which category copied text belongs to.
    * Select a category, then type a rule in the 'Enter rule' box and click 'Add Rule'.
    * Rules are checked in order for each category listed. The first matching rule assigns the item. If no rules match, it goes to 'Uncategorized'.
    * Keyword Rule: Just type a word or phrase (e.g., `import`, `meeting notes`). If the copied text *contains* this phrase, it matches. (Case-sensitive by default).
    * Regex Rule: Start the rule with `regex:` followed by a Python regular expression (e.g., `regex:^\d{3}-\d{2}-\d{4}$` for SSN format, or `regex:https?://` for links). This allows for more complex pattern matching.
    * Click the 'X' next to a rule in the 'Current Rules' list to delete it.

3.  Clipboard History (Right Panel):
    * When you copy text, it's checked against the rules and added to the top of the history list in the matching category's tab on the right.
    * Click the 'Copy' button next to any item in a history list to copy it back to your system clipboard.
    * Click the small 'X' button next to a history item to delete it permanently.

4.  Saving:
    * Click 'Save Config' (Left Panel) to manually save your categories and rules.
    * Configuration (categories, rules, history) is also saved automatically when you close the application using the window's 'X' button or the tray icon's Exit option.

5.  System Tray:
    * Closing the main window with the 'X' button will hide it. The app keeps running in the background.
    * Find the app icon in the system tray (usually in the hidden icons area).
    * Right-click the tray icon for options:
        * Show: Reopens the main window.
        * Exit: Properly closes the application and saves data.

Enjoy managing your clipboard!
"""
        help_content_label = ctk.CTkLabel(help_text_frame, text=help_text, justify=tkinter.LEFT, anchor="w")
        help_content_label.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        close_button = ctk.CTkButton(self.help_overlay_frame, text="Close Help", width=100, command=self.hide_help_overlay)
        close_button.grid(row=2, column=0, columnspan=2, padx=20, pady=(10, 20))

    def show_help_overlay(self):
        """Displays the help overlay frame."""
        self.help_overlay_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=20, sticky="nsew")
        self.help_overlay_frame.tkraise()

    def hide_help_overlay(self):
        """Hides the help overlay frame."""
        self.help_overlay_frame.grid_forget()

    # --- System Tray Functions ---
    def setup_tray_icon(self):
        """Creates the pystray Icon object with menu."""
        icon_full_path = resource_path(TRAY_ICON_PATH)
        try:
            image = Image.open(icon_full_path)
        except FileNotFoundError:
            print(f"Error: Tray icon '{icon_full_path}' not found.")
            image = None # pystray can use a default if image is None
        except Exception as e:
            print(f"Error loading tray icon '{icon_full_path}': {e}")
            image = None

        menu = (
            item('Show', self.show_window, default=True),
            item('Exit', self.quit_application)
        )
        self.tray_icon = pystray.Icon("ClipboardManager", image, "Clipboard Manager", menu)

    def run_tray_icon(self):
        """Runs the system tray icon loop in a separate thread."""
        if self.tray_icon:
            try:
                self.tray_icon.run()
            except Exception as e:
                 print(f"Error running tray icon: {e}")

    def show_window(self):
        """Shows the main application window from the tray."""
        # Use self.after to ensure these run in the main Tkinter thread
        self.after(0, self.deiconify)
        self.after(10, self.lift)
        self.after(20, self.focus_force)

    def hide_window_to_tray(self):
        """Hides the main window instead of closing it."""
        self.withdraw()

    def quit_application(self):
        """Stops monitoring, saves config, stops tray icon, and exits."""
        # Stop clipboard monitoring thread
        if self.clipboard_handler:
            self.clipboard_handler.stop()
            self.clipboard_handler.join() # Wait for thread to finish

        # Save configuration
        self.trigger_save_config()

        # Stop the system tray icon loop
        if self.tray_icon:
             try:
                 self.tray_icon.stop()
             except Exception as e:
                  print(f"Error stopping tray icon: {e}")

        # Destroy the Tkinter window (schedule to run in main thread)
        self.after(50, self.destroy)

    # --- Helper to ensure 'Uncategorized' exists ---
    def _ensure_uncategorized_exists(self):
        """Ensures the 'Uncategorized' category is present in the data structure."""
        if "Uncategorized" not in self.categories:
            self.categories["Uncategorized"] = {"rules": [], "history": []}

    # --- Category Management ---
    def add_category(self):
        """Adds a new category based on the entry field input."""
        new_cat_name = self.entry_new_category.get().strip()
        if new_cat_name and new_cat_name not in self.categories:
            self.categories[new_cat_name] = {"rules": [], "history": []}
            self.update_category_tabs()
            self.update_category_dropdown()
            self.selected_category_var.set(new_cat_name)
            self.update_rule_display()
            self.entry_new_category.delete(0, tkinter.END)
            self.status_label.configure(text=f"Status: Added category '{new_cat_name}'")
            self.trigger_save_config()
        elif not new_cat_name:
             self.status_label.configure(text="Status: Category name cannot be empty.")
        else:
             self.status_label.configure(text=f"Status: Category '{new_cat_name}' already exists.")

    def delete_selected_category(self):
        """Deletes the category currently selected in the dropdown."""
        cat_to_delete = self.selected_category_var.get()
        if not cat_to_delete or cat_to_delete == "Uncategorized":
            self.status_label.configure(text="Status: Cannot delete this category.")
            return

        confirm = tkinter.messagebox.askyesno("Confirm Delete",
                                             f"Delete category '{cat_to_delete}' and its history?")
        if confirm:
            if cat_to_delete in self.categories:
                del self.categories[cat_to_delete]
            if cat_to_delete in self.ui_elements:
                 del self.ui_elements[cat_to_delete]
            try:
                self.tab_view.delete(cat_to_delete)
            except ValueError:
                 print(f"Warning: Tab '{cat_to_delete}' might have already been removed.")
            except Exception as e:
                 print(f"Error deleting tab '{cat_to_delete}': {e}")

            self.update_category_dropdown()
            self._select_initial_category()
            self.status_label.configure(text=f"Status: Deleted category '{cat_to_delete}'.")
            self.trigger_save_config()

    def update_category_dropdown(self):
        """Refreshes the list of categories in the selection dropdown."""
        category_names = list(self.categories.keys())
        self.category_dropdown.configure(values=category_names)
        current_selection = self.selected_category_var.get()
        if current_selection not in category_names:
             if category_names:
                 self.selected_category_var.set(category_names[0])
             else:
                 self.selected_category_var.set("")

    def update_category_tabs(self):
        """Creates UI tabs for categories that don't have them yet."""
        for cat_name in self.categories:
            if cat_name not in self.ui_elements:
                try:
                    self.tab_view.add(cat_name)
                    tab_content = self.tab_view.tab(cat_name)
                    tab_content.grid_columnconfigure(0, weight=1)
                    tab_content.grid_rowconfigure(0, weight=1)

                    scroll_frame = ctk.CTkScrollableFrame(tab_content, label_text=f"{cat_name} History")
                    scroll_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
                    scroll_frame.grid_columnconfigure(0, weight=1)

                    # Store references to the UI elements for this category
                    self.ui_elements[cat_name] = {"tab": tab_content, "scroll_frame": scroll_frame}
                    self.update_history_display(cat_name)
                except ValueError:
                     print(f"Tab '{cat_name}' might already exist unexpectedly.")
                     # Attempt to re-link existing UI elements if they weren't properly removed
                     try:
                          tab_widget = self.tab_view.tab(cat_name)
                          scroll_frame_widget = tab_widget.winfo_children()[0]
                          if isinstance(scroll_frame_widget, ctk.CTkScrollableFrame):
                              self.ui_elements[cat_name] = {"tab": tab_widget, "scroll_frame": scroll_frame_widget}
                              print(f"Re-linked existing UI for tab: {cat_name}")
                          else: print(f"Could not re-link UI for tab: {cat_name}")
                     except Exception: print(f"Failed to re-link UI for tab: {cat_name}")

                except Exception as e:
                     print(f"Error creating UI for tab '{cat_name}': {e}")


    # --- Rule Management ---
    def add_rule(self):
        """Adds a new rule to the currently selected category."""
        selected_cat = self.selected_category_var.get()
        new_rule = self.entry_new_rule.get().strip()
        if not selected_cat or not new_rule:
            self.status_label.configure(text="Status: Select category and enter rule.")
            return

        if selected_cat in self.categories:
            if "rules" not in self.categories[selected_cat]: self.categories[selected_cat]["rules"] = []
            if new_rule not in self.categories[selected_cat]["rules"]:
                self.categories[selected_cat]["rules"].append(new_rule)
                self.update_rule_display()
                self.entry_new_rule.delete(0, tkinter.END)
                self.status_label.configure(text=f"Status: Added rule to '{selected_cat}'.")
                self.trigger_save_config()
            else:
                self.status_label.configure(text="Status: Rule already exists.")
        else:
             self.status_label.configure(text="Status: Selected category error.")

    def delete_rule(self, category_name, rule_to_delete):
        """Removes a specific rule from a category and updates the display."""
        if category_name in self.categories and \
           "rules" in self.categories[category_name] and \
           rule_to_delete in self.categories[category_name]["rules"]:
            self.categories[category_name]["rules"].remove(rule_to_delete)
            self.update_rule_display()
            self.status_label.configure(text=f"Status: Deleted rule from '{category_name}'.")
            self.trigger_save_config()
        else:
            print(f"Warning: Rule '{rule_to_delete}' not found in '{category_name}'.")
            self.status_label.configure(text="Status: Rule not found error.")

    def update_rule_display(self, selected_category_name=None):
        """Clears and repopulates the rule display frame for the selected category."""
        if selected_category_name is None:
            selected_category_name = self.selected_category_var.get()

        # Clear current rule display widgets
        for widget in self.rule_display_frame.winfo_children(): widget.destroy()

        if selected_category_name and selected_category_name in self.categories:
            rules = self.categories[selected_category_name].get("rules", [])
            if not rules:
                 ctk.CTkLabel(self.rule_display_frame, text="(No rules defined)", text_color="gray").grid(row=0, column=0, padx=5, pady=5)
            else:
                for index, rule_text in enumerate(rules):
                    rule_frame = ctk.CTkFrame(self.rule_display_frame, fg_color="transparent")
                    rule_frame.grid(row=index, column=0, padx=5, pady=2, sticky="ew")
                    rule_frame.grid_columnconfigure(0, weight=1)
                    ctk.CTkLabel(rule_frame, text=rule_text, anchor="w").grid(row=0, column=0, sticky="ew", padx=(0, 5))
                    ctk.CTkButton(rule_frame, text="X", width=25, fg_color="red", hover_color="darkred",
                                  command=lambda cat=selected_category_name, rule=rule_text: self.delete_rule(cat, rule)).grid(row=0, column=1, sticky="e")
        else:
             ctk.CTkLabel(self.rule_display_frame, text="(Select a category)", text_color="gray").grid(row=0, column=0, padx=5, pady=5)

    # --- Clipboard Processing ---
    def _schedule_process_clipboard(self, content):
        """Schedules the processing of new clipboard content in the main Tkinter thread."""
        self.after(50, self.process_clipboard_content, content)

    def process_clipboard_content(self, content):
        """Categorizes and adds new clipboard content to history (runs in main thread)."""
        assigned_category = ClipboardHandler.categorize_content(content, self.categories)

        if assigned_category:
            self.add_to_history(assigned_category, content)
            self.update_history_display(assigned_category)
            self.status_label.configure(text=f"Status: Added item to '{assigned_category}'")
        else:
            print(f"Warning: Could not categorize content: {content[:50]}...")


    # --- History Management ---
    def add_to_history(self, category_name, item):
        """Adds an item to a category's history, handling duplicates and limits."""
        if category_name in self.categories:
            if not isinstance(self.categories[category_name].get("history"), list):
                 self.categories[category_name]["history"] = []
            history = self.categories[category_name]["history"]
            # Prevent adding the same item consecutively
            if history and history[0] == item: return
            # Remove item if it already exists elsewhere in history to move it to the top
            if item in history: history.remove(item)
            # Add new item to the beginning
            history.insert(0, item)
            # Trim history if it exceeds the limit
            if len(history) > HISTORY_LIMIT_PER_CATEGORY:
                self.categories[category_name]["history"] = history[:HISTORY_LIMIT_PER_CATEGORY]
            # Note: UI update is triggered separately

        else:
            print(f"Warning: Attempted to add history to non-existent category: {category_name}")


    def update_history_display(self, category_name):
        """Clears and repopulates the history display frame for a specific category."""
        if category_name not in self.ui_elements or \
           "scroll_frame" not in self.ui_elements[category_name]:
            print(f"Cannot update history display for '{category_name}', UI elements not ready.")
            return

        scroll_frame = self.ui_elements[category_name]["scroll_frame"]
        history = self.categories[category_name].get("history", [])

        # Clear current history widgets
        for widget in scroll_frame.winfo_children(): widget.destroy()

        if not history:
             ctk.CTkLabel(scroll_frame, text="(History is empty)", text_color="gray").grid(row=0, column=0, padx=5, pady=5)
        else:
            for index, item_text in enumerate(history):
                # Ensure item is string and truncate for display
                if not isinstance(item_text, str): item_text = str(item_text)
                display_text = item_text.replace('\n', ' ').strip()
                max_len = 80
                if len(display_text) > max_len: display_text = display_text[:max_len-3] + "..."

                # Create frame for each history item with label, copy, and delete buttons
                item_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
                item_frame.grid(row=index, column=0, padx=5, pady=(2,3), sticky="ew")
                item_frame.grid_columnconfigure(0, weight=1)
                item_frame.grid_columnconfigure(1, weight=0)
                item_frame.grid_columnconfigure(2, weight=0)

                ctk.CTkLabel(item_frame, text=display_text, anchor="w").grid(row=0, column=0, sticky="ew", padx=(0, 5))
                ctk.CTkButton(item_frame, text="Copy", width=60,
                              command=lambda text=item_text: self.copy_item_to_clipboard(text)).grid(row=0, column=1, sticky="e", padx=(0, 5))
                ctk.CTkButton(item_frame, text="X", width=25, fg_color="red", hover_color="darkred",
                              command=lambda cat=category_name, item=item_text: self.delete_history_item(cat, item)).grid(row=0, column=2, sticky="e")

    def delete_history_item(self, category_name, item_to_delete):
        """Removes a specific item from a category's history and updates the UI."""
        if category_name in self.categories and \
           isinstance(self.categories[category_name].get("history"), list) and \
           item_to_delete in self.categories[category_name]["history"]:
            self.categories[category_name]["history"].remove(item_to_delete)
            self.update_history_display(category_name)
            self.status_label.configure(text=f"Status: Deleted item from '{category_name}'.")
            self.trigger_save_config()
        else:
            print(f"Warning: Item not found in history for '{category_name}'.")
            self.status_label.configure(text="Status: Item not found error.")

    def update_all_history_displays(self):
        """Refreshes the history display for all categories."""
        for cat_name in self.categories:
             if cat_name in self.ui_elements:
                 self.update_history_display(cat_name)

    def copy_item_to_clipboard(self, text):
        """Copies the given text to the system clipboard."""
        try:
            clipboard.copy(text)
            self.status_label.configure(text="Status: Item copied to clipboard!")
        except Exception as e:
            print(f"Error copying to clipboard: {e}")
            self.status_label.configure(text="Status: Error copying item.")

    # --- Configuration Persistence ---
    def trigger_save_config(self):
        """Saves the current application configuration to a file."""
        if config_manager.save_config(self.categories):
            # Status updated elsewhere for specific actions (add/delete)
            pass
        else:
            self.status_label.configure(text="Status: Error saving configuration!")
            tkinter.messagebox.showerror("Save Error", "Could not save configuration.")

# Note: The main application loop (if __name__ == "__main__": app = ClipboardManagerApp(); app.mainloop())
# should be in your main execution file, not necessarily here if this is just a module.
# If this file is the entry point, add the following block at the end:
# if __name__ == "__main__":
#     app = ClipboardManagerApp()
#     app._ensure_uncategorized_exists() # Ensure default category exists on startup
#     app.mainloop()

