from __future__ import annotations

import logging
from tools.screener import scrape_screener

def get_fundamental_signals(symbol: str) -> list[dict[str, str | int | float]]:
    signals = []
    try:
        data = scrape_screener.invoke({"symbol": symbol})
        if not data:
            return signals

        # 1. Earnings/Sales Growth & Margin Expansion
        quarterly = data.get("quarterly")
        if quarterly is not None and not quarterly.empty:
            if "Sales" in quarterly.index and quarterly.shape[1] >= 2:
                recent_sales = quarterly.loc["Sales"].iloc[-1]
                prev_sales = quarterly.loc["Sales"].iloc[-2]
                try:
                    rs = float(str(recent_sales).replace(",", ""))
                    ps = float(str(prev_sales).replace(",", ""))
                    if ps > 0 and rs > ps * 1.05:
                        signals.append({
                            "signal_type": "Earnings surprise",
                            "strength_score": min(1.0, 0.5 + ((rs/ps)-1)), 
                            "short_explanation": f"High revenue growth: +{((rs/ps)-1)*100:.1f}% QoQ",
                            "source": "screener.in"
                        })
                except:
                    pass
                    
            if "OPM %" in quarterly.index or "OPM" in quarterly.index:
                opm_key = "OPM %" if "OPM %" in quarterly.index else "OPM"
                if quarterly.shape[1] >= 2:
                    recent_opm = quarterly.loc[opm_key].iloc[-1]
                    prev_opm = quarterly.loc[opm_key].iloc[-2]
                    try:
                        ro = float(str(recent_opm).replace("%", ""))
                        po = float(str(prev_opm).replace("%", ""))
                        if ro > po + 2.0:
                            signals.append({
                                "signal_type": "Margin expansion",
                                "strength_score": min(1.0, 0.6 + (ro - po) * 0.05),
                                "short_explanation": f"Operating margin expanded from {po}% to {ro}%",
                                "source": "screener.in"
                            })
                    except:
                        pass

        # 2. Shareholding accumulation
        shareholding = data.get("shareholding")
        if shareholding and "trend" in shareholding and not shareholding["trend"].empty:
            trend = shareholding["trend"]
            # FII or Promoter accumulation
            if "Promoters" in trend.index and trend.shape[1] >= 2:
                recent_promoter = trend.loc["Promoters"].iloc[-1]
                prev_promoter = trend.loc["Promoters"].iloc[-2]
                try:
                    r_p = float(str(recent_promoter).replace("%", ""))
                    p_p = float(str(prev_promoter).replace("%", ""))
                    if r_p - p_p >= 0.5:
                        signals.append({
                            "signal_type": "Promoter buying",
                            "strength_score": min(1.0, 0.7 + (r_p - p_p) * 0.1),
                            "short_explanation": f"Promoters increased stake by {r_p - p_p:.2f}% to {r_p:.2f}%",
                            "source": "screener.in"
                        })
                except:
                    pass
                    
            fii_idx = next((idx for idx in trend.index if "FII" in idx or "Foreign" in idx), None)
            if fii_idx and trend.shape[1] >= 2:
                recent_fii = trend.loc[fii_idx].iloc[-1]
                prev_fii = trend.loc[fii_idx].iloc[-2]
                try:
                    r_f = float(str(recent_fii).replace("%", ""))
                    p_f = float(str(prev_fii).replace("%", ""))
                    if r_f - p_f >= 0.5:
                        signals.append({
                            "signal_type": "Institutional buying",
                            "strength_score": min(1.0, 0.6 + (r_f - p_f) * 0.1),
                            "short_explanation": f"FIIs increased stake by {r_f - p_f:.2f}% to {r_f:.2f}%",
                            "source": "screener.in"
                        })
                except:
                    pass
                    
        # 3. Undervalued Growth
        summary = data.get("summary", {})
        pe_val = None
        if summary.get("stock_pe"):
            try: pe_val = float(summary["stock_pe"].replace(",", ""))
            except: pass
            
        if pe_val is not None and pe_val < 25 and any(s["signal_type"] == "Earnings surprise" for s in signals):
            signals.append({
                "signal_type": "Undervalued growth",
                "strength_score": 0.85,
                "short_explanation": f"Low PE ({pe_val}) combined with high recent growth",
                "source": "screener.in"
            })

    except Exception as e:
        logging.error(f"Error fetching fundamentals for {symbol}: {e}")

    return signals


def get_fundamental_context(symbol: str) -> dict[str, float | str | None]:
    context = {
        "pe_ratio": None,
        "roce": None,
        "roe": None,
        "debt_to_equity": None,
        "revenue_growth": None,
        "profit_growth": None,
        "operating_margin": None,
        "source": "none"
    }
    
    try:
        data = scrape_screener.invoke({"symbol": symbol})
        if not data:
            return context
            
        summary = data.get("summary", {})
        if summary.get("stock_pe"):
            try: context["pe_ratio"] = float(summary["stock_pe"].replace(",", ""))
            except: pass
            
        if summary.get("roce"):
            try: context["roce"] = float(summary["roce"].replace("%", ""))
            except: pass
            
        if summary.get("roe"):
            try: context["roe"] = float(summary["roe"].replace("%", ""))
            except: pass
            
        if summary.get("debt_to_equity"):
            try: context["debt_to_equity"] = float(summary["debt_to_equity"])
            except: pass
            
        quarterly = data.get("quarterly")
        if quarterly is not None and not quarterly.empty:
            if "OPM %" in quarterly.index or "OPM" in quarterly.index:
                opm_key = "OPM %" if "OPM %" in quarterly.index else "OPM"
                recent_opm = quarterly.loc[opm_key].iloc[-1]
                if str(recent_opm).strip() and "%" in str(recent_opm):
                    try: context["operating_margin"] = float(str(recent_opm).replace("%", ""))
                    except: pass
                else:
                    try: context["operating_margin"] = float(recent_opm)
                    except: pass
                    
            if "Sales" in quarterly.index and quarterly.shape[1] >= 5:
                recent_sales = quarterly.loc["Sales"].iloc[-1]
                yoy_sales = quarterly.loc["Sales"].iloc[-5] 
                try:
                    rs = float(str(recent_sales).replace(",", ""))
                    ys = float(str(yoy_sales).replace(",", ""))
                    if ys > 0:
                        context["revenue_growth"] = ((rs / ys) - 1) * 100
                except: pass
                
            if "Net Profit" in quarterly.index and quarterly.shape[1] >= 5:
                recent_profit = quarterly.loc["Net Profit"].iloc[-1]
                yoy_profit = quarterly.loc["Net Profit"].iloc[-5] 
                try:
                    rp = float(str(recent_profit).replace(",", ""))
                    yp = float(str(yoy_profit).replace(",", ""))
                    if yp > 0:
                        context["profit_growth"] = ((rp / yp) - 1) * 100
                except: pass
                
        context["source"] = "screener.in"
    except Exception as e:
        logging.error(f"Error extracting fundamental context for {symbol}: {e}")
        
    return context
