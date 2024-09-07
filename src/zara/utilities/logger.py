import asyncio
import http.client
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from logging import FileHandler, StreamHandler


class AsyncHTTPRequestHandler(logging.Handler):
    def __init__(self, url, loop=None):
        super().__init__()
        self.url = url
        parsed_url = url.split("/", 3)
        self.host = parsed_url[2]
        self.path = f"/{parsed_url[3]}" if len(parsed_url) > 3 else "/"
        self.loop = loop or asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor()

    def emit(self, record):
        log_entry = self.format(record)
        self.loop.run_in_executor(self.executor, self.send_log, log_entry)

    def send_log(self, log_entry):
        headers = {"Content-type": "application/json"}
        body = json.dumps({"log": log_entry})

        try:
            conn = http.client.HTTPConnection(self.host)
            conn.request("POST", self.path, body, headers)
            response = conn.getresponse()
            if response.status != 200:
                print(
                    f"Failed to send log. Status: {response.status}, Reason: {response.reason}"
                )
            conn.close()
        except Exception as e:
            print(f"Failed to send log to {self.url}: {e}")


class CustomFormatter(logging.Formatter):
    def __init__(self):
        super().__init__()
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        self.formatter = logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        log_format = {
            logging.DEBUG: "\033[90m",  # Grey
            logging.INFO: "\033[92m",  # Green
            logging.WARNING: "\033[93m",  # Yellow
            logging.ERROR: "\033[91m",  # Red
            logging.CRITICAL: "\033[95m",  # Magenta
        }
        reset = "\033[0m"
        log_color = log_format.get(record.levelno, reset)
        formatted_msg = self.formatter.format(record)
        return f"{log_color}{formatted_msg}{reset}"


async def setup_logger(name, log_file=None, url=None, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler with custom formatting
    console_handler = StreamHandler()
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)

    # File handler if log_file is provided
    if log_file:
        file_handler = FileHandler(log_file)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    # Async HTTP handler if URL is provided
    if url:
        http_handler = AsyncHTTPRequestHandler(url)
        http_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(http_handler)

    return logger
