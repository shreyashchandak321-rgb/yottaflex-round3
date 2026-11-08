# Data Dictionary

Conventions: IDs are immutable and zero-padded. Dates are ISO `YYYY-MM-DD`.
`Required` means the field is never empty. All text is synthetic.

## Customer
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| customer_id | string | yes | `CUST-` + 6 digits, unique |
| full_name | string | yes | synthetic name, no real persons |
| segment | enum | yes | consumer, small_business, enterprise, prospect |
| region | string | yes | region code, e.g. IN-MH, DE-BY |
| language_pref | enum | yes | en, hi, mr, es, de, fr |
| signup_date | date | yes | before 2026-01-01 |
| status | enum | yes | active, inactive |

## Product
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| product_id | string | yes | `PROD-` + 3 digits, unique |
| product_name | string | yes | unique |
| category | enum | yes | Platform, Services, Commerce |
| launch_date | date | yes | |
| status | enum | yes | active |

## Channel
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| channel_id | string | yes | `CHAN-` + 3 digits, unique |
| channel_name | string | yes | |
| channel_type | enum | yes | digital, voice |

## Survey
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| survey_id | string | yes | `SUR-2026-` + 6 digits, unique |
| survey_name | string | yes | |
| survey_type | enum | yes | CSAT, Product Feedback |
| product_id | string | optional | FK to Product; empty = general survey |
| channel_id | string | yes | FK to Channel |
| start_date | date | yes | <= end_date |
| end_date | date | yes | last day of the survey month |
| status | enum | yes | closed |

## SurveyResponse
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| response_id | string | yes | `RESP-<survey_id>-` + zero-padded counter (3+ digits), unique |
| survey_id | string | yes | FK to Survey |
| customer_id | string | yes | FK to Customer |
| product_id | string | yes | FK to Product |
| channel_id | string | yes | FK to Channel (inherited from survey) |
| theme_id | string | yes | FK to Theme (anomalies excepted, see ground truth) |
| sentiment_label_id | string | yes | FK to SentimentLabel |
| sentiment_score | int | yes | derived: equals the label's polarity score |
| response_date | date | yes | within the survey's start/end dates |
| language | enum | yes | en, hi, mr, es, de, fr |
| text_style | enum | yes | standard, sarcastic, ambiguous, multilingual |
| text | string | yes | synthetic feedback text |
| test_label | string | optional | normally empty; a populated value is a labelled leakage anomaly and must never be used as a feature |

## Review
Same feedback fields as SurveyResponse, with `review_id` = `REV-2026-` + 6 digits
and `review_date` in 2026-01-01..2026-10-31. Reviews are not tied to a survey.

## SupportTicket (parent of SupportMessage)
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| ticket_id | string | yes | `TKT-2026-` + 6 digits, unique |
| customer_id | string | yes | FK to Customer |
| product_id | string | yes | FK to Product |
| channel_id | string | yes | FK to Channel |
| theme_id | string | yes | FK to Theme |
| opened_date | date | yes | <= every message_date on the ticket |
| status | enum | yes | open, pending, resolved; history kept in state_events |

## SupportMessage
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| message_id | string | yes | `MSG-<ticket_id>-` + 3 digits, unique |
| ticket_id | string | yes | FK to SupportTicket |
| customer_id | string | yes | FK to Customer |
| sender_type | enum | yes | customer, agent |
| theme_id | string | yes | FK to Theme |
| sentiment_label_id | string | yes | FK to SentimentLabel |
| sentiment_score | int | yes | derived from label catalogue |
| message_date | date | yes | >= ticket opened_date |
| language / text_style / text / test_label | | | as in SurveyResponse |

## Theme
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| theme_id | string | yes | `THEME-` + 6 digits, unique |
| theme_name | string | yes | the 10-theme taxonomy |
| theme_category | enum | yes | product, commercial, service, general |

## SentimentLabel
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| sentiment_label_id | string | yes | SENT-POS, SENT-NEG, SENT-NEU, SENT-MIX |
| label | enum | yes | positive, negative, neutral, mixed |
| polarity_score | int | yes | +1, -1, 0, 0 respectively |

## ActionItem (derived by src/analyze.py)
| Field | Type | Required | Allowed values / validation |
|---|---|---|---|
| action_item_id | string | yes | `ACT-` + 6 digits, unique |
| theme_id | string | yes | FK to Theme |
| theme_name | string | yes | copied from taxonomy for readability |
| title | string | yes | |
| owner_team | string | yes | mapped from theme by documented rule |
| priority_score | float | yes | derived: recent negative volume x recent negative share |
| evidence | string | yes | cites theme, counts and period (traceability) |
| status | enum | yes | open, in_progress, resolved; history in action_item_events |
| created_date | date | yes | |

## state_events / action_item_events
Append-only lifecycle history: event_id, entity reference, from_state,
to_state, event_date, reason. History is never overwritten (brief rule 4).

## ground_truth.csv / ground_truth.json
One row per deliberate anomaly: record_id, record_type, issue_type, detail.
issue_type is one of: label_contradicts_text, duplicate_response,
customer_identity_leaked, theme_outside_taxonomy, test_label_in_input.
This file is an evaluation artefact only; it is never an input feature.

## Relationships and cardinality
- Customer 1:N Review, SurveyResponse, SupportTicket, SupportMessage
- Product 1:N Review, SurveyResponse, SupportTicket; Product 1:N Survey (optional)
- Channel 1:N Review, SurveyResponse, SupportTicket, Survey
- Survey 1:N SurveyResponse
- SupportTicket 1:N SupportMessage
- Theme 1:N Review, SurveyResponse, SupportMessage, SupportTicket, ActionItem
- SentimentLabel 1:N Review, SurveyResponse, SupportMessage
- No N:M relationships exist in this domain model, so no bridge tables are
  required; if a record ever needed multiple themes, a `feedback_theme`
  bridge table (record_id, theme_id) would be the extension point.
