"""Generate scripts/sample_marketing.csv — 90 days x 5 campaigns of Meta-ads-like data."""
import csv
import datetime
import os
import random

random.seed(42)
campaigns = ["Summer Sale", "Retargeting", "Prospecting", "Brand Awareness", "Holiday Push"]
countries = ["US", "DE", "FR", "UK", "CA"]
devices = ["mobile", "desktop", "tablet"]
roas_target = {
    "Summer Sale": 4.2, "Retargeting": 5.1, "Prospecting": 1.8,
    "Brand Awareness": 1.2, "Holiday Push": 3.6,
}
base_spend = {
    "Summer Sale": 180, "Retargeting": 90, "Prospecting": 250,
    "Brand Awareness": 300, "Holiday Push": 140,
}

start = datetime.date(2025, 1, 1)
rows = []
for d in range(90):
    day = start + datetime.timedelta(days=d)
    for c in campaigns:
        spend = round(base_spend[c] * random.uniform(0.7, 1.3), 2)
        if c == "Prospecting" and d == 45:  # injected anomaly
            spend *= 4
        revenue = round(spend * roas_target[c] * random.uniform(0.8, 1.2), 2)
        impressions = int(spend * random.uniform(180, 240))
        clicks = int(impressions * random.uniform(0.008, 0.03))
        purchases = max(0, int(clicks * random.uniform(0.02, 0.08)))
        rows.append([
            c, random.choice(countries), random.choice(devices), day.isoformat(),
            spend, revenue, impressions, clicks, purchases,
        ])

out = os.path.join(os.path.dirname(__file__), "sample_marketing.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Campaign", "Country", "Device", "Date", "Spend", "Revenue", "Impressions", "Clicks", "Purchases"])
    w.writerows(rows)
print(f"wrote {len(rows)} rows to {out}")
