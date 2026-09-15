"""VADER sentiment label policy."""


def label_compound(score: float) -> str:
    value = float(score)
    if not -1.0 <= value <= 1.0:
        raise ValueError("VADER compound score must be between -1 and 1")
    if value >= 0.05:
        return "positive"
    if value <= -0.05:
        return "negative"
    return "neutral"

