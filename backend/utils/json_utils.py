import re
import json

def extract_json(text: str) -> dict:
    if not text:
        return {}

    # remove markdown fences
    text = re.sub(r"```(json)?", "", text)

    # extract JSON block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}