import clipboard
import threading
import time
import re

class ClipboardHandler:
    """Monitors the system clipboard and categorizes new content based on rules."""

    def __init__(self, categories_ref, process_callback):
        """Initializes the handler with category data and a processing callback."""
        self.categories = categories_ref
        self.process_callback = process_callback # Function to call in main thread
        self.stop_monitoring = threading.Event()
        self.monitor_thread = None
        self.recent_value = self._get_initial_clipboard()

    def _get_initial_clipboard(self):
        """Safely retrieves the initial clipboard content."""
        try:
            value = clipboard.paste()
            return value if isinstance(value, str) else ""
        except Exception as e:
            print(f"Initial clipboard access failed: {e}")
            return ""

    # --- Monitoring Control ---
    def start_monitoring(self):
        """Starts the background thread to monitor clipboard changes."""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.stop_monitoring.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            print("Clipboard monitor thread started.")

    def stop(self):
        """Signals the monitoring thread to stop."""
        self.stop_monitoring.set()
        print("Stop signal sent to clipboard monitor.")

    def join(self, timeout=1.0):
        """Waits for the monitoring thread to finish (optional)."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=timeout)
            print("Clipboard monitor thread joined.")

    # --- Background Monitoring Loop ---
    def _monitor_loop(self):
        """Continuously checks the clipboard for new string content."""
        while not self.stop_monitoring.is_set():
            try:
                current_value = clipboard.paste()

                # Only process strings
                if not isinstance(current_value, str):
                    time.sleep(0.5)
                    continue

                if current_value != self.recent_value and current_value:
                    self.recent_value = current_value
                    # Schedule processing in the main thread via the callback
                    self.process_callback(current_value)

            except clipboard.ClipboardEmpty:
                # Handle case where clipboard becomes empty
                if self.recent_value != "":
                    self.recent_value = ""
            except Exception as e:
                # Log errors but keep monitoring
                print(f"Error reading clipboard in monitor loop: {e}")
                # Reset recent value to prevent potential issues with problematic content
                self.recent_value = self._get_initial_clipboard() # Re-fetch safely

            time.sleep(0.5) # Polling interval

        print("Clipboard monitor loop finished.")

    # --- Content Categorization ---
    @staticmethod
    def categorize_content(content, categories_data):
        """Determines the appropriate category for a piece of text based on rules."""
        if not isinstance(content, str):
            return "Uncategorized" # Or None, depending on desired handling

        # Prioritize specific categories over "Uncategorized"
        categories_to_check = [
            (name, data) for name, data in categories_data.items() if name != "Uncategorized"
        ]

        for cat_name, cat_data in categories_to_check:
            rules = cat_data.get("rules", [])
            for rule in rules:
                try:
                    if rule.startswith("regex:"):
                        pattern = rule[len("regex:"):]
                        if re.search(pattern, content): 
                            return cat_name
                    elif rule in content: 
                        return cat_name
                except re.error as e:
                    print(f"Regex error in category '{cat_name}' rule '{rule}': {e}")
                    # Skip this rule if invalid
                    continue
                except Exception as e:
                    print(f"Error processing rule '{rule}' for category '{cat_name}': {e}")
                    continue # Skip rule on other errors

        # If no specific rules matched, assign to "Uncategorized"
        return "Uncategorized"
