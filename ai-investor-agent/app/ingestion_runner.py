import time
import logging
from app.data_sources import MarketDataService
from app.detectors.fundamental import get_fundamental_context, get_fundamental_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

WATCHLIST = ["TATASTEEL", "RELIANCE", "HDFCBANK", "INFY", "SUNPHARMA"]

def ingest_data_for_symbol(symbol: str):
    logging.info(f"Ingesting data for {symbol}...")
    market = MarketDataService()
    
    # 1. Fetch Market Data
    price_history = market.get_price_history(symbol)
    if price_history.data.empty:
        logging.warning(f"Could not fetch price history for {symbol}")
        
    market.get_bulk_deals(symbol)
    
    # 2. Fetch Fundamental Data 
    fund_context = get_fundamental_context(symbol)
    fund_signals = get_fundamental_signals(symbol)
    
    pe = fund_context.get('pe_ratio')
    growth = fund_context.get('revenue_growth')
    logging.info(f"[{symbol}] Fundamentals: PE={pe}, Sales Growth={growth:.1f}%" if growth else f"[{symbol}] Fundamentals: PE={pe}, Sales Growth=None")
    logging.info(f"[{symbol}] Found {len(fund_signals)} fundamental signals.")

def run_ingestion_job():
    logging.info("Starting scheduled ingestion job...")
    for symbol in WATCHLIST:
        try:
            ingest_data_for_symbol(symbol)
        except Exception as e:
            logging.error(f"Error ingesting {symbol}: {e}")
        time.sleep(2) # Rate limiting
    logging.info("Ingestion job completed.")

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Opportunity Radar Ingestion worker")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=86400, help="Interval in seconds (default 24h)")
    args = parser.parse_args()
    
    if args.once:
        run_ingestion_job()
    else:
        logging.info(f"Ingestion runner started. Interval: {args.interval}s")
        while True:
            run_ingestion_job()
            logging.info(f"Sleeping for {args.interval} seconds...")
            time.sleep(args.interval)
