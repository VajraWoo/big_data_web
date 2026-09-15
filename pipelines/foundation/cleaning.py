"""Pure, versioned Silver rules and bounded streaming source registration."""
import base64
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import unicodedata

RELEASE = 'amazon-reviews-2023-appliances-v1'
RULE_VERSION = 'silver-basic-v1'
MAX_TIMESTAMP = 1696118399999  # published dataset cutoff month, UTC


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def stable_id(filename, line):
    return digest(f'{RELEASE}\n{filename}\n{line}')


def select_lines(total, size, seed):
    return set(random.Random(seed).sample(range(1, total + 1), min(size, total)))


def stage_file(source, expected, destination, selected=None, shard_rows=50000):
    source, destination = Path(source), Path(destination)
    with source.open('rb') as stream:
        actual_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if source.stat().st_size != expected['bytes'] or actual_hash != expected['sha256'].lower():
        raise ValueError(f'Bronze integrity mismatch: {source.name}')
    destination.mkdir(parents=True, exist_ok=False)
    handle, count, kept = None, 0, 0
    try:
        with gzip.open(source, 'rb') as stream:
            for count, raw in enumerate(stream, 1):
                if selected is not None and count not in selected:
                    continue
                if kept % shard_rows == 0:
                    if handle:
                        handle.close()
                    handle = (destination/f'part-{kept//shard_rows:05d}.jsonl').open('w', encoding='utf-8')
                try:
                    decoded, encoded = raw.decode('utf-8'), None
                except UnicodeDecodeError:
                    decoded, encoded = None, base64.b64encode(raw).decode('ascii')
                envelope = dict(source_file=source.name, source_line_number=count,
                                raw_json=decoded, raw_bytes_base64=encoded)
                handle.write(json.dumps(envelope, ensure_ascii=True, separators=(',', ':'))+'\n')
                kept += 1
    finally:
        if handle:
            handle.close()
    if count != expected['records']:
        raise ValueError(f'Bronze row count mismatch: {source.name}: {count} != {expected["records"]}')
    if selected is not None and kept != len(selected):
        raise ValueError('Selected source lines were not all present')
    return dict(source_file=source.name, sha256=actual_hash, bytes=source.stat().st_size,
                rows_scanned=count, rows_selected=kept, gzip_read_to_eof=True)


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite_json_number')


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('nonfinite_json_number')
    return number


def clean_record(envelope, role, run_id):
    row = dict(envelope)
    row.update(data_release_id=RELEASE, processing_run_id=run_id, silver_rule_version=RULE_VERSION,
               parse_status='ok', parse_error_code=None, field_status={}, field_types={}, field_issues=[])
    row['raw_bytes_base64'] = envelope.get('raw_bytes_base64')
    row['review_id' if role == 'reviews' else 'metadata_id'] = stable_id(row['source_file'], row['source_line_number'])
    try:
        if row['raw_bytes_base64']:
            raise ValueError('invalid_utf8')
        value = json.loads(row['raw_json'], object_pairs_hook=strict_pairs,
                           parse_constant=reject_constant, parse_float=finite_float)
        if not isinstance(value, dict):
            raise ValueError('non_object_json')
        # Reject isolated UTF-16 surrogate code points which cannot be stored as UTF-8.
        canonical = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        row['exact_hash'] = digest(canonical)
    except (ValueError, TypeError, UnicodeError) as error:
        row['parse_status'] = 'quarantined'
        row['parse_error_code'] = ('invalid_json' if isinstance(error, json.JSONDecodeError)
                                   else 'invalid_unicode' if isinstance(error, UnicodeError) else str(error))
        return row

    def field(name, types, valid=lambda x: True):
        v = value.get(name)
        status = ('missing' if name not in value else 'null' if v is None
                  else 'invalid_type' if type(v) not in types else 'valid' if valid(v) else 'invalid_value')
        row['field_types'][name] = 'missing' if name not in value else type(v).__name__
        row['field_status'][name] = status
        if status != 'valid':
            row['field_issues'].append(f'{name}:{status}')
        return v if status == 'valid' else None

    row['parent_asin'] = field('parent_asin', (str,), lambda v: bool(v.strip()))
    if role != 'reviews':
        for name in ('title', 'store', 'main_category'):
            row[name] = field(name, (str,), lambda v: bool(v.strip()))
        row['price'] = field('price', (int, float), lambda v: 0 <= v <= 1.7976931348623157e308)
        if row['price'] is not None:
            row['price'] = float(row['price'])
        row['categories'] = field('categories', (list,), lambda v: all(type(x) is str for x in v))
        for name, types in (('details', (dict,)), ('features', (list,)), ('description', (list,))):
            v = field(name, types)
            row[name+'_json'] = json.dumps(v, ensure_ascii=False) if v is not None else None
        row['metadata_status'] = 'usable' if not row['field_issues'] else 'partial'
        return row

    row['asin'] = field('asin', (str,), lambda v: bool(v.strip()))
    user = field('user_id', (str,), lambda v: bool(v.strip()))
    row['user_id_hash'] = digest(user) if user is not None else None
    row['title_raw'] = field('title', (str,))
    row['text_raw'] = field('text', (str,))
    row['rating'] = field('rating', (int, float), lambda v: 1 <= v <= 5)
    if row['rating'] is not None:
        row['rating'] = float(row['rating'])
    row['rating_valid'] = row['rating'] is not None
    row['low_rating'] = row['rating'] <= 2 if row['rating_valid'] else None
    stamp = field('timestamp', (int,), lambda v: 0 <= v <= MAX_TIMESTAMP)
    date = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp) if stamp is not None else None
    row['timestamp_ms'] = stamp
    row['reviewed_at_iso'] = date.isoformat() if date else None
    row['review_month'] = date.strftime('%Y-%m') if date else None
    row['helpful_vote'] = field('helpful_vote', (int,), lambda v: 0 <= v <= 2**63-1)
    row['verified_purchase'] = field('verified_purchase', (bool,))
    text = row['text_raw']
    normalized = unicodedata.normalize('NFC', text).strip() if text is not None else None
    row['text_normalized'] = normalized
    row['text_length'] = len(normalized) if normalized is not None else None
    row['text_status'] = ('invalid_type' if row['field_status']['text'] == 'invalid_type'
                          else 'empty' if not normalized else 'pending_assessment')
    row['body_hash'] = digest(normalized) if normalized else None
    row['language'] = 'unknown'
    row['eligible_rating_stats'] = row['rating_valid']
    row['rating_exclusion_reasons'] = [] if row['rating_valid'] else ['rating:'+row['field_status']['rating']]
    row['eligible_text'] = bool(normalized)
    row['text_exclusion_reasons'] = [] if normalized else ['text:'+row['text_status']]
    row['eligible_nlp'] = None if normalized else False
    row['nlp_exclusion_reasons'] = (['language_not_assessed', 'text_suitability_not_calibrated']
                                     if normalized else ['text:'+row['text_status']])
    row['near_duplicate_cluster_id'] = None
    row['rating_text_mismatch'] = None
    row['burst_flag'] = None
    row['advanced_quality_status'] = 'not_assessed'
    return row
