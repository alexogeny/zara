import asyncio
import logging
import os
import sys
import threading
import time

from zara.utilities.logger import setup_logger


class FileMonitor:
    def __init__(self, watch_dir, interval=3, env_file=".env"):
        self.watch_dir = watch_dir
        self.env_file = os.path.join(os.getcwd(), env_file)
        self.interval = interval  # How often to check for file changes
        self.file_mtimes = {}
        self.logger = asyncio.get_event_loop().run_until_complete(
            setup_logger("FileMonitor", level=logging.INFO)
        )

    def start(self):
        """Start the monitoring in a background thread."""
        monitor_thread = threading.Thread(target=self._monitor_files, daemon=True)
        monitor_thread.start()

    def _monitor_files(self):
        """Monitor the files in the directory for changes."""
        while True:
            self._check_directory(self.watch_dir)
            self._check_file("example.py")
            self._check_file(self.env_file)  # Explicitly monitor the .env file
            time.sleep(self.interval)

    def _check_directory(self, directory):
        """Check all files in the directory for modification."""
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                path = os.path.join(dirpath, filename)
                self._check_file(path)

    def _check_file(self, path):
        """Check a single file for modification."""
        try:
            current_mtime = os.path.getmtime(path)
            if path not in self.file_mtimes:
                self.file_mtimes[path] = current_mtime
            elif current_mtime != self.file_mtimes[path]:
                self.logger.info(f"File changed: {path}")
                self.file_mtimes[path] = current_mtime
                self.reload_server()
        except FileNotFoundError:
            pass

    def reload_server(self):
        """Reload the server by restarting the Python interpreter."""
        self.logger.info("Reloading server due to file changes...")
        os.execv(sys.executable, ["python"] + sys.argv)
