"""
screener_scraper.py
-------------------
Scrape company financials from https://www.screener.in/company/{SYMBOL}/

Usage:
    from screener_scraper import scrape_screener
    data = scrape_screener("TCS")

Requirements:
    pip install requests beautifulsoup4 pandas lxml
"""

import re
import requests
from langchain.tools import tool
import pandas as pd
from bs4 import BeautifulSoup
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.screener.in/company/{symbol}/consolidated/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.screener.in/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Strip whitespace and normalise unicode spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _fetch(symbol: str) -> BeautifulSoup:
    """Fetch the screener page and return a BeautifulSoup object."""
    url = BASE_URL.format(symbol=symbol.upper())
    resp = requests.get(url, headers=HEADERS, timeout=30)

    # Fall back to standalone page if consolidated doesn't exist
    if resp.status_code == 404:
        url = f"https://www.screener.in/company/{symbol.upper()}/"
        resp = requests.get(url, headers=HEADERS, timeout=30)

    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def _table_to_df(section: BeautifulSoup) -> pd.DataFrame:
    """
    Convert a screener.in financial table inside *section* to a DataFrame.

    Screener tables look like:
        <table>
          <thead><tr><th></th><th>Mar 2020</th>...</tr></thead>
          <tbody>
            <tr><td class="...">Sales</td><td>1000</td>...</tr>
            ...
          </tbody>
        </table>
    """
    table = section.find("table")
    if table is None:
        return pd.DataFrame()

    # ---- header row ----
    header_cells = table.select("thead th")
    columns = [_clean(th.get_text()) for th in header_cells]

    # ---- data rows ----
    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        row = [_clean(td.get_text()) for td in cells]
        # Pad / trim to match column count
        if len(row) < len(columns):
            row += [""] * (len(columns) - len(row))
        else:
            row = row[: len(columns)]
        rows.append(row)

    if not columns or not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=columns if columns else None)

    # Use first column (row labels) as index if it looks like a label column
    first_col = columns[0] if columns else ""
    if first_col == "" or first_col.lower() in ("", "#"):
        df = df.set_index(df.columns[0])
        df.index.name = None

    return df


def _filter_df_rows(df: pd.DataFrame, wanted: list) -> pd.DataFrame:
    """
    Keep only rows whose index label contains one of the *wanted* substrings
    (case-insensitive).  Returns the original df if no filter matches.
    """
    if df.empty or not wanted:
        return df
    mask = df.index.to_series().str.contains(
        "|".join(re.escape(w) for w in wanted), case=False, na=False
    )
    filtered = df[mask]
    return filtered if not filtered.empty else df


