insert into stocks (symbol, name, sector, market_cap, is_fno) values
('TATASTEEL', 'Tata Steel Ltd', 'Metals', 204000, true),
('RELIANCE', 'Reliance Industries Ltd', 'Energy', 1900000, true),
('HDFCBANK', 'HDFC Bank Ltd', 'Financials', 1350000, true),
('INFY', 'Infosys Ltd', 'Information Technology', 720000, true),
('SUNPHARMA', 'Sun Pharmaceutical Industries Ltd', 'Healthcare', 410000, true)
on conflict (symbol) do nothing;

insert into bulk_deals (symbol, deal_date, buyer, quantity, price) values
('TATASTEEL', current_date - interval '1 day', 'Demo Institutional Fund', 1250000, 132.40)
on conflict do nothing;

insert into pattern_success_rates (
  symbol, pattern_name, total_occurrences, successful_occurrences, success_rate, avg_return_pct
) values
('TATASTEEL', 'breakout', 12, 9, 0.72, 8.5),
('TATASTEEL', 'support_bounce', 16, 10, 0.63, 5.4),
('RELIANCE', 'breakout', 14, 9, 0.64, 6.2),
('HDFCBANK', 'support_bounce', 18, 13, 0.72, 4.1)
on conflict do nothing;

insert into user_portfolios (user_id, holdings, risk_profile, total_capital) values
(
  'demo_moderate',
  '[{"symbol":"TATASTEEL","quantity":400,"avg_price":146.0,"sector":"Metals"},{"symbol":"JSWSTEEL","quantity":220,"avg_price":885.0,"sector":"Metals"},{"symbol":"HDFCBANK","quantity":80,"avg_price":1585.0,"sector":"Financials"}]'::jsonb,
  'moderate',
  1000000
),
(
  'demo_aggressive',
  '[{"symbol":"RELIANCE","quantity":90,"avg_price":2840.0,"sector":"Energy"},{"symbol":"INFY","quantity":120,"avg_price":1650.0,"sector":"Information Technology"}]'::jsonb,
  'aggressive',
  2500000
)
on conflict (user_id) do nothing;

insert into recommendation_outcomes (
  user_id, symbol, pattern_name, action, market_condition, signal_stack,
  entry_price, target_price, stop_loss, outcome_return_pct, outcome_horizon_days, outcome_label
) values
(
  'demo_moderate', 'TATASTEEL', 'breakout', 'BUY', 'risk_on',
  '["bulk_deal","delivery_spike","oi_buildup","pattern_start"]'::jsonb,
  132.5, 148.0, 125.0, 12.4, 18, 'win'
),
(
  'demo_aggressive', 'TATASTEEL', 'breakout', 'BUY', 'risk_on',
  '["bulk_deal","volume_breakout","pattern_start"]'::jsonb,
  130.0, 146.0, 123.0, 9.1, 12, 'win'
),
(
  'demo_moderate', 'TATASTEEL', 'breakout', 'WATCH', 'risk_on',
  '["delivery_spike","pattern_start"]'::jsonb,
  128.0, 140.0, 121.0, -4.3, 9, 'loss'
)
on conflict do nothing;
