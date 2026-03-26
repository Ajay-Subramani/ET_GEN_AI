from __future__ import annotations

import streamlit as st

from app.config import get_settings
from app.graph import run_recommendation
from app.repository import Repository


st.set_page_config(page_title="AI Investor Agent", page_icon="Rs", layout="wide")

settings = get_settings()
repo = Repository()

st.title("AI Investor Agent")
st.caption("Autonomous buy-side analyst for Indian retail investors")

left, right = st.columns([1, 2])

with left:
    symbol = st.text_input("Symbol", value=settings.default_symbol)
    user_id = st.selectbox(
        "Demo User",
        options=["demo_moderate", "demo_aggressive"],
        index=0 if settings.default_user_id == "demo_moderate" else 1,
    )
    run = st.button("Run Autonomous Analysis", type="primary")
    user_data = repo.get_user_portfolio(user_id)
    st.subheader("Portfolio Context")
    st.json(user_data)

with right:
    if run:
        recommendation = run_recommendation(symbol, user_id)
        st.subheader(recommendation.summary)

        metric_cols = st.columns(4)
        metric_cols[0].metric("Action", recommendation.action)
        metric_cols[1].metric("Confidence", f"{recommendation.confidence_pct:.1f}%")
        metric_cols[2].metric("Entry", f"Rs {recommendation.entry_price:.2f}")
        metric_cols[3].metric("Target", f"Rs {recommendation.target_price:.2f}")

        metric_cols = st.columns(3)
        metric_cols[0].metric("Stop Loss", f"Rs {recommendation.stop_loss:.2f}")
        metric_cols[1].metric("Conviction", recommendation.conviction_mode.replace("_", " "))
        metric_cols[2].metric("Allocation", f"{recommendation.allocation_pct:.1f}%")

        metric_cols = st.columns(2)
        metric_cols[0].metric("Capital", f"Rs {recommendation.allocation_amount:,.0f}")
        metric_cols[1].metric("Sector Exposure", f"{recommendation.sector_exposure_pct:.1f}%")

        st.markdown("### Reasoning")
        st.write(recommendation.reasoning)
        st.info(recommendation.confidence_note)

        st.markdown("### Analyst Note")
        st.write(recommendation.analyst_note)

        st.markdown("### Pattern Memory")
        st.json(recommendation.setup_memory.model_dump())

        if recommendation.personalization_warning:
            st.warning(recommendation.personalization_warning)

        st.markdown("### Next Step")
        st.write(recommendation.next_step)

        st.markdown("### What To Watch Next")
        st.write(recommendation.watch_next)

        st.markdown("### Confirmation Triggers")
        st.write(recommendation.confirmation_triggers)

        st.markdown("### Invalidation Triggers")
        st.write(recommendation.invalidation_triggers)

        st.markdown("### Data Sources")
        st.json(recommendation.sources)
    else:
        st.info("Run the flow to generate a portfolio-aware decision.")
