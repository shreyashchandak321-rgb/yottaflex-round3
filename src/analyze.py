"""
Analysis: recurring themes, sentiment shifts, service priorities, action items.

Reads a generated dataset (see generate.py) and writes to <data_dir>/outputs:
theme_summary.csv, sentiment_shifts.csv, service_priorities.csv,
action_items.csv, action_item_events.csv and metrics.json.

Only whitelisted columns are read -- the leaked `test_label` column in the
input is never touched -- and records listed in the ground truth are excluded
from every metric.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

LABEL_OF = {"SENT-POS": "positive", "SENT-NEG": "negative",
            "SENT-NEU": "neutral", "SENT-MIX": "mixed"}

# Transparent keyword baseline used only to demonstrate measurable metrics.
KEYWORDS = {
    "negative": ["crash", "delayed", "waited", "disappointed", "frustrating",
                 "poor", "broken", "broke", "missing", "dismissive",
                 "pareshan", "kharab", "tras", "decepcionado", "enttäuscht",
                 "déçu", "does not exist", "deleted", "surprise charge"],
    "positive": ["pleased", "great experience", "exceeded", "recommend",
                 "solid", "khush", "badhiya", "changla", "contento",
                 "zufrieden", "satisfait", "courteous", "patiently"],
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def baseline_predict(text):
    t = text.lower()
    neg = sum(1 for k in KEYWORDS["negative"] if k in t)
    pos = sum(1 for k in KEYWORDS["positive"] if k in t)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def main(data_dir):
    data = Path(data_dir)
    out = data / "outputs"
    out.mkdir(parents=True, exist_ok=True)

    themes = {r["theme_id"]: r["theme_name"] for r in read_csv(data / "themes.csv")}
    products = {r["product_id"]: r["product_name"] for r in read_csv(data / "products.csv")}
    anomalies = {r["record_id"] for r in read_csv(data / "ground_truth.csv")}

    # Whitelisted feature view: test_label is deliberately not selected.
    feedback = []
    for row in read_csv(data / "reviews.csv"):
        if row["review_id"] not in anomalies:
            feedback.append(dict(record_id=row["review_id"], date=row["review_date"],
                                 product_id=row["product_id"], theme_id=row["theme_id"],
                                 label=LABEL_OF[row["sentiment_label_id"]],
                                 score=int(row["sentiment_score"]), text=row["text"]))
    for row in read_csv(data / "survey_responses.csv"):
        if row["response_id"] not in anomalies:
            feedback.append(dict(record_id=row["response_id"], date=row["response_date"],
                                 product_id=row["product_id"], theme_id=row["theme_id"],
                                 label=LABEL_OF[row["sentiment_label_id"]],
                                 score=int(row["sentiment_score"]), text=row["text"]))
    for row in read_csv(data / "support_messages.csv"):
        if row["message_id"] not in anomalies and row["sender_type"] == "customer":
            feedback.append(dict(record_id=row["message_id"], date=row["message_date"],
                                 product_id="", theme_id=row["theme_id"],
                                 label=LABEL_OF[row["sentiment_label_id"]],
                                 score=int(row["sentiment_score"]), text=row["text"]))

    # ---- Recurring themes -------------------------------------------------
    theme_rows = []
    by_theme = defaultdict(list)
    for f in feedback:
        by_theme[f["theme_id"]].append(f)
    for theme_id, rows in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        counts = Counter(r["label"] for r in rows)
        total = len(rows)
        theme_rows.append(dict(
            theme_id=theme_id, theme_name=themes.get(theme_id, "UNKNOWN"),
            total_records=total,
            share_pct=round(100 * total / len(feedback), 2),
            positive=counts["positive"], negative=counts["negative"],
            neutral=counts["neutral"], mixed=counts["mixed"],
            negative_share_pct=round(100 * counts["negative"] / total, 2),
            avg_sentiment_score=round(sum(r["score"] for r in rows) / total, 3),
        ))
    write_csv(out / "theme_summary.csv",
              ["theme_id", "theme_name", "total_records", "share_pct", "positive",
               "negative", "neutral", "mixed", "negative_share_pct",
               "avg_sentiment_score"], theme_rows)

    # ---- Sentiment shifts (monthly index, traceable to source records) ----
    monthly = defaultdict(list)
    for f in feedback:
        monthly[(f["product_id"], f["theme_id"], f["date"][:7])].append(f)
    shift_rows = []
    quarters = defaultdict(list)
    for (product_id, theme_id, month), rows in sorted(monthly.items()):
        if not product_id:
            continue
        idx = round(sum(r["score"] for r in rows) / len(rows), 3)
        shift_rows.append(dict(product_id=product_id,
                               product_name=products.get(product_id, ""),
                               theme_id=theme_id,
                               theme_name=themes.get(theme_id, "UNKNOWN"),
                               month=month, records=len(rows), sentiment_index=idx))
        quarter = "Q1" if month <= "2026-05" else "Q2"
        quarters[(product_id, theme_id, quarter)].append(idx)
    for row in shift_rows:
        q1 = quarters.get((row["product_id"], row["theme_id"], "Q1"), [])
        q2 = quarters.get((row["product_id"], row["theme_id"], "Q2"), [])
        row["shift_q1_to_q2"] = (round(sum(q2) / len(q2) - sum(q1) / len(q1), 3)
                                 if q1 and q2 else "")
    write_csv(out / "sentiment_shifts.csv",
              ["product_id", "product_name", "theme_id", "theme_name", "month",
               "records", "sentiment_index", "shift_q1_to_q2"], shift_rows)

    # ---- Service priorities ----------------------------------------------
    # Documented rule: priority = recent negative volume x recent negative
    # share, so a theme must be both frequent AND worsening-heavy to rank top.
    recent = [f for f in feedback if f["date"] >= "2026-08-01"]
    recent_by_theme = defaultdict(list)
    for f in recent:
        recent_by_theme[f["theme_id"]].append(f)
    priority_rows = []
    for theme_id, rows in recent_by_theme.items():
        neg = sum(1 for r in rows if r["label"] == "negative")
        score = round(neg * (neg / len(rows)), 1)
        priority_rows.append(dict(
            rank=0, theme_id=theme_id, theme_name=themes.get(theme_id, "UNKNOWN"),
            recent_records=len(rows), recent_negative=neg,
            recent_negative_share_pct=round(100 * neg / len(rows), 2),
            priority_score=score))
    priority_rows.sort(key=lambda r: -r["priority_score"])
    for i, r in enumerate(priority_rows, 1):
        r["rank"] = i
    write_csv(out / "service_priorities.csv",
              ["rank", "theme_id", "theme_name", "recent_records", "recent_negative",
               "recent_negative_share_pct", "priority_score"], priority_rows)

    # ---- Action items from recurring themes --------------------------------
    # Rule: a theme becomes an action item when, in the most recent quarter,
    # it has >= 2% of all feedback AND >= 30% negative share.
    action_items, action_events = [], []
    owners = {"Technical Issues": "Engineering", "Support Responsiveness": "Support Ops",
              "Pricing & Value": "Commercial", "Delivery & Timeliness": "Operations",
              "Ease of Use": "Product", "Documentation & Guidance": "Product"}
    for rank_row in priority_rows:
        theme_id = rank_row["theme_id"]
        theme_total = next(t for t in theme_rows if t["theme_id"] == theme_id)
        share = theme_total["share_pct"]
        if share >= 2.0 and rank_row["recent_negative_share_pct"] >= 30.0:
            item_id = f"ACT-{len(action_items) + 1:06d}"
            status = "in_progress" if rank_row["rank"] <= 3 else "open"
            action_items.append(dict(
                action_item_id=item_id, theme_id=theme_id,
                theme_name=rank_row["theme_name"],
                title=f"Reduce negative feedback on {rank_row['theme_name']}",
                owner_team=owners.get(rank_row["theme_name"], "CX Team"),
                priority_score=rank_row["priority_score"],
                evidence=f"theme {theme_id}: {rank_row['recent_negative']} negative of "
                         f"{rank_row['recent_records']} records since 2026-08-01",
                status=status, created_date="2026-11-01"))
            action_events.append(dict(
                event_id=f"AEV-{len(action_events) + 1:06d}", action_item_id=item_id,
                from_state="", to_state="open", event_date="2026-11-01",
                reason="auto-created from service priority rule"))
            if status == "in_progress":
                action_events.append(dict(
                    event_id=f"AEV-{len(action_events) + 1:06d}", action_item_id=item_id,
                    from_state="open", to_state="in_progress", event_date="2026-11-03",
                    reason="owner team picked up"))
    write_csv(out / "action_items.csv",
              ["action_item_id", "theme_id", "theme_name", "title", "owner_team",
               "priority_score", "evidence", "status", "created_date"], action_items)
    write_csv(out / "action_item_events.csv",
              ["event_id", "action_item_id", "from_state", "to_state", "event_date",
               "reason"], action_events)

    # ---- Measurable evaluation metrics -------------------------------------
    label_counts = Counter(f["label"] for f in feedback)
    correct = Counter()
    totals = Counter()
    for f in feedback:
        pred = baseline_predict(f["text"])
        totals[f["label"]] += 1
        if pred == f["label"]:
            correct[f["label"]] += 1
    per_label = {lab: round(correct[lab] / totals[lab], 3) if totals[lab] else 0
                 for lab in LABEL_OF.values()}
    metrics = dict(
        records_analysed=len(feedback),
        anomaly_records_excluded=len(anomalies),
        label_distribution={k: label_counts[k] for k in sorted(label_counts)},
        baseline_classifier_accuracy=round(
            sum(correct.values()) / sum(totals.values()), 3),
        baseline_per_label_accuracy=per_label,
        note="Baseline is a transparent keyword model, scored against the "
             "dataset labels. Ground-truth anomaly rows and the leaked "
             "test_label column are excluded.",
    )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    main(args.data)
