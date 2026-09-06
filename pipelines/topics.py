import math
import re


STOPWORDS = {
    "and", "are", "but", "for", "from", "had", "has", "have", "not", "that",
    "the", "this", "was", "were", "with", "you", "your", "they", "them", "its",
}


def document_terms(text: str) -> list[str]:
    """Return unique informative unigrams and adjacent bigrams in document order."""
    tokens = [token for token in re.findall(r"[a-z]+", (text or "").lower())
              if len(token) >= 3 and token not in STOPWORDS]
    candidates = tokens + [f"{left} {right}" for left, right in zip(tokens, tokens[1:])]
    return list(dict.fromkeys(candidates))


def tfidf_score(group_document_frequency: int, global_document_frequency: int,
                total_documents: int) -> float:
    if (group_document_frequency < 0 or global_document_frequency < 0 or
            total_documents < 0 or group_document_frequency > global_document_frequency or
            global_document_frequency > total_documents):
        raise ValueError("document frequencies must satisfy 0 <= group <= global <= total")
    return group_document_frequency * (
        math.log((total_documents + 1) / (global_document_frequency + 1)) + 1.0
    )
