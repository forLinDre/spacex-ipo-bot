"""
Source checking module for SpaceX IPO Bot.

Monitors multiple online sources for SpaceX IPO news and rumors.
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

import requests
import feedparser

logger = logging.getLogger(__name__)

# User-Agent to avoid being blocked
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# =============================================================================
# SEARCH TERMS
# =============================================================================

# Terms that indicate a CONFIRMED IPO
CONFIRMED_KEYWORDS = [
    "spacex s-1 filing",
    "spacex files for ipo",
    "spacex filed s-1",
    "spacex ipo confirmed",
    "spacex goes public",
    "spacex has gone public",
    "spacex public offering approved",
    "spacex ipo date set",
    "spacex begins trading",
    "spacex listed on nasdaq",
    "spacex listed on nyse",
    "space exploration technologies s-1",
    "space exploration technologies ipo",
]

# Terms that indicate RUMORS about IPO or dates
RUMOR_KEYWORDS = [
    "spacex ipo",
    "spacex public offering",
    "spacex ipo date",
    "spacex ipo timeline",
    "spacex ipo expected",
    "spacex ipo rumor",
    "spacex ipo plan",
    "spacex listing date",
    "spacex direct listing",
    "spacex may go public",
    "spacex could go public",
    "spacex considering ipo",
    "spacex ipo 2025",
    "spacex ipo 2026",
    "spacex ipo 2027",
    "elon musk spacex ipo",
    "elon musk spacex public",
]

# Regex patterns to extract rumored dates/timeframes
DATE_PATTERNS = [
    r"(Q[1-4]\s*20\d{2})",                          # Q1 2026, Q3 2027
    r"((?:early|mid|late)\s*20\d{2})",               # early 2026, late 2027
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s*20\d{2})",
    r"(20\d{2})",                                     # standalone year
    r"((?:first|second|third|fourth)\s*(?:quarter|half)\s*(?:of\s*)?20\d{2})",
    r"(within\s*\d+\s*(?:months?|years?))",           # within 6 months
    r"(by\s*(?:end\s*of\s*)?20\d{2})",               # by end of 2026
    r"(as\s*(?:early|soon)\s*as\s*\w+\s*20\d{2})",   # as early as March 2026
]


@dataclass
class Article:
    """Represents a found article/post about SpaceX IPO."""
    title: str
    url: str
    source: str
    alert_level: str  # "confirmed" or "rumor"
    rumored_date: Optional[str] = None  # Extracted date/timeframe if found
    ticker_symbol: Optional[str] = None  # Ticker symbol if found (e.g., from SEC filing)


def extract_rumored_date(text: str) -> Optional[str]:
    """
    Extract a rumored IPO date or timeframe from text.

    Args:
        text: The article title or snippet to search.

    Returns:
        The first date/timeframe match found, or None.
    """
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def classify_article(title: str, description: str = "") -> Optional[str]:
    """
    Classify an article as 'confirmed', 'rumor', or None (irrelevant).

    Args:
        title: Article title.
        description: Article description/snippet.

    Returns:
        'confirmed', 'rumor', or None.
    """
    combined = f"{title} {description}".lower()

    # Check for confirmed signals first
    for keyword in CONFIRMED_KEYWORDS:
        if keyword in combined:
            return "confirmed"

    # Check for rumor signals
    for keyword in RUMOR_KEYWORDS:
        if keyword in combined:
            return "rumor"

    return None


def check_google_news() -> List[Article]:
    """
    Check Google News RSS for SpaceX IPO articles.

    Returns:
        List of Article objects found.
    """
    articles = []
    search_queries = [
        "SpaceX+IPO",
        "SpaceX+public+offering",
        "SpaceX+S-1+filing",
        "SpaceX+IPO+date",
        "SpaceX+goes+public",
    ]

    for query in search_queries:
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:  # Check top 10 per query
                title = entry.get("title", "")
                link = entry.get("link", "")
                description = entry.get("summary", "")

                alert_level = classify_article(title, description)
                if alert_level:
                    rumored_date = extract_rumored_date(f"{title} {description}")
                    articles.append(Article(
                        title=title,
                        url=link,
                        source="Google News",
                        alert_level=alert_level,
                        rumored_date=rumored_date,
                    ))
        except Exception as e:
            logger.warning(f"Error fetching Google News for '{query}': {e}")

    return articles


def _extract_ticker_symbol(text: str) -> Optional[str]:
    """
    Extract a ticker symbol from text (e.g., from SEC filing display names).

    Looks for patterns like "(TSLA)", "(SPCE, SPCEW)", etc.

    Args:
        text: Text that may contain a ticker symbol in parentheses.

    Returns:
        The primary ticker symbol if found, or None.
    """
    # Match ticker symbols in parentheses - e.g., "(TSLA)" or "(ASTS, ASTSW)"
    match = re.search(r"\(([A-Z]{1,5})(?:[,\s]+[A-Z]{1,6})*\)", text)
    if match:
        return match.group(1)
    return None


def _is_spacex_filing(title: str, entity_name: str = "") -> bool:
    """Check if a filing is actually from SpaceX (not another space company)."""
    combined = f"{title} {entity_name}".lower()
    spacex_indicators = [
        "space exploration technologies",
        "spacex",
    ]
    return any(indicator in combined for indicator in spacex_indicators)


def check_sec_edgar() -> List[Article]:
    """
    Check SEC EDGAR for SpaceX (Space Exploration Technologies Corp) filings.

    Looks for S-1, S-1/A (IPO registration statements).
    Filters strictly to only include actual SpaceX filings.

    Returns:
        List of Article objects found.
    """
    articles = []

    # Use the EDGAR full-text search API with exact company name
    try:
        api_url = (
            "https://efts.sec.gov/LATEST/search-index?"
            "q=%22Space+Exploration+Technologies+Corp%22"
            "&forms=S-1,S-1/A&dateRange=custom&startdt=2024-01-01"
        )
        response = requests.get(api_url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            hits = data.get("hits", {}).get("hits", [])
            for hit in hits:
                source_data = hit.get("_source", {})
                title = source_data.get("display_names", ["SpaceX SEC Filing"])[0]
                entity_name = source_data.get("entity_name", "")

                # Only include if it's actually SpaceX
                if not _is_spacex_filing(title, entity_name):
                    continue

                file_num = source_data.get("file_num", "")
                filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={file_num}"

                # Extract ticker symbol from display name (e.g., "SpaceX (SPCE)")
                ticker = _extract_ticker_symbol(title)

                articles.append(Article(
                    title=f"SEC S-1 Filing: {title}",
                    url=filing_url,
                    source="SEC EDGAR",
                    alert_level="confirmed",
                    rumored_date=None,
                    ticker_symbol=ticker,
                ))
    except Exception as e:
        logger.warning(f"Error checking SEC EDGAR full-text search: {e}")

    # Check EDGAR company search with exact name
    try:
        company_url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            "?company=space+exploration+technologies+corp"
            "&CIK=&type=S-1&dateb=&owner=include&count=10"
            "&search_text=&action=getcompany&output=atom"
        )
        response = requests.get(company_url, headers=HEADERS, timeout=15)
        if response.status_code == 200 and len(response.text) > 500:
            # Parse the Atom feed for results
            feed = feedparser.parse(response.text)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")

                if _is_spacex_filing(title):
                    articles.append(Article(
                        title=f"SEC S-1 Filing: {title}",
                        url=link,
                        source="SEC EDGAR",
                        alert_level="confirmed",
                        rumored_date=None,
                    ))
    except Exception as e:
        logger.warning(f"Error checking SEC EDGAR company search: {e}")

    return articles


def check_reddit() -> List[Article]:
    """
    Check Reddit for SpaceX IPO discussions.

    Monitors r/wallstreetbets, r/stocks, r/investing, r/spacex.

    Returns:
        List of Article objects found.
    """
    articles = []
    subreddits = ["wallstreetbets", "stocks", "investing", "spacex", "stockmarket"]

    for subreddit in subreddits:
        url = f"https://www.reddit.com/r/{subreddit}/search.json?q=SpaceX+IPO&sort=new&t=week&restrict_sr=1"
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                posts = data.get("data", {}).get("children", [])
                for post in posts[:5]:  # Top 5 per subreddit
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")
                    permalink = post_data.get("permalink", "")
                    selftext = post_data.get("selftext", "")[:500]

                    alert_level = classify_article(title, selftext)
                    if alert_level:
                        rumored_date = extract_rumored_date(f"{title} {selftext}")
                        articles.append(Article(
                            title=title,
                            url=f"https://www.reddit.com{permalink}",
                            source=f"Reddit r/{subreddit}",
                            alert_level=alert_level,
                            rumored_date=rumored_date,
                        ))
            elif response.status_code == 429:
                logger.warning(f"Reddit rate limited for r/{subreddit}")
        except Exception as e:
            logger.warning(f"Error checking Reddit r/{subreddit}: {e}")

    return articles


def check_ticker_live(ticker: str) -> Optional[dict]:
    """
    Check if a ticker symbol is actively trading using Yahoo Finance.

    Args:
        ticker: The ticker symbol to check (e.g., "SPCE").

    Returns:
        A dict with price info if trading, or None if not yet live.
        Example: {"price": 142.50, "exchange": "NASDAQ", "name": "SpaceX"}
    """
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?interval=1m&range=1d"
        )
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code != 200:
            return None

        data = response.json()
        result = data.get("chart", {}).get("result")

        if not result:
            return None

        meta = result[0].get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        exchange = meta.get("exchangeName", "Unknown")
        name = meta.get("shortName", ticker)
        market_state = meta.get("marketState", "")

        # Price must be > 0 and market state should indicate it's active
        if price and price > 0:
            return {
                "price": price,
                "exchange": exchange,
                "name": name,
                "market_state": market_state,
                "currency": meta.get("currency", "USD"),
            }

        return None

    except Exception as e:
        logger.debug(f"Ticker check for {ticker} failed: {e}")
        return None


def check_all_sources() -> List[Article]:
    """
    Check all sources for SpaceX IPO news.

    Returns:
        Combined list of all articles found across all sources.
    """
    all_articles = []

    logger.info("Checking Google News...")
    all_articles.extend(check_google_news())

    logger.info("Checking SEC EDGAR...")
    all_articles.extend(check_sec_edgar())

    logger.info("Checking Reddit...")
    all_articles.extend(check_reddit())

    logger.info(f"Found {len(all_articles)} total articles across all sources.")
    return all_articles
