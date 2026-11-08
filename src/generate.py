"""
Generates the synthetic dataset: master data, then feedback and support
records, then the labelled anomalies. See README.md for the full picture.

Deterministic IDs, fixed seed (default 20261022), and a --scale switch so the
starter and full datasets come from the same code path.
"""

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

import textgen

# --------------------------------------------------------------------------
# Reference / master data (created first; everything else points at it)
# --------------------------------------------------------------------------

PRODUCTS = [
    # (id, name, category, launch date)
    ("PROD-001", "Analytics Dashboard", "Platform", "2024-03-01"),
    ("PROD-002", "Mobile App", "Platform", "2023-11-15"),
    ("PROD-003", "API Service", "Platform", "2024-06-01"),
    ("PROD-004", "Onboarding Service", "Services", "2024-01-20"),
    ("PROD-005", "Support Desk", "Services", "2023-09-01"),
    ("PROD-006", "Training Program", "Services", "2025-02-10"),
    ("PROD-007", "Billing & Payments", "Commerce", "2023-08-05"),
    ("PROD-008", "Subscription Plans", "Commerce", "2024-09-12"),
    ("PROD-009", "Marketplace", "Commerce", "2025-05-01"),
    ("PROD-010", "Loyalty Program", "Commerce", "2025-08-18"),
]

CHANNELS = [
    ("CHAN-001", "Web Portal", "digital"),
    ("CHAN-002", "Mobile App", "digital"),
    ("CHAN-003", "Email", "digital"),
    ("CHAN-004", "Phone", "voice"),
    ("CHAN-005", "Social Media", "digital"),
    ("CHAN-006", "In-App Chat", "digital"),
]

THEMES = [
    ("THEME-000001", "Product Quality", "product"),
    ("THEME-000002", "Pricing & Value", "commercial"),
    ("THEME-000003", "Support Responsiveness", "service"),
    ("THEME-000004", "Ease of Use", "product"),
    ("THEME-000005", "Delivery & Timeliness", "service"),
    ("THEME-000006", "Staff Professionalism", "service"),
    ("THEME-000007", "Technical Issues", "product"),
    ("THEME-000008", "Documentation & Guidance", "product"),
    ("THEME-000009", "Feature Requests", "product"),
    ("THEME-000010", "Overall Satisfaction", "general"),
]
THEME_NAME = {tid: name for tid, name, _ in THEMES}

SENTIMENTS = [
    # (id, label, polarity score) -- polarity is the derived-value source
    ("SENT-POS", "positive", 1),
    ("SENT-NEG", "negative", -1),
    ("SENT-NEU", "neutral", 0),
    ("SENT-MIX", "mixed", 0),
]
SENTIMENT_ID = {label: sid for sid, label, _ in SENTIMENTS}
SENTIMENT_SCORE = {sid: score for sid, _, score in SENTIMENTS}

FIRST_NAMES = ["Aarav", "Priya", "Rohan", "Sneha", "Vikram", "Ananya", "Kiran",
               "Meera", "Arjun", "Divya", "Rahul", "Ishita", "Nikhil", "Pooja",
               "Sanjay", "Kavita", "Manoj", "Rekha", "Aditya", "Shreya",
               "Lukas", "Emma", "Mateo", "Sofia", "Jonas", "Camille"]
LAST_NAMES = ["Sharma", "Patel", "Khan", "Iyer", "Reddy", "Nair", "Gupta",
              "Kulkarni", "Singh", "Das", "Weber", "Garcia", "Muller",
              "Dubois", "Rossi", "Joshi", "Menon", "Rao", "Verma", "Kaur"]
REGIONS = ["IN-MH", "IN-KA", "IN-DL", "IN-TN", "IN-TS", "DE-BY", "ES-MD", "FR-IDF"]
SEGMENTS = ["consumer", "small_business", "enterprise", "prospect"]

SCALES = {
    # starter and full run the identical generator; only volumes differ
    "starter": dict(customers=200, reviews=300, responses=200, messages=240,
                    anomalies=dict(contradiction=4, duplicate=3, pii=3,
                                   outside_theme=2, leakage=3)),
    "full": dict(customers=5000, reviews=30000, responses=20000, messages=20000,
                 anomalies=dict(contradiction=150, duplicate=120, pii=100,
                                outside_theme=80, leakage=100)),
}

START = date(2026, 1, 1)
END = date(2026, 10, 31)