def _filter_df_cols(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Keep the last *n* columns (years / quarters)."""
    if df.empty:
        return df
    return df.iloc[:, -n:] if df.shape[1] > n else df


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_summary(soup: BeautifulSoup) -> dict:
    """Extract the top-level company summary box."""
    data: dict = {
        "company_name": "",
        "current_price": "",
        "market_cap": "",
        "stock_pe": "",
        "book_value": "",
        "dividend_yield": "",
        "roce": "",
        "roe": "",
        "high_52w": "",
        "low_52w": "",
    }

    try:
        name_tag = soup.find("h1", class_="margin-0")
        if name_tag:
            data["company_name"] = _clean(name_tag.get_text())
    except Exception:
        pass

    try:
        # Current price lives in the first .number span inside #top-ratios
        price_tag = soup.select_one(".company-header .number") or \
                    soup.select_one("#top-ratios .number") or \
                    soup.select_one("span.number")
        if price_tag:
            data["current_price"] = _clean(price_tag.get_text())
    except Exception:
        pass

    # Top-ratios are rendered as a list of <li> elements with a label + value
    try:
        ratio_items = soup.select("#top-ratios li")
        for li in ratio_items:
            label_tag = li.find("span", class_="name") or li.find("span", class_=re.compile("name"))
            value_tag = li.find("span", class_="number") or li.find("span", class_=re.compile("value|number"))
            if not label_tag or not value_tag:
                # Try generic child spans
                spans = li.find_all("span")
                if len(spans) >= 2:
                    label_tag, value_tag = spans[0], spans[-1]
                else:
                    continue

            label = _clean(label_tag.get_text()).lower()
            value = _clean(value_tag.get_text())

            if "market cap" in label:
                data["market_cap"] = value
            elif "stock p/e" in label or "p/e" in label:
                data["stock_pe"] = value
            elif "book value" in label:
                data["book_value"] = value
            elif "dividend yield" in label:
                data["dividend_yield"] = value
            elif "roce" in label:
                data["roce"] = value
            elif "roe" in label:
                data["roe"] = value
            elif "52 week high" in label or "high / low" in label:
                # "52w High / Low" sometimes combined: "2500 / 1800"
                parts = value.split("/")
                data["high_52w"] = parts[0].strip() if parts else value
                data["low_52w"] = parts[1].strip() if len(parts) > 1 else ""
            elif "52 week low" in label:
                data["low_52w"] = value
    except Exception:
        pass

    return data


def _parse_financial_table(
    soup: BeautifulSoup,
    section_id: str,
    wanted_rows: Optional[list] = None,
    last_n_cols: Optional[int] = None,
) -> pd.DataFrame:
    """Generic parser for any screener financial table section."""
    try:
        section = soup.find(id=section_id)
        if section is None:
            return pd.DataFrame()
        df = _table_to_df(section)
        if wanted_rows:
            df = _filter_df_rows(df, wanted_rows)
        if last_n_cols:
            df = _filter_df_cols(df, last_n_cols)
        return df
    except Exception as exc:
        print(f"[WARN] Could not parse section '{section_id}': {exc}")
        return pd.DataFrame()


def _parse_shareholding(soup: BeautifulSoup) -> dict:
    """
    Parse the shareholding pattern table.

    Returns:
        {
          "latest": {"promoters": "...", "fii": "...", "dii": "...", "public": "..."},
          "trend":  DataFrame (4 quarters × 4 categories)
        }
    """
    result = {
        "latest": {"promoters": "", "fii": "", "dii": "", "public": ""},
        "trend": pd.DataFrame(),
    }
    try:
        section = soup.find(id="shareholding")
        if section is None:
            return result

        # screener renders two sub-tables: quarterly + yearly
        # We want the quarterly one
        tables = section.find_all("table")
        if not tables:
            return result

        # Pick the first table (usually quarterly)
        table = tables[0]
        header_cells = table.select("thead th")
        columns = [_clean(th.get_text()) for th in header_cells]

        rows = []
        row_labels = []
        for tr in table.select("tbody tr"):
            cells = tr.find_all("td")
            if not cells:
                continue
            label = _clean(cells[0].get_text())
            values = [_clean(td.get_text()) for td in cells[1:]]
            row_labels.append(label)
            rows.append(values)

        data_cols = columns[1:] if columns else []
        df = pd.DataFrame(rows, index=row_labels, columns=data_cols if data_cols else None)

        # Keep last 4 quarters
        result["trend"] = df.iloc[:, -4:] if df.shape[1] > 4 else df

        # Latest quarter = last column
        if not df.empty and df.shape[1] >= 1:
            latest = df.iloc[:, -1]
            for idx, val in latest.items():
                lbl = str(idx).lower()
                if "promoter" in lbl:
                    result["latest"]["promoters"] = val
                elif "fii" in lbl or "foreign" in lbl:
                    result["latest"]["fii"] = val
                elif "dii" in lbl or "domestic inst" in lbl:
                    result["latest"]["dii"] = val
                elif "public" in lbl or "others" in lbl:
                    result["latest"]["public"] = val

    except Exception as exc:
        print(f"[WARN] Could not parse shareholding: {exc}")

    return result


def _parse_pros_cons(soup: BeautifulSoup) -> tuple:
    """Return (pros: list[str], cons: list[str])."""
    pros, cons = [], []
    try:
        # screener wraps pros/cons in <div class="pros"> and <div class="cons">
        pros_div = soup.find("div", class_="pros")
        if pros_div:
            pros = [_clean(li.get_text()) for li in pros_div.find_all("li")]

        cons_div = soup.find("div", class_="cons")
        if cons_div:
            cons = [_clean(li.get_text()) for li in cons_div.find_all("li")]
    except Exception as exc:
        print(f"[WARN] Could not parse pros/cons: {exc}")
    return pros, cons


def _parse_about(soup: BeautifulSoup) -> dict:
    """Extract company description and key points."""
    about: dict = {"description": "", "key_points": ""}
    try:
        # screener puts a company description in #company-info or .about section
        about_section = (
            soup.find("div", class_="about")
            or soup.find("div", id="company-info")
            or soup.find("section", id="about")
        )
        if about_section:
            paras = about_section.find_all("p")
            if paras:
                about["description"] = _clean(paras[0].get_text())

            # Key points often follow in a second <p> or a <div>
            key_div = about_section.find("div", class_="key-points") or (
                paras[1] if len(paras) > 1 else None
            )
            if key_div:
                about["key_points"] = _clean(key_div.get_text())
    except Exception as exc:
        print(f"[WARN] Could not parse about: {exc}")
    return about


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------
@tool
def scrape_screener(symbol: str) -> dict:
    """
    Scrape https://www.screener.in/company/{symbol}/ and return a dict:

        {
          "summary":       dict,
          "quarterly":     pd.DataFrame,
          "pnl":           pd.DataFrame,
          "balance_sheet": pd.DataFrame,
          "cashflow":      pd.DataFrame,
          "ratios":        pd.DataFrame,
          "shareholding":  {"latest": dict, "trend": pd.DataFrame},
          "pros":          list[str],
          "cons":          list[str],
          "about":         {"description": str, "key_points": str},
        }
    """
    print(f"[INFO] Fetching data for: {symbol.upper()}")
    soup = _fetch(symbol)

    # 1. Summary
    summary = _parse_summary(soup)

    # 2. Quarterly Results
    quarterly = _parse_financial_table(
        soup,
        section_id="quarters",
        wanted_rows=["Sales", "Expenses", "Operating Profit", "OPM", "Net Profit", "EPS"],
        last_n_cols=8,
    )

    # 3. Profit & Loss
    pnl = _parse_financial_table(
        soup,
        section_id="profit-loss",
        wanted_rows=["Sales", "Expenses", "Operating Profit", "OPM", "Net Profit", "EPS"],
        last_n_cols=6,
    )

    # 4. Balance Sheet
    balance_sheet = _parse_financial_table(
        soup,
        section_id="balance-sheet",
        wanted_rows=["Equity Capital", "Reserves", "Borrowings", "Total Assets"],
        last_n_cols=5,
    )

    # 5. Cash Flow
    cashflow = _parse_financial_table(
        soup,
        section_id="cash-flow",
        wanted_rows=["Operating", "Investing", "Financing"],
        last_n_cols=5,
    )

    # 6. Key Ratios
    ratios = _parse_financial_table(
        soup,
        section_id="ratios",
        wanted_rows=["Debtor Days", "Inventory Days", "ROCE", "ROE", "Dividend Payout"],
        last_n_cols=5,
    )

    # 7. Shareholding
    shareholding = _parse_shareholding(soup)

    # 8. Pros & Cons
    pros, cons = _parse_pros_cons(soup)

    # 9. About / Key Points
    about = _parse_about(soup)

    company_data = {
        "summary": summary,
        "quarterly": quarterly,
        "pnl": pnl,
        "balance_sheet": balance_sheet,
        "cashflow": cashflow,
        "ratios": ratios,
        "shareholding": shareholding,
        "pros": pros,
        "cons": cons,
        "about": about,
    }

    return company_data


# ---------------------------------------------------------------------------
# Quick CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    symbol = sys.argv[1] if len(sys.argv) > 1 else "TCS"
    data = scrape_screener(symbol)

    print("\n" + "=" * 60)
    print(f"SUMMARY — {data['summary'].get('company_name', symbol)}")
    print("=" * 60)
    for k, v in data["summary"].items():
        if k != "company_name":
            print(f"  {k:<20}: {v}")

    for section_name in ("quarterly", "pnl", "balance_sheet", "cashflow", "ratios"):
        df: pd.DataFrame = data[section_name]
        print(f"\n{'=' * 60}")
        print(f"{section_name.upper()}")
        print("=" * 60)
        if df.empty:
            print("  [no data]")
        else:
            print(df.to_string())

    print(f"\n{'=' * 60}")
    print("SHAREHOLDING (latest quarter)")
    print("=" * 60)
    for k, v in data["shareholding"]["latest"].items():
        print(f"  {k:<12}: {v}")
    print("\nTrend:")
    trend = data["shareholding"]["trend"]
    if not trend.empty:
        print(trend.to_string())

    print(f"\n{'=' * 60}")
    print("PROS")
    print("=" * 60)
    for p in data["pros"]:
        print(f"  + {p}")

    print(f"\n{'=' * 60}")
    print("CONS")
    print("=" * 60)
    for c in data["cons"]:
        print(f"  - {c}")

    print(f"\n{'=' * 60}")
    print("ABOUT")
    print("=" * 60)
    print(data["about"]["description"])
    if data["about"]["key_points"]:
        print("\nKey Points:")
        print(data["about"]["key_points"])