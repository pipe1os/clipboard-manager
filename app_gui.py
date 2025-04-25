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
HIGHLIGHT_BORDER_WIDTH = 2
HIGHLIGHT_BORDER_COLOR = "yellow"

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
        # Dictionary to hold search queries for each category
        self.search_queries = {}
        # Drag and drop state
        self.drag_data = None
        self.drag_window = None
        self.previously_highlighted_category = None # Track highlighted tab
        self.selected_items = {} # Track selected items {category: set(items)}

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
    * Regex Rule: Start the rule with `regex:` followed by a Python regular expression (e.g., `regex:^\\d{3}-\\d{2}-\\d{4}$` for SSN format, or `regex:https?://` for links). This allows for more complex pattern matching.
    * Click the 'X' next to a rule in the 'Current Rules' list to delete it.

3.  Clipboard History (Right Panel):
    * When you copy text, it's checked against the rules and added to the top of the history list in the matching category's tab on the right.
    * Use the checkboxes to select one or more items in the history list.
    * Use the action buttons below the list ('Copy Sel.', 'Delete Sel.', 'Pin Sel.', 'Unpin Sel.') to act on the selected items.
    * Alternatively, use the individual 'Pin'/'Unpin', 'Copy', or 'X' buttons on each row for single-item actions.

4.  Saving:
    * Click 'Save Config' (Left Panel) to manually save your categories and rules.
    * Configuration (categories, rules, history) is also saved automatically when you close the application using the window's 'X' button or the tray icon's Exit option.

5.  System Tray:
    * Closing the main window with the 'X' button will hide it. The app keeps running in the background.
    * Find the app icon in the system tray (usually in the hidden icons area).
    * Right-click the tray icon for options:
        * Show: Reopens the main window.
        * Exit: Properly closes the application and saves data.

6.  Pinning Items:
    * Pinned items (marked with 📌) always appear at the top of their category's history list.
    * Use the 'Pin Sel.' button to pin selected items.
    * Use the 'Unpin Sel.' button to unpin selected items.
    * Copying an item again (pinned or not) will move it to the top of the *regular* history list.

