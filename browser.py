import atexit
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager

# ─── One global driver we keep alive ────────────────────────────────────────────
_driver = None

def _init_driver(headless: bool = False):
    """Create the global Firefox driver once."""
    global _driver
    if _driver is not None:
        return _driver

    options = webdriver.FirefoxOptions()
    if headless:
        options.add_argument("--headless")

    service = FirefoxService(executable_path=GeckoDriverManager().install())
    _driver = webdriver.Firefox(service=service, options=options)

    # Make sure we close the browser when Python exits
    atexit.register(lambda: _driver.quit() if _driver else None)
    return _driver

def open_new_tab(url: str, headless: bool = False) -> str:
    """Open URL in a new tab (or first tab if none)."""
    if not url:
        raise ValueError("URL must not be empty")

    driver = _init_driver(headless=headless)

    # If this is the first call, driver has one blank tab. Load URL there.
    if len(driver.window_handles) == 1 and driver.current_url in ("about:blank", "data:"):
        driver.get(url)
    else:
        driver.execute_script(f"window.open('{url}', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])

    return f"✅ Opened: {url}"

def search_google(query: str, headless: bool = False) -> str:
    """Perform a Google search and open the results."""
    if not query:
        raise ValueError("Search query must not be empty")

    google_url = f"https://www.google.com/search?q={query}"
    return open_new_tab(google_url, headless=headless)

def navigate_to(url: str, headless: bool = False) -> str:
    """Navigate to a URL in the browser."""
    if not url:
        raise ValueError("URL must not be empty")

    driver = _init_driver(headless=headless)
    driver.get(url)

    return f"✅ Navigated to: {url}"
