"""Pure text profiling and language-admission rules."""
import math
import re


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*|[0-9]+(?:[./][0-9]+)*")
SENTENCE_PATTERN = re.compile(r"[^.!?]+(?:[.!?]+|$)")
WHITESPACE = re.compile(r"\s+")


def fasttext_input(text):
    """Convert arbitrary review whitespace to the single line expected by fastText."""
    return WHITESPACE.sub(' ', text or '').strip()


def basic_text_features(text):
    text = text or ''
    stripped = text.strip()
    sentences = ([part for part in SENTENCE_PATTERN.findall(stripped)
                  if any(character.isalnum() for character in part)] if stripped else [])
    return dict(
        char_count=len(text),
        word_count=len(WORD_PATTERN.findall(text)),
        sentence_count=len(sentences),
        line_count=sum(bool(line.strip()) for line in text.splitlines()),
        alphabetic_count=sum(character.isalpha() for character in text),
    )


def assess_language(text, predicted_label, probability, *, min_alphabetic=5, min_confidence=0.80):
    features = basic_text_features(text)
    result = dict(language='unknown', language_confidence=None, language_status=None,
                  eligible_nlp=False, nlp_exclusion_reasons=[])
    if not text:
        result.update(language_status='empty', nlp_exclusion_reasons=['text:empty'])
        return result
    if features['alphabetic_count'] == 0:
        result.update(language_status='non_linguistic',
                      nlp_exclusion_reasons=['text:non_linguistic'])
        return result
    if features['alphabetic_count'] < min_alphabetic:
        result.update(language_status='too_short', nlp_exclusion_reasons=['text:too_short'])
        return result
    if (not isinstance(predicted_label, str) or not predicted_label.startswith('__label__')
            or not isinstance(probability, (int, float)) or isinstance(probability, bool)
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        result.update(language_status='invalid_prediction',
                      nlp_exclusion_reasons=['language:invalid_prediction'])
        return result
    language = predicted_label.removeprefix('__label__')
    result.update(language=language, language_confidence=float(probability))
    if probability < min_confidence:
        result.update(language_status='low_confidence',
                      nlp_exclusion_reasons=['language:low_confidence'])
    elif language != 'en':
        result.update(language_status='non_english',
                      nlp_exclusion_reasons=['language:non_english'])
    else:
        result.update(language_status='accepted', eligible_nlp=True)
    return result


def profile_rows(rows, predictor, *, min_alphabetic=5, min_confidence=0.80):
    """Profile a bounded batch, calling fastText only for linguistic-enough text."""
    prepared = []
    prediction_indexes = []
    prediction_texts = []
    for source in rows:
        source = source.asDict(recursive=False) if hasattr(source, 'asDict') else dict(source)
        text = source.get('text_normalized') or ''
        features = basic_text_features(text)
        prepared.append((source, text, features, None, None))
        if features['alphabetic_count'] >= min_alphabetic:
            prediction_indexes.append(len(prepared) - 1)
            prediction_texts.append(fasttext_input(text))
    if prediction_texts:
        labels, probabilities = predictor.predict(prediction_texts, k=1)
        if len(labels) != len(prediction_texts) or len(probabilities) != len(prediction_texts):
            raise ValueError('fastText returned a different prediction count than input count')
        for prepared_index, label_values, probability_values in zip(
                prediction_indexes, labels, probabilities, strict=True):
            source, text, features, _, _ = prepared[prepared_index]
            prepared[prepared_index] = (
                source, text, features, str(label_values[0]), float(probability_values[0])
            )
    results = []
    for source, text, features, label, probability in prepared:
        language = assess_language(
            text, label, probability,
            min_alphabetic=min_alphabetic,
            min_confidence=min_confidence,
        )
        results.append(dict(
            review_id=source['review_id'],
            parent_asin=source.get('parent_asin'),
            rating=source.get('rating'),
            review_month=source.get('review_month'),
            **features,
            **language,
        ))
    return results