7.  Moving Items:
    * Click and drag an item to move it to another category, but only if *no items are selected* in the source category via checkbox.
    * Drop the item onto the tab or history area of the destination category.

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
            self.categories[new_cat_name] = {"rules": [], "history": [], "pinned_history": []}
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
            # Also remove the search query for the deleted category
            if cat_to_delete in self.search_queries:
                del self.search_queries[cat_to_delete]
            # Also remove selection data for the deleted category
            if cat_to_delete in self.selected_items:
                del self.selected_items[cat_to_delete]
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
                    # Configure rows: 0 for search, 1 for history frame, 2 for action buttons
                    tab_content.grid_rowconfigure(0, weight=0) # Search entry row
                    tab_content.grid_rowconfigure(1, weight=1) # History frame row
                    tab_content.grid_rowconfigure(2, weight=0) # Action buttons row

                    # Search Entry
                    search_entry = ctk.CTkEntry(tab_content, placeholder_text=f"Search in {cat_name} history...")
                    search_entry.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="ew")
                    # Trigger search on key release
                    search_entry.bind("<KeyRelease>", lambda event, c=cat_name: self._filter_history_callback(c))

                    # History Scroll Frame
                    scroll_frame = ctk.CTkScrollableFrame(tab_content, label_text=f"{cat_name} History")
                    scroll_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew") # Changed row to 1
                    scroll_frame.grid_columnconfigure(0, weight=1)

                    # Action Buttons Frame
                    action_button_frame = ctk.CTkFrame(tab_content, fg_color="transparent")
                    action_button_frame.grid(row=2, column=0, padx=5, pady=(0, 5), sticky="ew")
                    # Configure columns to space out buttons
                    action_button_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

                    # Action Buttons (Initially disabled)
                    copy_selected_btn = ctk.CTkButton(action_button_frame, text="Copy Sel.", state="disabled", command=lambda c=cat_name: self._copy_selected(c))
                    copy_selected_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

                    delete_selected_btn = ctk.CTkButton(action_button_frame, text="Delete Sel.", state="disabled", fg_color="red", hover_color="darkred", command=lambda c=cat_name: self._delete_selected(c))
                    delete_selected_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

                    pin_selected_btn = ctk.CTkButton(action_button_frame, text="Pin Sel.", state="disabled", command=lambda c=cat_name: self._pin_selected(c))
                    pin_selected_btn.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

                    unpin_selected_btn = ctk.CTkButton(action_button_frame, text="Unpin Sel.", state="disabled", command=lambda c=cat_name: self._unpin_selected(c))
                    unpin_selected_btn.grid(row=0, column=3, padx=2, pady=2, sticky="ew")

                    # Store references to the UI elements for this category
                    self.ui_elements[cat_name] = {
                        "tab": tab_content,
                        "scroll_frame": scroll_frame,
                        "search_entry": search_entry,
                        "tab_button": None, # Placeholder for the actual tab button
                        # Action buttons
                        "copy_selected_button": copy_selected_btn,
                        "delete_selected_button": delete_selected_btn,
                        "pin_selected_button": pin_selected_btn,
                        "unpin_selected_button": unpin_selected_btn
                    }
                    # Attempt to find and store the corresponding tab button widget
                    # NOTE: This relies on internal CTkTabview structure (_segmented_button)
                    # and might need adjustment if CTk changes.
                    try:
                        # Segmented button should exist after adding the tab
                        segmented_button = self.tab_view._segmented_button
                        # Find the button by its text (which is the category name)
                        for button in segmented_button.winfo_children():
                            if isinstance(button, ctk.CTkButton) and button.cget("text") == cat_name:
                                self.ui_elements[cat_name]["tab_button"] = button
                                print(f"Stored tab button for {cat_name}: {button}") # Debug
                                break
                    except Exception as e_btn:
                        print(f"Warning: Could not find/store tab button for {cat_name}: {e_btn}")

                    self.update_history_display(cat_name) # Initial population
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

    # --- Filtering and Clipboard Processing ---
    def _filter_history_callback(self, category_name):
        """Called when the search entry text changes for a category."""
        if category_name in self.ui_elements:
            search_entry = self.ui_elements[category_name].get("search_entry")
            if search_entry:
                self.search_queries[category_name] = search_entry.get().strip()
                self.update_history_display(category_name) # Refresh display with filter

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
            cat_data = self.categories[category_name]
            if not isinstance(cat_data.get("history"), list):
                 cat_data["history"] = []
            if not isinstance(cat_data.get("pinned_history"), list):
                 cat_data["pinned_history"] = []

            history = cat_data["history"]
            pinned_history = cat_data["pinned_history"]

            # If item exists anywhere (pinned or not), remove it first
            if item in history: history.remove(item)
            if item in pinned_history: pinned_history.remove(item)

            # Prevent adding the same item consecutively TO THE TOP if it was already there
            # Note: This check is less critical now items are always removed first,
            # but kept for safety. Checking history[0] is sufficient as items
            # copied again are unpinned and added to normal history.
            # if history and history[0] == item: return # Less relevant now

            # Add new item to the beginning of the normal history
            history.insert(0, item)

            # Trim *normal* history if it exceeds the limit
            if len(history) > HISTORY_LIMIT_PER_CATEGORY:
                self.categories[category_name]["history"] = history[:HISTORY_LIMIT_PER_CATEGORY]
            # Note: UI update is triggered separately

        else:
            print(f"Warning: Attempted to add history to non-existent category: {category_name}")


    def update_history_display(self, category_name):
        """Clears and repopulates the history display frame for a specific category, applying search filter."""
        if category_name not in self.ui_elements or \
           "scroll_frame" not in self.ui_elements[category_name]:
            print(f"Cannot update history display for '{category_name}', UI elements not ready.")
            return

        scroll_frame = self.ui_elements[category_name]["scroll_frame"]
        cat_data = self.categories[category_name]
        full_history = cat_data.get("history", [])
        pinned_history = cat_data.get("pinned_history", [])
        search_query = self.search_queries.get(category_name, "").lower()

        # Filter history based on search query
        filtered_pinned = []
        filtered_history = []
        if search_query:
            filtered_pinned = [item for item in pinned_history if search_query in str(item).lower()]
            filtered_history = [item for item in full_history if search_query in str(item).lower()]
        else:
            filtered_pinned = pinned_history[:]
            filtered_history = full_history[:]

        # Clear current history widgets
        for widget in scroll_frame.winfo_children(): widget.destroy()

        if not filtered_pinned and not filtered_history:
             if search_query:
                 # Show different message if history is empty due to filtering
                 ctk.CTkLabel(scroll_frame, text=f"(No results for '{search_query}')", text_color="gray").grid(row=0, column=0, padx=5, pady=5)
             else:
             ctk.CTkLabel(scroll_frame, text="(History is empty)", text_color="gray").grid(row=0, column=0, padx=5, pady=5)
        else:
            # Display filtered history
            current_row_index = 0

            # Display Pinned Items First
            for item_text in filtered_pinned:
                self._create_history_item_widget(scroll_frame, category_name, item_text, current_row_index, is_pinned=True)
                current_row_index += 1

            # Display Regular History Items
            for item_text in filtered_history:
                self._create_history_item_widget(scroll_frame, category_name, item_text, current_row_index, is_pinned=False)
                current_row_index += 1

    def _create_history_item_widget(self, parent_frame, category_name, item_text, row_index, is_pinned):
        """Creates the widget frame for a single history item with a checkbox and individual buttons."""
                # Ensure item is string and truncate for display
                if not isinstance(item_text, str): item_text = str(item_text)
                display_text = item_text.replace('\n', ' ').strip()
        # Adjust max_len based on available space with checkbox and 3 buttons
        max_len = 55 
                if len(display_text) > max_len: display_text = display_text[:max_len-3] + "..."

        # Add pin indicator if pinned
        if is_pinned:
            display_text = f"📌 {display_text}"

        # Check selection state
        is_selected = item_text in self.selected_items.get(category_name, set())
        frame_fg_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"][0] if is_selected else "transparent"

        # Create frame for each history item with checkbox and label
        item_frame = ctk.CTkFrame(parent_frame, fg_color=frame_fg_color, corner_radius=3)
        item_frame.grid(row=row_index, column=0, padx=5, pady=(1,2), sticky="ew") # Reduced pady
        # Configure columns: Checkbox, Label (stretches), Pin, Copy, Delete
        item_frame.grid_columnconfigure(0, weight=0) # Checkbox column
        item_frame.grid_columnconfigure(1, weight=1) # Label column
        item_frame.grid_columnconfigure(2, weight=0) # Pin/Unpin Button
        item_frame.grid_columnconfigure(3, weight=0) # Copy Button
        item_frame.grid_columnconfigure(4, weight=0) # Delete Button

        # Checkbox for selection
        checkbox_var = ctk.StringVar(value="on" if is_selected else "off")
        checkbox = ctk.CTkCheckBox(item_frame, text="", variable=checkbox_var, onvalue="on", offvalue="off",
                                   width=0,
                                   command=lambda cat=category_name, item=item_text: self._toggle_item_selection(cat, item))
        checkbox.grid(row=0, column=0, sticky="w", padx=(5, 5))

        # Label (decreased padx slightly)
        label_widget = ctk.CTkLabel(item_frame, text=display_text, anchor="w")
        label_widget.grid(row=0, column=1, sticky="ew", padx=(0, 5))

        # --- RE-ADD Individual Buttons --- 
        button_width = 45 # Define common width

        # Pin/Unpin Button
        pin_button_text = "Unpin" if is_pinned else "Pin"
        pin_button_command = lambda c=category_name, i=item_text: self.unpin_item(c, i) if is_pinned else self.pin_item(c, i)
        pin_button = ctk.CTkButton(item_frame, text=pin_button_text, width=button_width,
                      command=pin_button_command)
        pin_button.grid(row=0, column=2, sticky="e", padx=(0, 5))

        # Copy Button
        copy_button = ctk.CTkButton(item_frame, text="Copy", width=button_width, 
                      command=lambda text=item_text: self.copy_item_to_clipboard(text))
        copy_button.grid(row=0, column=3, sticky="e", padx=(0, 5))

        # Delete Button
        delete_button = ctk.CTkButton(item_frame, text="X", width=25, # Keep delete narrow
                      fg_color="red", hover_color="darkred",
                      command=lambda cat=category_name, item=item_text: self.delete_history_item(cat, item))
        delete_button.grid(row=0, column=4, sticky="e")

        # --- RE-ADD Drag and Drop Bindings --- 
        # We bind to the item_frame and the label inside it, as events might trigger on either
        item_frame.bind("<ButtonPress-1>", lambda event, cat=category_name, item=item_text, frame=item_frame: self._on_drag_start(event, cat, item, frame))
        item_frame.bind("<B1-Motion>", self._on_drag_motion)
        item_frame.bind("<ButtonRelease-1>", self._on_drag_drop)
        label_widget.bind("<ButtonPress-1>", lambda event, cat=category_name, item=item_text, frame=item_frame: self._on_drag_start(event, cat, item, frame))
        label_widget.bind("<B1-Motion>", self._on_drag_motion)
        label_widget.bind("<ButtonRelease-1>", self._on_drag_drop)

    def pin_item(self, category_name, item_to_pin):
        """Moves an item from history to pinned_history."""
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            history = cat_data.get("history", [])
            pinned_history = cat_data.get("pinned_history", [])

            if item_to_pin in history:
                history.remove(item_to_pin)
                if item_to_pin not in pinned_history:
                    pinned_history.insert(0, item_to_pin) # Add to top of pinned
                self.update_history_display(category_name)
                self.status_label.configure(text=f"Status: Pinned item in '{category_name}'.")
                self.trigger_save_config()
            elif item_to_pin in pinned_history:
                # Already pinned, maybe move to top? For now, do nothing.
                self.status_label.configure(text="Status: Item already pinned.")
            else:
                print(f"Warning: Item to pin not found in history for '{category_name}'.")
                self.status_label.configure(text="Status: Item not found to pin.")

    def unpin_item(self, category_name, item_to_unpin):
        """Moves an item from pinned_history back to the top of history."""
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            history = cat_data.get("history", [])
            pinned_history = cat_data.get("pinned_history", [])

            if item_to_unpin in pinned_history:
                pinned_history.remove(item_to_unpin)
                if item_to_unpin in history:
                    history.remove(item_to_unpin)
                history.insert(0, item_to_unpin) # Add to top of normal history
                self.update_history_display(category_name)
                self.status_label.configure(text=f"Status: Unpinned item in '{category_name}'.")
                self.trigger_save_config()
            else:
                print(f"Warning: Item to unpin not found in pinned history for '{category_name}'.")
                self.status_label.configure(text="Status: Item not found to unpin.")

    def delete_history_item(self, category_name, item_to_delete):
        """Removes a specific item from a category's history (both normal and pinned) and updates the UI."""
        item_deleted = False
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            history = cat_data.get("history", [])
            pinned_history = cat_data.get("pinned_history", [])

            # Try removing from pinned history
            if item_to_delete in pinned_history:
                pinned_history.remove(item_to_delete)
                item_deleted = True

            # Try removing from normal history
            if item_to_delete in history:
                history.remove(item_to_delete)
                item_deleted = True

            # Remove from selection if it was selected
            if item_to_delete in self.selected_items.get(category_name, set()):
                self.selected_items[category_name].remove(item_to_delete)

            if item_deleted:
            self.update_history_display(category_name)
                # Update button states AFTER display update (which clears selection visually)
                self._update_action_buttons_state(category_name)
            self.status_label.configure(text=f"Status: Deleted item from '{category_name}'.")
            self.trigger_save_config()
        else:
                print(f"Warning: Item to delete not found in history or pinned history for '{category_name}'.")
            self.status_label.configure(text="Status: Item not found error.")
        else:
            print(f"Warning: Category '{category_name}' not found for deletion.")
            self.status_label.configure(text="Status: Category not found error.")

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

    # --- Item Moving Logic ---
    def _move_item(self, source_category, destination_category, item_to_move):
        """Moves an item from the source category to the destination category."""
        item_removed_from_source = False
        # Remove from source category (check both pinned and normal history)
        if source_category in self.categories:
            source_cat_data = self.categories[source_category]
            if item_to_move in source_cat_data.get("pinned_history", []):
                source_cat_data["pinned_history"].remove(item_to_move)
                item_removed_from_source = True
            if item_to_move in source_cat_data.get("history", []):
                source_cat_data["history"].remove(item_to_move)
                item_removed_from_source = True

        if not item_removed_from_source:
            print(f"Warning: Item '{item_to_move[:20]}...' not found in source category '{source_category}' during move.")
            # Continue anyway, maybe it was already removed somehow

        # Add to destination category (always to the top of normal history)
        if destination_category in self.categories:
            dest_cat_data = self.categories[destination_category]
            # Ensure lists exist
            if not isinstance(dest_cat_data.get("history"), list): dest_cat_data["history"] = []
            if not isinstance(dest_cat_data.get("pinned_history"), list): dest_cat_data["pinned_history"] = []

            # Remove from destination if it exists (to avoid duplicates and ensure move to top)
            if item_to_move in dest_cat_data.get("pinned_history", []):
                dest_cat_data["pinned_history"].remove(item_to_move)
            if item_to_move in dest_cat_data.get("history", []):
                dest_cat_data["history"].remove(item_to_move)

            # Add to the beginning of the normal history in the destination
            dest_cat_data["history"].insert(0, item_to_move)

            # Update UI for both categories
            self.update_history_display(source_category)
            self.update_history_display(destination_category)

            self.status_label.configure(text=f"Status: Moved item to '{destination_category}'.")
            self.trigger_save_config()
        else:
            print(f"Error: Destination category '{destination_category}' not found during move.")
            self.status_label.configure(text="Status: Error moving item (destination not found).")
            # Re-update source display in case item was removed but couldn't be added
            if item_removed_from_source:
                self.update_history_display(source_category)

    # --- Multi-Select Actions ---
    def _toggle_item_selection(self, category_name, item_text):
        """Adds or removes an item from the selection set for a category."""
        if category_name not in self.selected_items:
            self.selected_items[category_name] = set()

        selected_set = self.selected_items[category_name]
        if item_text in selected_set:
            selected_set.remove(item_text)
        else:
            selected_set.add(item_text)

        # Update the visual state (background color)
        self.update_history_display(category_name)
        # Update the state of action buttons
        self._update_action_buttons_state(category_name)

    def _update_action_buttons_state(self, category_name):
        """Enables or disables action buttons based on selection."""
        selected_count = len(self.selected_items.get(category_name, set()))
        new_state = "normal" if selected_count > 0 else "disabled"

        ui_elements = self.ui_elements.get(category_name)
        if ui_elements:
            for button_key in ["copy_selected_button", "delete_selected_button", 
                               "pin_selected_button", "unpin_selected_button"]:
                button = ui_elements.get(button_key)
                if button and button.winfo_exists(): # Check if button exists
                    try:
                        button.configure(state=new_state)
                    except Exception as e:
                         print(f"Error configuring button {button_key} state: {e}")

    def _copy_selected(self, category_name):
        """Copies selected items (concatenated) to the clipboard in visual order."""
        selected_items_set = self.selected_items.get(category_name, set())
        if not selected_items_set:
            self.status_label.configure(text="Status: No items selected to copy.")
            return

        ordered_items_to_copy = []
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            pinned_history = cat_data.get("pinned_history", [])
            history = cat_data.get("history", [])

            # Iterate through pinned items first
            for item in pinned_history:
                if item in selected_items_set:
                    ordered_items_to_copy.append(str(item)) # Ensure string
            
            # Iterate through normal history items
            for item in history:
                if item in selected_items_set:
                    ordered_items_to_copy.append(str(item)) # Ensure string

        if not ordered_items_to_copy:
            # This might happen if selected items were somehow removed before copy action
            print("Warning: No items found to copy despite selection set not being empty.")
            self.status_label.configure(text="Status: Error finding selected items to copy.")
            # Clear selection just in case
            self.selected_items[category_name] = set()
            self._update_action_buttons_state(category_name)
            return

        # Concatenate items with double newline for clarity
        concatenated_text = "\n\n".join(ordered_items_to_copy)

        try:
            clipboard.copy(concatenated_text)
            self.status_label.configure(text=f"Status: Copied {len(ordered_items_to_copy)} selected items.")
            
            # Deselect items after successful copy
            self.selected_items[category_name] = set()
            self.update_history_display(category_name)
            self._update_action_buttons_state(category_name)
            # No need to save config for copy, unless deselecting is considered a state change worth saving
            # self.trigger_save_config() 

        except Exception as e:
            print(f"Error copying selected items to clipboard: {e}")
            self.status_label.configure(text="Status: Error copying selected items.")
            # Do not deselect if copy failed

    def _delete_selected(self, category_name):
        """Deletes all selected items in the category."""
        selected_items_to_delete = self.selected_items.get(category_name, set()).copy() # Copy set for safe iteration
        if not selected_items_to_delete:
            # This case should ideally not be reached if button state is managed correctly
            self.status_label.configure(text="Status: No items selected to delete.")
            return

        items_deleted_count = 0
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            history = cat_data.setdefault("history", [])
            pinned_history = cat_data.setdefault("pinned_history", [])

            for item in selected_items_to_delete:
                item_was_found = False
                if item in history:
                    history.remove(item)
                    item_was_found = True
                if item in pinned_history:
                    pinned_history.remove(item)
                    item_was_found = True
                
                if item_was_found:
                    items_deleted_count += 1
                else:
                     print(f"Warning: Selected item '{item[:20]}...' not found during mass delete.")

            # Clear selection for this category AFTER iteration
            self.selected_items[category_name] = set()

            # Update UI only once after all deletions
            self.update_history_display(category_name)
            self._update_action_buttons_state(category_name)

            # Save config
            self.trigger_save_config()

            self.status_label.configure(text=f"Status: Deleted {items_deleted_count} selected items from '{category_name}'.")

        else:
            print(f"Error: Category '{category_name}' not found during delete selected.")
            self.status_label.configure(text="Status: Error deleting items (category not found).")
            # Still clear selection if category doesn't exist somehow
            if category_name in self.selected_items: self.selected_items[category_name] = set()
            self._update_action_buttons_state(category_name)

    def _pin_selected(self, category_name):
        """Pins all selected items in the category."""
        selected_items_to_pin = self.selected_items.get(category_name, set()).copy()
        if not selected_items_to_pin:
            self.status_label.configure(text="Status: No items selected to pin.")
            return

        items_pinned_count = 0
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            history = cat_data.setdefault("history", [])
            pinned_history = cat_data.setdefault("pinned_history", [])

            for item in selected_items_to_pin:
                item_was_moved_or_confirmed_pinned = False
                # Check if it's in normal history
                if item in history:
                    history.remove(item)
                    # Add to pinned only if not already there
                    if item not in pinned_history:
                        pinned_history.insert(0, item) # Add to top of pinned
                    item_was_moved_or_confirmed_pinned = True
                elif item in pinned_history:
                    # It was already pinned, maybe move to top?
                    # For simplicity, we just confirm it's pinned.
                    # Optional: Move to top if desired: 
                    # pinned_history.remove(item)
                    # pinned_history.insert(0, item)
                    item_was_moved_or_confirmed_pinned = True # Count it as processed
                else:
                     print(f"Warning: Selected item '{item[:20]}...' not found during mass pin.")
                
                if item_was_moved_or_confirmed_pinned:
                     items_pinned_count += 1

            # Clear selection after processing all items
            self.selected_items[category_name] = set()

            # Update UI
            self.update_history_display(category_name)
            self._update_action_buttons_state(category_name)

            # Save config
            self.trigger_save_config()

            self.status_label.configure(text=f"Status: Pinned {items_pinned_count} selected items in '{category_name}'.")

        else:
            print(f"Error: Category '{category_name}' not found during pin selected.")
            self.status_label.configure(text="Status: Error pinning items (category not found).")
            if category_name in self.selected_items: self.selected_items[category_name] = set()
            self._update_action_buttons_state(category_name)

    def _unpin_selected(self, category_name):
        """Unpins all selected items in the category."""
        selected_items_to_unpin = self.selected_items.get(category_name, set()).copy()
        if not selected_items_to_unpin:
            self.status_label.configure(text="Status: No items selected to unpin.")
            return

        items_unpinned_count = 0
        if category_name in self.categories:
            cat_data = self.categories[category_name]
            history = cat_data.setdefault("history", [])
            pinned_history = cat_data.setdefault("pinned_history", [])

            for item in selected_items_to_unpin:
                item_was_moved = False
                # Check if it's in pinned history
                if item in pinned_history:
                    pinned_history.remove(item)
                    # Remove from normal history if it exists there (to move to top)
                    if item in history:
                        history.remove(item)
                    # Add to the top of normal history
                    history.insert(0, item)
                    item_was_moved = True
                elif item in history:
                    # Item was selected but wasn't pinned, maybe move to top?
                    # For consistency with pin action, we do nothing here. 
                    # User might have selected both pinned and unpinned.
                    # We only act on the ones that *were* pinned.
                    pass # Or we could count it as processed if needed
                else:
                     print(f"Warning: Selected item '{item[:20]}...' not found during mass unpin.")
                
                if item_was_moved:
                    items_unpinned_count += 1

            # Clear selection after processing all items
            self.selected_items[category_name] = set()

            # Update UI
            self.update_history_display(category_name)
            self._update_action_buttons_state(category_name)

            # Save config
            self.trigger_save_config()

            self.status_label.configure(text=f"Status: Unpinned {items_unpinned_count} selected items in '{category_name}'.")

        else:
            print(f"Error: Category '{category_name}' not found during unpin selected.")
            self.status_label.configure(text="Status: Error unpinning items (category not found).")
            if category_name in self.selected_items: self.selected_items[category_name] = set()
            self._update_action_buttons_state(category_name)

    # --- Drag and Drop Handlers ---
    def _on_drag_start(self, event, category_name, item_text, frame_widget):
        """Initiates the drag operation, only if nothing is selected in this category."""
        # --- Check if items are selected --- 
        if self.selected_items.get(category_name, set()):
            print("Drag prevented: Items are selected in this category.")
            return # Do not start drag if items are selected
        # --- End Check ---

        print(f"Drag Start: {category_name} - {item_text[:20]}...") # Debug
        # Store drag data (Corrected: Store dict)
        self.drag_data = {
            "source_category": category_name,
            "item_text": item_text,
            "widget": frame_widget # Store the widget being dragged
        }

        # Create drag window (visual feedback) (Corrected: Restore Toplevel window)
        if self.drag_window:
            self.drag_window.destroy()
        self.drag_window = ctk.CTkToplevel(self)
        self.drag_window.overrideredirect(True) # No window decorations
        self.drag_window.geometry(f"+{(event.x_root + 10)}+{(event.y_root + 10)}")
        self.drag_window.attributes("-alpha", 0.7) # Semi-transparent
        self.drag_window.attributes("-topmost", True)

        # Add a label with item preview to the drag window
        preview_text = item_text.replace('\n', ' ').strip()
        max_preview = 40
        if len(preview_text) > max_preview: preview_text = preview_text[:max_preview-3] + "..."
        label = ctk.CTkLabel(self.drag_window, text=preview_text, fg_color="gray20", corner_radius=5)
        label.pack(padx=5, pady=5)

    def _on_drag_motion(self, event):
        """Handles the dragging motion and highlights potential drop targets."""
        # (Restored full logic)
        if not self.drag_data or not self.drag_window:
            return
        # Update drag window position
        self.drag_window.geometry(f"+{(event.x_root + 10)}+{(event.y_root + 10)}")

        # --- Find Hover Target --- 
        hovered_category = None
        widget_under_cursor = self.winfo_containing(event.x_root, event.y_root)
        source_category = self.drag_data.get("source_category")

        if widget_under_cursor:
            current_widget = widget_under_cursor
            while current_widget is not None and current_widget != self:
                # Check UI elements (tab content or scroll frame)
                for cat_name, elements in self.ui_elements.items():
                    if current_widget == elements.get("tab") or current_widget == elements.get("scroll_frame"):
                        if cat_name != source_category: # Can't drop onto source
                            hovered_category = cat_name
                        break # Found potential category via content/scroll area
                if hovered_category: break # Exit while loop if found via content/scroll

                # Check Tab Buttons if not found via content area yet
                potential_button = None
                if isinstance(current_widget, ctk.CTkButton): potential_button = current_widget
                elif isinstance(current_widget.master, ctk.CTkButton): potential_button = current_widget.master

                if potential_button and \
                   hasattr(potential_button, "master") and isinstance(potential_button.master, ctk.CTkSegmentedButton) and \
                   hasattr(potential_button.master, "master") and potential_button.master.master == self.tab_view:
                     button_text = potential_button.cget("text")
                     if button_text in self.categories and button_text != source_category:
                         hovered_category = button_text # Found potential category via tab button
                         break # Exit while loop

                current_widget = current_widget.master

        # --- Apply/Remove Highlight --- 
        if hovered_category != self.previously_highlighted_category:
            # Remove highlight from previous target
            if self.previously_highlighted_category:
                prev_button = self.ui_elements.get(self.previously_highlighted_category, {}).get("tab_button")
                if prev_button and prev_button.winfo_exists(): # Check if exists
                    try:
                        prev_button.configure(border_width=0) # Reset border
                    except Exception as e_unhighlight:
                         print(f"Error removing highlight: {e_unhighlight}")

            # Add highlight to new target
            if hovered_category:
                new_button = self.ui_elements.get(hovered_category, {}).get("tab_button")
                if new_button and new_button.winfo_exists(): # Check if exists
                     try:
                        new_button.configure(border_width=HIGHLIGHT_BORDER_WIDTH, border_color=HIGHLIGHT_BORDER_COLOR)
                     except Exception as e_highlight:
                         print(f"Error applying highlight: {e_highlight}")

            self.previously_highlighted_category = hovered_category

    def _on_drag_drop(self, event):
        """Handles the drop action."""
        # (Restored full logic)
        # --- Clear Highlight --- 
        if self.previously_highlighted_category:
            prev_button = self.ui_elements.get(self.previously_highlighted_category, {}).get("tab_button")
            if prev_button and prev_button.winfo_exists():
                 try:
                    prev_button.configure(border_width=0) # Reset border
                 except Exception as e_unhighlight:
                    print(f"Error removing highlight on drop: {e_unhighlight}")
            self.previously_highlighted_category = None
        # --- End Clear Highlight ---

        if not self.drag_data:
             return

        print(f"Drop at: {event.x_root}, {event.y_root}") # Debug

        # Destroy drag window
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None

        # --- Find Drop Target --- 
        target_category = None
        # Get widget under the cursor
        widget_under_cursor = self.winfo_containing(event.x_root, event.y_root)

        if widget_under_cursor:
            print(f"Widget under cursor: {widget_under_cursor.winfo_class()} {widget_under_cursor}") # Debug
            # Traverse up the widget hierarchy to find a recognizable container (tab or scroll_frame)
            current_widget = widget_under_cursor
            while current_widget is not None and current_widget != self:
                # Check if it's one of our stored UI elements
                for cat_name, elements in self.ui_elements.items():
                    # Check if dropped onto the tab content area or the scroll frame within it
                    if current_widget == elements.get("tab") or current_widget == elements.get("scroll_frame"): 
                        target_category = cat_name
                        print(f"Potential target found: {target_category}") # Debug
                        break # Found target category
                if target_category: break # Exit outer loop too
                
                # Check if dropped directly on a tab button or its contents
                potential_button = None
                if isinstance(current_widget, ctk.CTkButton):
                    potential_button = current_widget
                elif isinstance(current_widget.master, ctk.CTkButton):
                     potential_button = current_widget.master

                # Verify the button hierarchy: Button -> SegmentedButton -> Tabview
                if potential_button and \
                   hasattr(potential_button, "master") and isinstance(potential_button.master, ctk.CTkSegmentedButton) and \
                   hasattr(potential_button.master, "master") and potential_button.master.master == self.tab_view:
                     button_text = potential_button.cget("text")
                     if button_text in self.categories:
                         target_category = button_text
                         print(f"Potential target (tab button identified) found: {target_category}") # Debug
                         break # Exit while loop, target found

                current_widget = current_widget.master # Go up one level
        
        print(f"Final Target Category: {target_category}") # Debug

        # Process the move if a valid target was found
        source_category = self.drag_data["source_category"]
        item_text = self.drag_data["item_text"]

        if target_category and target_category != source_category:
            print(f"Moving '{item_text[:20]}...' from '{source_category}' to '{target_category}'") # Debug
            self._move_item(source_category, target_category, item_text)
        else:
             print("Drop outside valid target or onto source category. No move.") # Debug

        # Clear drag data
        self.drag_data = None


