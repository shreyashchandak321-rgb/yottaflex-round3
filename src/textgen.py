"""
Text composition for reviews, survey responses and support messages.

Each text is built from an opening, a theme-specific aspect phrase and a
closing, all chosen by the record's sentiment, so text and label agree unless
the generator deliberately injects a labelled anomaly (see generate.py).
A small share of records is sarcastic, ambiguous or multilingual.
"""

# Aspect phrases per theme, keyed by sentiment so the clause always agrees
# with the record's label. (For 'mixed', compose() deliberately pairs one
# positive and one negative aspect -- that is what mixed feedback means.)
ASPECTS = {
    "Product Quality": {
        "positive": ["the build quality feels solid and dependable",
                     "it has worked without a single defect so far"],
        "negative": ["the build quality feels flimsy and unreliable",
                     "defects started showing within the first month"],
        "neutral": ["the build quality is about average for this range",
                    "the quality is acceptable, nothing remarkable"],
    },
    "Pricing & Value": {
        "positive": ["the price feels fair for what is included",
                     "it is cheaper than the alternatives I compared"],
        "negative": ["the recent price change is hard to justify",
                     "the plan costs more than similar options"],
        "neutral": ["the price is in line with market rates",
                    "the pricing is neither cheap nor expensive"],
    },
    "Support Responsiveness": {
        "positive": ["the support team replied within an hour",
                     "the agent followed up until the issue was closed"],
        "negative": ["I waited three days for a simple answer from support",
                     "my ticket was closed without any resolution"],
        "neutral": ["support replied after a day, which was acceptable",
                    "the response time was average"],
    },
    "Ease of Use": {
        "positive": ["the interface is intuitive even for a first-time user",
                     "everyday tasks take only a couple of clicks"],
        "negative": ["simple tasks take far too many steps",
                     "the navigation is confusing and poorly labelled"],
        "neutral": ["the interface takes some getting used to",
                    "most tasks are straightforward once you learn the layout"],
    },
    "Delivery & Timeliness": {
        "positive": ["everything arrived exactly on the promised date",
                     "it was delivered a day earlier than promised"],
        "negative": ["the delivery was delayed twice without any update",
                     "the schedule slipped by a full week"],
        "neutral": ["the delivery took the usual time",
                    "it arrived on the last day of the promised window"],
    },
    "Staff Professionalism": {
        "positive": ["the staff were courteous and well informed",
                     "the team explained every step patiently"],
        "negative": ["the representative was dismissive and rushed",
                     "the staff could not answer basic questions"],
        "neutral": ["the staff were polite enough",
                    "the interaction was professional and brief"],
    },
    "Technical Issues": {
        "positive": ["it has been stable with no crashes at all",
                     "the recent update fixed the glitches I had"],
        "negative": ["the app crashes whenever I open the reports section",
                     "sync fails silently and data goes missing"],
        "neutral": ["there are occasional minor glitches",
                    "one small bug appears now and then"],
    },
    "Documentation & Guidance": {
        "positive": ["the help articles answered my question completely",
                     "the onboarding guide was clear and easy to follow"],
        "negative": ["the documentation is outdated and missing key steps",
                     "the guide does not match the current version at all"],
        "neutral": ["the documentation covers the basics",
                    "some guides are helpful, others are thin"],
    },
    "Feature Requests": {
        "positive": ["the new features in the last release are genuinely useful",
                     "the feature set already covers everything my team needs"],
        "negative": ["basic features I expected are still missing",
                     "promised features keep getting postponed"],
        "neutral": ["an export option would make this more useful",
                    "dark mode is the one thing I would add"],
    },
    "Overall Satisfaction": {
        "positive": ["overall I am happy and would recommend it to others",
                     "overall it has been a very good experience"],
        "negative": ["overall I would not choose this again",
                     "overall the experience has been disappointing"],
        "neutral": ["overall it does the job but nothing stands out",
                    "overall my experience has been average"],
    },
}

