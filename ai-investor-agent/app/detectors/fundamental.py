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
        def _to_float(val):
            if val is None: return None
            try:
                # Remove currency symbols and commas
                clean_val = str(val).replace(",", "").replace("Rs.", "").replace("%", "").strip()
                if not clean_val or clean_val == "nan": return None
                return float(clean_val)
            except:
                return None

        context["pe_ratio"] = _to_float(summary.get("stock_pe"))
        context["roce"] = _to_float(summary.get("roce"))
        context["roe"] = _to_float(summary.get("roe"))
        context["debt_to_equity"] = _to_float(summary.get("debt_to_equity"))
            
        quarterly = data.get("quarterly")
        if quarterly is not None and not quarterly.empty:
            if "OPM %" in quarterly.index or "OPM" in quarterly.index:
                opm_key = "OPM %" if "OPM %" in quarterly.index else "OPM"
                context["operating_margin"] = _to_float(quarterly.loc[opm_key].iloc[-1])
                    
            if "Sales" in quarterly.index and quarterly.shape[1] >= 5:
                rs = _to_float(quarterly.loc["Sales"].iloc[-1])
                ys = _to_float(quarterly.loc["Sales"].iloc[-5]) 
                if rs is not None and ys is not None and ys > 0:
                    context["revenue_growth"] = round(((rs / ys) - 1) * 100, 2)
                
            if "Net Profit" in quarterly.index and quarterly.shape[1] >= 5:
                rp = _to_float(quarterly.loc["Net Profit"].iloc[-1])
                yp = _to_float(quarterly.loc["Net Profit"].iloc[-5]) 
                if rp is not None and yp is not None and yp > 0:
                    context["profit_growth"] = round(((rp / yp) - 1) * 100, 2)
                
        context["source"] = "screener.in"
    except Exception as e:
        logging.error(f"Error extracting fundamental context for {symbol}: {e}")
        
    return context
