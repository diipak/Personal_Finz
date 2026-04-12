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

    text = re.sub(r"[^\w\s]", "", text)

    text = text.strip()

    words = text.split()

    if words:
        return words[0]

    return text