# --------------------------------------------------------------------------
# Sampling model (documented rules, not independent random outcomes)
# --------------------------------------------------------------------------

BASE_THEME_WEIGHTS = {
    "Platform": [14, 8, 10, 14, 4, 4, 16, 10, 10, 10],
    "Services": [8, 8, 20, 8, 14, 14, 4, 8, 4, 12],
    "Commerce": [10, 18, 10, 10, 12, 6, 6, 4, 6, 18],
}

# Sentiment distribution conditional on theme: (pos, neg, neu, mix).
# Chosen so the overall label mix stays broadly balanced, as required.
THEME_SENTIMENT = {
    "Product Quality": (0.55, 0.20, 0.15, 0.10),
    "Pricing & Value": (0.25, 0.45, 0.15, 0.15),
    "Support Responsiveness": (0.45, 0.35, 0.10, 0.10),
    "Ease of Use": (0.40, 0.35, 0.15, 0.10),
    "Delivery & Timeliness": (0.40, 0.40, 0.10, 0.10),
    "Staff Professionalism": (0.55, 0.25, 0.10, 0.10),
    "Technical Issues": (0.10, 0.65, 0.10, 0.15),
    "Documentation & Guidance": (0.40, 0.30, 0.20, 0.10),
    "Feature Requests": (0.30, 0.20, 0.35, 0.15),
    "Overall Satisfaction": (0.55, 0.20, 0.15, 0.10),
}
SENTIMENT_ORDER = ["positive", "negative", "neutral", "mixed"]


def theme_weights(product_category, product_id, on_date):
    """Theme weights with the two documented trend events applied.

    Event A: PROD-002 (Mobile App) shipped a faulty update on 2026-03-15;
    Technical Issues feedback surges Mar-May 2026 and then recovers.
    Event B: a support improvement programme starts 2026-07-01; negative
    Support Responsiveness feedback declines from July onwards (applied in
    sentiment_for(), which reads the same event dates).
    """
    weights = list(BASE_THEME_WEIGHTS[product_category])
    tech_idx = 6  # Technical Issues position in THEMES
    if product_id == "PROD-002" and date(2026, 3, 15) <= on_date <= date(2026, 5, 31):
        weights[tech_idx] *= 3
    return weights


def sentiment_for(rng, theme, on_date):
    """Sample a sentiment label from the documented conditional model."""
    probs = list(THEME_SENTIMENT[theme])
    # Event B: from July 2026 support responsiveness improves.
    if theme == "Support Responsiveness" and on_date >= date(2026, 7, 1):
        probs = [0.60, 0.20, 0.10, 0.10]
    # Event A fallout: during the Mobile App incident window, technical
    # feedback is more negative than the theme baseline.
    if theme == "Technical Issues" and date(2026, 3, 15) <= on_date <= date(2026, 5, 31):
        probs = [0.05, 0.75, 0.08, 0.12]
    return rng.choices(SENTIMENT_ORDER, weights=probs)[0]


def random_date(rng):
    """A date in Jan-Oct 2026, mildly weighted towards recent months."""
    span = (END - START).days
    # sqrt skews the uniform draw towards the end of the window
    offset = int(span * (rng.random() ** 0.8))
    return START + timedelta(days=offset)


# --------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------

def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------------------------------
# Main generation pipeline
# --------------------------------------------------------------------------

