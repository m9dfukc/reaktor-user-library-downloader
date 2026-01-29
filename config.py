"""Configuration constants for Reaktor User Library Downloader."""

# Base URLs
BASE_URL = "https://www.native-instruments.com"
LIBRARY_URL = f"{BASE_URL}/de/reaktor-community/reaktor-user-library/"
PAGINATION_PATTERN = "/de/reaktor-community/reaktor-user-library/all/all/all/all/all/latest/{page}/all/"

# File paths
DOWNLOAD_DIR = "./downloads"
COOKIES_FILE = "./cookies.json"
STATE_FILE = "./state.json"

# Download settings
SIZE_CHECK_THRESHOLD = 10 * 1024 * 1024 * 1024  # 10 GB in bytes

# Rate limiting
PAGE_DELAY_SECONDS = 1.0       # Delay between page loads
DOWNLOAD_DELAY_SECONDS = 0.5   # Delay between downloads
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5.0
DOWNLOAD_TIMEOUT_MS = 120000   # 2 minutes timeout for downloads

# Pagination
TOTAL_PAGES = 435