OPENINGS = {
    "positive": [
        "Really pleased with {product}.",
        "Great experience with {product} so far.",
        "Honestly, {product} exceeded my expectations.",
        "Solid experience overall with {product}.",
    ],
    "negative": [
        "Disappointed with {product}.",
        "Frustrating experience with {product}.",
        "Not happy with {product} at all.",
        "This has been a poor experience with {product}.",
    ],
    "neutral": [
        "Sharing my experience with {product}.",
        "A few notes on {product} after a month of use.",
        "My take on {product}, for what it is worth.",
        "Reviewing {product} after regular use.",
    ],
    "mixed": [
        "Mixed feelings about {product}.",
        "There is a lot to like about {product}, but also real problems.",
        "Partly satisfied with {product}, partly not.",
        "{product} gets some things right and some things wrong.",
    ],
}

CLOSINGS = {
    "positive": [
        "Would happily recommend it.",
        "Keep up the good work.",
        "Five stars from me.",
        "I plan to continue using it.",
    ],
    "negative": [
        "I am considering switching to an alternative.",
        "This needs urgent attention.",
        "I expected much better.",
        "Not worth it in its current state.",
    ],
    "neutral": [
        "It is acceptable for the price.",
        "Nothing more to add at this point.",
        "I will update this review after longer use.",
        "It meets the basic requirement.",
    ],
    "mixed": [
        "Worth trying, but go in with realistic expectations.",
        "Good in parts, disappointing in others.",
        "I will give it another month before deciding.",
        "Depends on what you need it for.",
    ],
}

# Sarcastic texts: surface wording is positive, meaning is negative.
# These are always labelled negative, and flagged text_style='sarcastic'.
SARCASTIC = [
    "Wonderful, {product} crashed again right before my deadline. Exactly what I needed.",
    "Brilliant update, it deleted my saved work. Ten out of ten, truly.",
    "Love waiting four days for a one-line reply from support. Fantastic service.",
    "Great, another surprise charge. Just what every customer dreams of.",
    "Perfect, the feature I paid for simply does not exist anymore. Amazing.",
]

# Multilingual full-sentence templates (language, sentiment) -> templates.
# Languages: Hindi (hi), Marathi (mr), Spanish (es), German (de), French (fr).
MULTILINGUAL = {
    ("hi", "positive"): [
        "{product} bahut accha hai, main bahut khush hoon.",
        "{product} ka experience bahut badhiya raha.",
    ],
    ("hi", "negative"): [
        "{product} se main bahut pareshan hoon, support bhi jawab nahi deta.",
        "{product} bilkul kharab hai, paisa barbaad ho gaya.",
    ],
    ("hi", "neutral"): [
        "{product} theek hai, kuch khaas nahi hai.",
        "{product} ka use aasan hai lekin kuch sudhaar chahiye.",
    ],
    ("hi", "mixed"): [
        "{product} kuch mamlo mein accha hai, kuch mein kharab.",
        "{product} accha hai lekin delivery mein deri hoti hai.",
    ],
    ("mr", "positive"): [
        "{product} khoop changla ahe, mi samadhani ahe.",
        "{product} cha anubhav uttam hota.",
    ],
    ("mr", "negative"): [
        "{product} mule khoop tras zala, seva changli nahi.",
        "{product} ajibat avadle nahi.",
    ],
    ("mr", "neutral"): [
        "{product} barobar ahe, vishesh kahich nahi.",
        "{product} sadharan ahe.",
    ],
    ("mr", "mixed"): [
        "{product} kahi goshtinmadhye changla, kahi madhe kharab.",
        "{product} theek ahe pan kimat jast ahe.",
    ],
    ("es", "positive"): [
        "Estoy muy contento con {product}, funciona muy bien.",
        "{product} superó mis expectativas, lo recomiendo.",
    ],
    ("es", "negative"): [
        "Muy decepcionado con {product}, el soporte no responde.",
        "{product} funciona mal y nadie ayuda.",
    ],
    ("es", "neutral"): [
        "{product} es aceptable, nada especial.",
        "Mi experiencia con {product} es normal.",
    ],
    ("es", "mixed"): [
        "{product} tiene cosas buenas y cosas malas.",
        "Me gusta {product} pero el precio es alto.",
    ],
    ("de", "positive"): [
        "Ich bin mit {product} sehr zufrieden.",
        "{product} funktioniert zuverlässig und gut.",
    ],
    ("de", "negative"): [
        "Ich bin von {product} enttäuscht, der Support meldet sich nicht.",
        "{product} hat zu viele technische Probleme.",
    ],
    ("de", "neutral"): [
        "{product} ist in Ordnung, nichts Besonderes.",
        "Meine Erfahrung mit {product} war durchschnittlich.",
    ],
    ("de", "mixed"): [
        "{product} ist teilweise gut, teilweise enttäuschend.",
        "Ich mag {product}, aber der Preis ist zu hoch.",
    ],
    ("fr", "positive"): [
        "Je suis très satisfait de {product}.",
        "{product} fonctionne très bien, je recommande.",
    ],
    ("fr", "negative"): [
        "Très déçu par {product}, le support ne répond pas.",
        "{product} pose trop de problèmes techniques.",
    ],
    ("fr", "neutral"): [
        "{product} est correct, sans plus.",
        "Mon expérience avec {product} est moyenne.",
    ],
    ("fr", "mixed"): [
        "{product} a de bons et de mauvais côtés.",
        "J'aime {product} mais le prix est élevé.",
    ],
}

