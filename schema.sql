-- Schema for the feedback-intelligence dataset (SQLite / standard SQL).
-- Load order respects foreign keys: master data first, then transactions.
-- CSV exports in data/<scale>/ map 1:1 onto these tables.

CREATE TABLE products (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    category     TEXT NOT NULL CHECK (category IN ('Platform','Services','Commerce')),
    launch_date  DATE NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE channels (
    channel_id   TEXT PRIMARY KEY,
    channel_name TEXT NOT NULL,
    channel_type TEXT NOT NULL CHECK (channel_type IN ('digital','voice'))
);

CREATE TABLE themes (
    theme_id       TEXT PRIMARY KEY,
    theme_name     TEXT NOT NULL UNIQUE,
    theme_category TEXT NOT NULL CHECK (theme_category IN ('product','commercial','service','general'))
);

CREATE TABLE sentiment_labels (
    sentiment_label_id TEXT PRIMARY KEY,
    label              TEXT NOT NULL CHECK (label IN ('positive','negative','neutral','mixed')),
    polarity_score     INTEGER NOT NULL
);

CREATE TABLE customers (
    customer_id   TEXT PRIMARY KEY,
    full_name     TEXT NOT NULL,
    segment       TEXT NOT NULL CHECK (segment IN ('consumer','small_business','enterprise','prospect')),
    region        TEXT NOT NULL,
    language_pref TEXT NOT NULL,
    signup_date   DATE NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('active','inactive'))
);

CREATE TABLE surveys (
    survey_id   TEXT PRIMARY KEY,
    survey_name TEXT NOT NULL,
    survey_type TEXT NOT NULL CHECK (survey_type IN ('CSAT','Product Feedback')),
    product_id  TEXT REFERENCES products(product_id),  -- optional relationship
    channel_id  TEXT NOT NULL REFERENCES channels(channel_id),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL CHECK (end_date >= start_date),
    status      TEXT NOT NULL DEFAULT 'closed'
);

CREATE TABLE survey_responses (
    response_id        TEXT PRIMARY KEY,
    survey_id          TEXT NOT NULL REFERENCES surveys(survey_id),
    customer_id        TEXT NOT NULL REFERENCES customers(customer_id),
    product_id         TEXT NOT NULL REFERENCES products(product_id),
    channel_id         TEXT NOT NULL REFERENCES channels(channel_id),
    theme_id           TEXT NOT NULL REFERENCES themes(theme_id),
    sentiment_label_id TEXT NOT NULL REFERENCES sentiment_labels(sentiment_label_id),
    sentiment_score    INTEGER NOT NULL,
    response_date      DATE NOT NULL,
    language           TEXT NOT NULL,
    text_style         TEXT NOT NULL,
    text               TEXT NOT NULL,
    test_label         TEXT  -- must stay empty; populated = labelled leakage anomaly
);

CREATE TABLE reviews (
    review_id          TEXT PRIMARY KEY,
    customer_id        TEXT NOT NULL REFERENCES customers(customer_id),
    product_id         TEXT NOT NULL REFERENCES products(product_id),
    channel_id         TEXT NOT NULL REFERENCES channels(channel_id),
    theme_id           TEXT NOT NULL REFERENCES themes(theme_id),
    sentiment_label_id TEXT NOT NULL REFERENCES sentiment_labels(sentiment_label_id),
    sentiment_score    INTEGER NOT NULL,
    review_date        DATE NOT NULL,
    language           TEXT NOT NULL,
    text_style         TEXT NOT NULL,
    text               TEXT NOT NULL,
    test_label         TEXT
);

CREATE TABLE support_tickets (
    ticket_id   TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    product_id  TEXT NOT NULL REFERENCES products(product_id),
    channel_id  TEXT NOT NULL REFERENCES channels(channel_id),
    theme_id    TEXT NOT NULL REFERENCES themes(theme_id),
    opened_date DATE NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('open','pending','resolved'))
);

CREATE TABLE support_messages (
    message_id         TEXT PRIMARY KEY,
    ticket_id          TEXT NOT NULL REFERENCES support_tickets(ticket_id),
    customer_id        TEXT NOT NULL REFERENCES customers(customer_id),
    sender_type        TEXT NOT NULL CHECK (sender_type IN ('customer','agent')),
    theme_id           TEXT NOT NULL REFERENCES themes(theme_id),
    sentiment_label_id TEXT NOT NULL REFERENCES sentiment_labels(sentiment_label_id),
    sentiment_score    INTEGER NOT NULL,
    message_date       DATE NOT NULL,
    language           TEXT NOT NULL,
    text_style         TEXT NOT NULL,
    text               TEXT NOT NULL,
    test_label         TEXT
);

CREATE TABLE state_events (
    event_id    TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    from_state  TEXT,
    to_state    TEXT NOT NULL,
    event_date  DATE NOT NULL,
    reason      TEXT NOT NULL
);

CREATE TABLE action_items (
    action_item_id TEXT PRIMARY KEY,
    theme_id       TEXT NOT NULL REFERENCES themes(theme_id),
    theme_name     TEXT NOT NULL,
    title          TEXT NOT NULL,
    owner_team     TEXT NOT NULL,
    priority_score REAL NOT NULL,
    evidence       TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('open','in_progress','resolved')),
    created_date   DATE NOT NULL
);