def generate(scale_name, out_dir, seed=20261022):
    cfg = SCALES[scale_name]
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ground_truth = []   # anomalies only; never part of the input features
    state_events = []   # lifecycle history (brief rule 4: never overwrite)

    # ---- Step 1/2: master data first -------------------------------------
    products = [dict(product_id=p, product_name=n, category=c, launch_date=d,
                     status="active") for p, n, c, d in PRODUCTS]
    channels = [dict(channel_id=c, channel_name=n, channel_type=t)
                for c, n, t in CHANNELS]
    themes = [dict(theme_id=t, theme_name=n, theme_category=c) for t, n, c in THEMES]
    sentiment_labels = [dict(sentiment_label_id=s, label=l, polarity_score=v)
                        for s, l, v in SENTIMENTS]

    customers = []
    for i in range(1, cfg["customers"] + 1):
        signup = START - timedelta(days=rng.randint(30, 900))
        customers.append(dict(
            customer_id=f"CUST-{i:06d}",
            full_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            segment=rng.choice(SEGMENTS),
            region=rng.choice(REGIONS),
            language_pref=rng.choice(["en", "en", "en", "hi", "mr", "es", "de", "fr"]),
            signup_date=signup.isoformat(),
            status=rng.choices(["active", "inactive"], weights=[92, 8])[0],
        ))

    surveys = []
    survey_no = 0
    for month in range(1, 11):  # monthly survey waves, Jan-Oct 2026
        for wave, (stype, prod) in enumerate(
                [("CSAT", None), ("Product Feedback", PRODUCTS[month % len(PRODUCTS)][0])]):
            survey_no += 1
            start = date(2026, month, 1)
            from calendar import monthrange
            end = date(2026, month, monthrange(2026, month)[1])
            surveys.append(dict(
                survey_id=f"SUR-{2026}-{survey_no:06d}",
                survey_name=f"{stype} Wave {month:02d}-2026" + (f" ({prod})" if prod else ""),
                survey_type=stype,
                product_id=prod or "",
                channel_id=CHANNELS[(month + wave) % len(CHANNELS)][0],
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                status="closed",
            ))

    product_by_id = {p["product_id"]: p for p in products}
    survey_ids = [s["survey_id"] for s in surveys]

    def pick_feedback_fields(on_date):
        product = rng.choice(products)
        weights = theme_weights(product["category"], product["product_id"], on_date)
        theme_id = rng.choices([t[0] for t in THEMES], weights=weights)[0]
        theme = THEME_NAME[theme_id]
        sentiment = sentiment_for(rng, theme, on_date)
        return product, theme_id, theme, sentiment

    # ---- Step 2: feedback records (reviews + survey responses) -----------
    reviews = []
    for i in range(1, cfg["reviews"] + 1):
        on_date = random_date(rng)
        product, theme_id, theme, sentiment = pick_feedback_fields(on_date)
        text, lang, style = textgen.compose_feedback_text(
            rng, product["product_name"], theme, sentiment)
        review_id = f"REV-2026-{i:06d}"
        reviews.append(dict(
            review_id=review_id,
            customer_id=rng.choice(customers)["customer_id"],
            product_id=product["product_id"],
            channel_id=rng.choice(channels)["channel_id"],
            theme_id=theme_id,
            sentiment_label_id=SENTIMENT_ID[sentiment],
            sentiment_score=SENTIMENT_SCORE[SENTIMENT_ID[sentiment]],
            review_date=on_date.isoformat(),
            language=lang,
            text_style=style,
            text=text,
            test_label="",  # leakage anomaly fills this for a few rows later
        ))

    responses = []
    resp_counters = {sid: 0 for sid in survey_ids}
    surveys_by_month = {}
    for s in surveys:
        surveys_by_month.setdefault(s["start_date"][:7], []).append(s)
    for _ in range(cfg["responses"]):
        on_date = random_date(rng)
        month_key = on_date.isoformat()[:7]
        survey = rng.choice(surveys_by_month.get(month_key, surveys))
        if survey["product_id"]:
            product = product_by_id[survey["product_id"]]
            weights = theme_weights(product["category"], product["product_id"], on_date)
            theme_id = rng.choices([t[0] for t in THEMES], weights=weights)[0]
            theme = THEME_NAME[theme_id]
            sentiment = sentiment_for(rng, theme, on_date)
        else:
            product, theme_id, theme, sentiment = pick_feedback_fields(on_date)
        text, lang, style = textgen.compose_feedback_text(
            rng, product["product_name"], theme, sentiment)
        resp_counters[survey["survey_id"]] += 1
        responses.append(dict(
            response_id=f"RESP-{survey['survey_id']}-{resp_counters[survey['survey_id']]:03d}",
            survey_id=survey["survey_id"],
            customer_id=rng.choice(customers)["customer_id"],
            product_id=product["product_id"],
            channel_id=survey["channel_id"],
            theme_id=theme_id,
            sentiment_label_id=SENTIMENT_ID[sentiment],
            sentiment_score=SENTIMENT_SCORE[SENTIMENT_ID[sentiment]],
            response_date=on_date.isoformat(),
            language=lang,
            text_style=style,
            text=text,
            test_label="",
        ))

    # ---- Step 2 (cont.): support tickets and messages --------------------
    tickets = []
    messages = []
    remaining = cfg["messages"]
    ticket_no = 0
    while remaining > 0:
        ticket_no += 1
        ticket_id = f"TKT-2026-{ticket_no:06d}"
        opened = random_date(rng)
        product, theme_id, theme, sentiment = pick_feedback_fields(opened)
        customer = rng.choice(customers)
        n_msgs = min(remaining, rng.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0])
        status = rng.choices(["resolved", "pending", "open"], weights=[65, 20, 15])[0]
        tickets.append(dict(
            ticket_id=ticket_id, customer_id=customer["customer_id"],
            product_id=product["product_id"],
            channel_id=rng.choice(channels)["channel_id"],
            theme_id=theme_id, opened_date=opened.isoformat(), status=status,
        ))
        state_events.append(dict(
            event_id=f"EVT-{len(state_events) + 1:07d}", entity_type="SupportTicket",
            entity_id=ticket_id, from_state="", to_state="open",
            event_date=opened.isoformat(), reason="ticket_created"))
        if status != "open":
            state_events.append(dict(
                event_id=f"EVT-{len(state_events) + 1:07d}", entity_type="SupportTicket",
                entity_id=ticket_id, from_state="open", to_state=status,
                event_date=(opened + timedelta(days=rng.randint(0, 5))).isoformat(),
                reason="agent_update"))
        for m in range(1, n_msgs + 1):
            msg_date = opened + timedelta(days=rng.randint(0, 4))
            if msg_date > END:
                msg_date = END
            if m % 2 == 1:
                text, lang, style = textgen.compose_support_text(
                    rng, product["product_name"], theme, sentiment)
                sender = "customer"
                msg_sentiment = sentiment
            else:
                text = rng.choice(textgen.AGENT_REPLIES)
                sender = "agent"
                lang, style, msg_sentiment = "en", "standard", "neutral"
            messages.append(dict(
                message_id=f"MSG-{ticket_id}-{m:03d}",
                ticket_id=ticket_id,
                customer_id=customer["customer_id"],
                sender_type=sender,
                theme_id=theme_id,
                sentiment_label_id=SENTIMENT_ID[msg_sentiment],
                sentiment_score=SENTIMENT_SCORE[SENTIMENT_ID[msg_sentiment]],
                message_date=msg_date.isoformat(),
                language=lang,
                text_style=style,
                text=text,
                test_label="",
            ))
        remaining -= n_msgs

    # ---- Step 5: labelled anomalies (ground truth) ------------------------
    anom = cfg["anomalies"]

    # (a) Label contradicts text, without explanation.
    for row in rng.sample(reviews, anom["contradiction"]):
        original = row["sentiment_label_id"]
        row["sentiment_label_id"] = "SENT-NEG" if original == "SENT-POS" else "SENT-POS"
        row["sentiment_score"] = SENTIMENT_SCORE[row["sentiment_label_id"]]
        ground_truth.append(dict(record_id=row["review_id"], record_type="Review",
                                 issue_type="label_contradicts_text",
                                 detail=f"label flipped from {original} to {row['sentiment_label_id']}"))

    # (b) Duplicate response: exact copy of an existing response, new ID.
    for row in rng.sample(responses, anom["duplicate"]):
        resp_counters[row["survey_id"]] += 1
        dup = dict(row)
        dup["response_id"] = f"RESP-{row['survey_id']}-{resp_counters[row['survey_id']]:03d}"
        responses.append(dup)
        ground_truth.append(dict(record_id=dup["response_id"], record_type="SurveyResponse",
                                 issue_type="duplicate_response",
                                 detail=f"exact duplicate of {row['response_id']}"))

    # (c) Customer identity leaked inside support text (synthetic PII only).
    customer_msgs = [m for m in messages if m["sender_type"] == "customer"]
    for row in rng.sample(customer_msgs, anom["pii"]):
        fake = rng.choice([
            "You can reach me at amit.verma@examplemail.com.",
            "My number is 98110 24680, please call back.",
            "Please reply to s.khan@examplemail.com directly.",
            "My alternate number is 98200 13579.",
        ])
        row["text"] = row["text"] + " " + fake
        ground_truth.append(dict(record_id=row["message_id"], record_type="SupportMessage",
                                 issue_type="customer_identity_leaked",
                                 detail="synthetic email/phone embedded in message text"))

    # (d) Theme assigned outside the taxonomy.
    for k in range(anom["outside_theme"]):
        on_date = random_date(rng)
        product = rng.choice(products)
        sentiment = rng.choice(SENTIMENT_ORDER)
        text, lang, style = textgen.compose_feedback_text(
            rng, product["product_name"], "Overall Satisfaction", sentiment)
        review_id = f"REV-2026-{len(reviews) + 1:06d}"
        reviews.append(dict(
            review_id=review_id,
            customer_id=rng.choice(customers)["customer_id"],
            product_id=product["product_id"],
            channel_id=rng.choice(channels)["channel_id"],
            theme_id="THEME-999999",  # deliberately not in themes.csv
            sentiment_label_id=SENTIMENT_ID[sentiment],
            sentiment_score=SENTIMENT_SCORE[SENTIMENT_ID[sentiment]],
            review_date=on_date.isoformat(), language=lang, text_style=style,
            text=text, test_label="",
        ))
        ground_truth.append(dict(record_id=review_id, record_type="Review",
                                 issue_type="theme_outside_taxonomy",
                                 detail="theme_id THEME-999999 not present in theme taxonomy"))

    # (e) Test labels leaked into model input features.
    label_name = {sid: lab for sid, lab, _ in SENTIMENTS}
    for row in rng.sample(reviews + responses, anom["leakage"]):
        row["test_label"] = label_name[row["sentiment_label_id"]]
        rid = row.get("review_id") or row.get("response_id")
        ground_truth.append(dict(record_id=rid, record_type="Feedback",
                                 issue_type="test_label_in_input",
                                 detail="test_label column populated; must be excluded from features"))

    # ---- Step 9: exports ---------------------------------------------------
    write_csv(out / "products.csv",
              ["product_id", "product_name", "category", "launch_date", "status"], products)
    write_csv(out / "channels.csv", ["channel_id", "channel_name", "channel_type"], channels)
    write_csv(out / "themes.csv", ["theme_id", "theme_name", "theme_category"], themes)
    write_csv(out / "sentiment_labels.csv",
              ["sentiment_label_id", "label", "polarity_score"], sentiment_labels)
    write_csv(out / "customers.csv",
              ["customer_id", "full_name", "segment", "region", "language_pref",
               "signup_date", "status"], customers)
    write_csv(out / "surveys.csv",
              ["survey_id", "survey_name", "survey_type", "product_id", "channel_id",
               "start_date", "end_date", "status"], surveys)
    write_csv(out / "survey_responses.csv",
              ["response_id", "survey_id", "customer_id", "product_id", "channel_id",
               "theme_id", "sentiment_label_id", "sentiment_score", "response_date",
               "language", "text_style", "text", "test_label"], responses)
    write_csv(out / "reviews.csv",
              ["review_id", "customer_id", "product_id", "channel_id", "theme_id",
               "sentiment_label_id", "sentiment_score", "review_date", "language",
               "text_style", "text", "test_label"], reviews)
    write_csv(out / "support_tickets.csv",
              ["ticket_id", "customer_id", "product_id", "channel_id", "theme_id",
               "opened_date", "status"], tickets)
    write_csv(out / "support_messages.csv",
              ["message_id", "ticket_id", "customer_id", "sender_type", "theme_id",
               "sentiment_label_id", "sentiment_score", "message_date", "language",
               "text_style", "text", "test_label"], messages)
    write_csv(out / "state_events.csv",
              ["event_id", "entity_type", "entity_id", "from_state", "to_state",
               "event_date", "reason"], state_events)
    write_csv(out / "ground_truth.csv",
              ["record_id", "record_type", "issue_type", "detail"], ground_truth)
    (out / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2),
                                           encoding="utf-8")

    manifest = dict(scale=scale_name, seed=seed,
                    counts=dict(customers=len(customers), surveys=len(surveys),
                                reviews=len(reviews), survey_responses=len(responses),
                                support_tickets=len(tickets),
                                support_messages=len(messages),
                                ground_truth_anomalies=len(ground_truth)),
                    feedback_total=len(reviews) + len(responses),
                    provenance="100% synthetic, generated by src/generate.py; "
                               "no external or personal data used")
    (out / "source_manifest.json").write_text(json.dumps(manifest, indent=2),
                                              encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", choices=list(SCALES), default="full")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=20261022)
    args = parser.parse_args()
    result = generate(args.scale, args.out, args.seed)
    print(json.dumps(result, indent=2))