SUPPORT_OPENINGS = {
    "positive": [
        "Hi team, just wanted to say thanks,",
        "Hello, quick note of appreciation,",
    ],
    "negative": [
        "Hi, I need urgent help,",
        "Hello, this is my third time writing about this,",
        "Hi team, I am losing patience,",
    ],
    "neutral": [
        "Hi, I have a question,",
        "Hello, could you clarify something,",
    ],
    "mixed": [
        "Hi, part of this works but part does not,",
        "Hello, I need help with one thing,",
    ],
}

SUPPORT_QUESTIONS = [
    "could you please look into this today?",
    "can someone explain why this keeps happening?",
    "please treat this as a priority for our account.",
    "a workaround for now would also help.",
    "please confirm once this is fixed.",
]


def compose_feedback_text(rng, product_name, theme, sentiment):
    """Return (text, language, text_style) for a review or survey response."""
    roll = rng.random()
    if roll < 0.05 and sentiment == "negative":
        # Sarcasm only makes sense as negative feedback.
        return rng.choice(SARCASTIC).format(product=product_name), "en", "sarcastic"
    if roll < 0.11:
        lang = rng.choice(["hi", "mr", "es", "de", "fr"])
        template = rng.choice(MULTILINGUAL[(lang, sentiment)])
        return template.format(product=product_name), lang, "multilingual"
    opening = rng.choice(OPENINGS[sentiment]).format(product=product_name)
    if sentiment == "mixed":
        good = rng.choice(ASPECTS[theme]["positive"])
        bad = rng.choice(ASPECTS[theme]["negative"])
        aspect = f"{good}, but {bad}"
    else:
        aspect = rng.choice(ASPECTS[theme][sentiment])
    closing = rng.choice(CLOSINGS[sentiment])
    style = "ambiguous" if sentiment == "mixed" else "standard"
    return f"{opening} Noticed that {aspect}. {closing}", "en", style


def compose_support_text(rng, product_name, theme, sentiment):
    """Return (text, language, text_style) for a customer support message."""
    roll = rng.random()
    if roll < 0.06:
        lang = rng.choice(["hi", "mr", "es", "de", "fr"])
        template = rng.choice(MULTILINGUAL[(lang, sentiment)])
        return template.format(product=product_name), lang, "multilingual"
    opening = rng.choice(SUPPORT_OPENINGS[sentiment])
    if sentiment == "mixed":
        aspect = (f"{rng.choice(ASPECTS[theme]['positive'])}, but "
                  f"{rng.choice(ASPECTS[theme]['negative'])}")
    else:
        aspect = rng.choice(ASPECTS[theme][sentiment])
    question = rng.choice(SUPPORT_QUESTIONS)
    style = "ambiguous" if sentiment == "mixed" else "standard"
    return f"{opening} regarding {product_name}: {aspect}. {question}", "en", style


AGENT_REPLIES = [
    "Thank you for reaching out. We are looking into this and will update you shortly.",
    "We apologise for the inconvenience. Our team is working on a fix.",
    "Thanks for the details. This has been escalated to the concerned team.",
    "We have resolved this from our side. Please confirm if everything works now.",
    "We appreciate your patience. A specialist will follow up today.",
]
