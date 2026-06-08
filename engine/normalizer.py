import re

REMOVE_WORDS = [
    "gmbh",
    "sarl",
    "ltd",
    "inc",
    "kg"
]

def normalize(description: str):

    text = description.lower()

    text = re.sub(r"\d+", "", text)

    for word in REMOVE_WORDS:
        text = text.replace(word, "")

    text = re.sub(r"[^\w\s]", " ", text)

    text = text.strip()

    # Ensure single spaces between words
    text = " ".join(text.split())

    return text