"""Browser setup and management using Playwright."""

import json
from pathlib import Path
from typing import Tuple, Optional

from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
)

from config import COOKIES_FILE


async def setup_browser(
    headless: bool = True,
    cookies_file: str = COOKIES_FILE
) -> Tuple[Playwright, Browser, BrowserContext]:
    """
    Initialize Playwright browser with cookies for authenticated session.

    The approach here is to:
    1. First visit the site to establish fresh anti-bot cookies
    2. Then inject only the authentication cookies (access-token)

    Args:
        headless: Run browser without visible window
        cookies_file: Path to cookies JSON file

    Returns:
        Tuple of (playwright, browser, context)
    """
    import asyncio

    playwright = await async_playwright().start()

    # Launch Chromium with anti-detection settings
    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
        ]
    )

    # Create context with download support
    context = await browser.new_context(
        accept_downloads=True,
        locale='de-DE',
        user_agent=(
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/131.0.0.0 Safari/537.36'
        ),
        viewport={'width': 1280, 'height': 800},
    )

    # Remove webdriver flag
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # Load ALL cookies (including fresh anti-bot cookies) since user just exported them
    all_cookies = load_all_cookies(cookies_file)
    if all_cookies:
        await context.add_cookies(all_cookies)
        print(f"  Loaded {len(all_cookies)} cookies")

    return playwright, browser, context


def load_cookies(cookies_file: str) -> list:
    """
    Load cookies from JSON file.

    Args:
        cookies_file: Path to cookies JSON file

    Returns:
        List of cookie dictionaries
    """
    path = Path(cookies_file)
    if not path.exists():
        raise FileNotFoundError(f"Cookies file not found: {cookies_file}")

    with open(path, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    # Filter to only NI domain cookies (skip third-party tracking cookies)
    ni_cookies = [
        c for c in cookies
        if 'native-instruments.com' in c.get('domain', '')
    ]

    return ni_cookies


def load_auth_cookies(cookies_file: str) -> list:
    """
    Load only authentication cookies, excluding anti-bot cookies.

    Anti-bot cookies (Akamai) are session-specific and cannot be reused.
    We only need the access-token and related auth cookies.

    Supports two formats:
    1. Array format (from browser extension export)
    2. Object format with documentCookies key (from console export)

    Args:
        cookies_file: Path to cookies JSON file

    Returns:
        List of authentication cookie dictionaries in Playwright format
    """
    path = Path(cookies_file)
    if not path.exists():
        raise FileNotFoundError(f"Cookies file not found: {cookies_file}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Handle different cookie export formats
    if isinstance(data, dict) and 'documentCookies' in data:
        # Format: {"documentCookies": {"name": "value", ...}, ...}
        cookies = convert_document_cookies(data)
    elif isinstance(data, list):
        # Format: [{"name": "x", "value": "y", "domain": ".example.com", ...}, ...]
        cookies = data
    else:
        raise ValueError(f"Unknown cookie format in {cookies_file}")

    # Authentication cookie names to include
    auth_names = (
        'access-token',
        'refresh-token',
        'localization_country',
        'user_ni_user_language',
        'auth0.SOpam6ZNbnOKlsuC6wUT6O7RK6nggZjg.is.authenticated',
        '_legacy_auth0.SOpam6ZNbnOKlsuC6wUT6O7RK6nggZjg.is.authenticated',
    )

    auth_cookies = [c for c in cookies if c.get('name', '') in auth_names]

    return auth_cookies


def convert_document_cookies(data: dict) -> list:
    """
    Convert documentCookies format to Playwright cookie format.

    Args:
        data: Dict with documentCookies key

    Returns:
        List of cookie dictionaries in Playwright format
    """
    doc_cookies = data.get('documentCookies', {})
    domain = data.get('domain', 'www.native-instruments.com')

    # Ensure domain starts with dot for subdomain matching
    if not domain.startswith('.'):
        domain = '.' + domain.replace('www.', '')

    cookies = []
    for name, value in doc_cookies.items():
        cookies.append({
            'name': name,
            'value': value,
            'domain': domain,
            'path': '/',
            'httpOnly': False,
            'secure': True,
            'sameSite': 'Lax',
        })

    return cookies


def load_all_cookies(cookies_file: str) -> list:
    """
    Load ALL cookies from file (including anti-bot cookies).

    Use this when cookies were just exported and are fresh.

    Supports two formats:
    1. Array format (from browser extension export)
    2. Object format with documentCookies key (from console export)

    Args:
        cookies_file: Path to cookies JSON file

    Returns:
        List of all cookie dictionaries in Playwright format
    """
    path = Path(cookies_file)
    if not path.exists():
        raise FileNotFoundError(f"Cookies file not found: {cookies_file}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Handle different cookie export formats
    if isinstance(data, dict) and 'documentCookies' in data:
        # Format: {"documentCookies": {"name": "value", ...}, ...}
        cookies = convert_document_cookies(data)
    elif isinstance(data, list):
        # Format: [{"name": "x", "value": "y", "domain": ".example.com", ...}, ...]
        # Filter to NI domain only
        cookies = [
            c for c in data
            if 'native-instruments.com' in c.get('domain', '')
        ]
    else:
        raise ValueError(f"Unknown cookie format in {cookies_file}")

    return cookies


async def close_browser(
    playwright: Playwright,
    browser: Browser
) -> None:
    """
    Clean up browser resources.

    Handles cases where the browser connection may already be closed
    (e.g., after Ctrl+C or browser crash).

    Args:
        playwright: Playwright instance
        browser: Browser instance
    """
    try:
        await browser.close()
    except Exception:
        # Browser connection already closed, ignore
        pass

    try:
        await playwright.stop()
    except Exception:
        # Playwright already stopped, ignore
        pass


async def check_auth_status(page: Page) -> bool:
    """
    Check if the current session is authenticated.

    Args:
        page: Playwright page

    Returns:
        True if authenticated, False otherwise
    """
    # Check for login redirect or login button presence
    current_url = page.url

    # If we're on a login page without returnTo, we've been logged out
    if '/auth/login' in current_url and 'returnTo=' not in current_url:
        return False

    # Look for signs of being logged out
    try:
        login_btn = await page.query_selector('.login-button, .btn-login, [data-action="login"]')
        if login_btn:
            # Check if it's visible
            is_visible = await login_btn.is_visible()
            if is_visible:
                return False
    except Exception:
        pass

    return True


async def create_page(context: BrowserContext) -> Page:
    """
    Create a new page with default settings.

    Args:
        context: Browser context

    Returns:
        New page instance
    """
    page = await context.new_page()

    # Set reasonable viewport
    await page.set_viewport_size({'width': 1280, 'height': 800})

    return page
