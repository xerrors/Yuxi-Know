"""URL validation utilities for whitelist-based URL parsing."""
import os
from urllib.parse import urlparse

# Environment variable name for URL whitelist
YUXI_URL_WHITELIST_ENV = "YUXI_URL_WHITELIST"


def _get_whitelist() -> list[str]:
    """Get the URL whitelist from environment variables."""
    whitelist_str = os.environ.get(YUXI_URL_WHITELIST_ENV, "")
    if not whitelist_str:
        return []
    # Split by comma and clean up whitespace
    return [item.strip() for item in whitelist_str.split(",") if item.strip()]


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate if a URL is in the whitelist.

    Args:
        url: The URL to validate.

    Returns:
        A tuple of (is_valid, error_message).
        If is_valid is True, error_message will be empty.
    """
    if not url:
        return False, "URL cannot be empty"

    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    # Check if URL has a valid scheme
    if not parsed.scheme:
        return False, "URL must start with http:// or https://"

    if parsed.scheme not in ("http", "https"):
        return False, "URL must use HTTP or HTTPS protocol"

    # Get the hostname
    hostname = parsed.hostname
    if not hostname:
        return False, "Invalid URL: no hostname found"

    # Get the whitelist
    whitelist = _get_whitelist()

    # If whitelist is empty, URL parsing is disabled
    if not whitelist:
        return False, "URL parsing feature is disabled"

    # Check if hostname is in whitelist
    for allowed in whitelist:
        # Handle wildcard patterns like *.example.com
        if allowed.startswith("*."):
            domain = allowed[2:]
            # Check if hostname ends with the domain (or matches exactly)
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True, ""
        else:
            # Exact match or subdomain match
            if hostname == allowed or hostname.endswith(f".{allowed}"):
                return True, ""

    return False, f"Domain '{hostname}' is not in the whitelist"


def is_url_parsing_enabled() -> bool:
    """Check if URL parsing is enabled (whitelist is configured)."""
    whitelist = _get_whitelist()
    return len(whitelist) > 0


def get_whitelist_info() -> dict:
    """Get information about the current whitelist configuration."""
    whitelist = _get_whitelist()
    return {
        "enabled": len(whitelist) > 0,
        "domains": whitelist,
        "count": len(whitelist),
    }
