# main.py
"""
Main entry point for the Clipboard Category Manager application.
Initializes the appearance, creates the main application window,
and starts the Tkinter event loop.
"""

import customtkinter as ctk
from app_gui import ClipboardManagerApp # Import the main application class

if __name__ == "__main__":
    # --- Application Setup ---
    # Configure the visual appearance and theme of the application
    ctk.set_appearance_mode("System") # Options: "System", "Dark", "Light"
    ctk.set_default_color_theme("blue") # Options: "blue", "green", "dark-blue"

    # --- Run Application ---
    # Create an instance of the main application window and run it
    app = ClipboardManagerApp()
    app.mainloop()
