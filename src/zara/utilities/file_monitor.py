import os
import sys
import threading
import time


class FileMonitor:
    def __init__(self, watch_dir, interval=3):
        self.watch_dir = watch_dir
        self.interval = interval  # How often to check for file changes
        self.file_mtimes = {}

    def start(self):
        """Start the monitoring in a background thread."""
        monitor_thread = threading.Thread(target=self._monitor_files, daemon=True)
        monitor_thread.start()

    def _monitor_files(self):
        """Monitor the files in the directory for changes."""
        while True:
            self._check_directory(self.watch_dir)
            self._check_file("example.py")
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
                print(f"File changed: {path}")
                self.file_mtimes[path] = current_mtime
                self.reload_server()
        except FileNotFoundError:
            pass

    def reload_server(self):
        """Reload the server by restarting the Python interpreter."""
        print("Reloading server...")
        os.execv(sys.executable, ["python"] + sys.argv)
