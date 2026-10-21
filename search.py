"""Catalog search for the Polaris product MCP.

Explicit filters, sorting, pagination, and the tool result shape stay on the
published contract. Retrieval adds intent parsing, a field-weighted inverted
index, and complementary recommendations.
"""
import json
import logging
import math
import re
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator, ValidationError

from lexicon import (
    OOD,
    TYPE_ALIASES,
    Choice,
    parse_intent,
    protected_terms,
)

ROOT = Path(__file__).resolve().parent
INPUT_SCHEMA = json.loads((ROOT / 'schemas/input.schema.json').read_text())
OUTPUT_SCHEMA = json.loads((ROOT / 'schemas/output.schema.json').read_text())
VALIDATOR = Draft202012Validator(INPUT_SCHEMA)
STRING_FILTERS = ('category', 'product_type', 'color', 'audience', 'section', 'pattern')
LOG = logging.getLogger('polaris.search')

NEUTRALS = frozenset({
    'black', 'white', 'off white', 'beige', 'grey', 'light beige', 'dark grey',
    'light grey', 'dark beige', 'greyish beige',
})
COLOR_TOKENS = set()
TYPE_TOKENS = set()


def _phrase_tokens():
    from lexicon import COLOR_GROUPS, EXACT_COLORS, PATTERN_ALIASES, SECTION_ALIASES
    for phrase in list(COLOR_GROUPS) + list(EXACT_COLORS):
        COLOR_TOKENS.update(phrase.split())
    for phrase in TYPE_ALIASES:
        TYPE_TOKENS.update(phrase.split())
    for phrase in list(PATTERN_ALIASES) + list(SECTION_ALIASES):
        TYPE_TOKENS.update(phrase.split())


_phrase_tokens()


def validate_arguments(arguments):
    # Reject non-JSON floating point values even when called directly from Python.
    json.dumps(arguments, allow_nan=False)
    try:
        VALIDATOR.validate(arguments)
    except ValidationError as exc:
        raise ValueError(exc.message) from exc
    filters = arguments.get('filters', {})
    if any(not filters[k].strip() for k in STRING_FILTERS if k in filters):
        raise ValueError('String filters cannot be blank')
    if filters.get('min_price', 0) > filters.get('max_price', math.inf):
        raise ValueError('min_price cannot exceed max_price')


@lru_cache(maxsize=8192)
def tokens(text):
    return tuple(re.findall(r'\w+', text.casefold()))


def _edits(word):
    letters = 'abcdefghijklmnopqrstuvwxyz'
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [left + right[1:] for left, right in splits if right]
    transposes = [left + right[1] + right[0] + right[2:] for left, right in splits if len(right) > 1]
    replaces = [left + char + right[1:] for left, right in splits if right for char in letters]
    inserts = [left + char + right for left, right in splits for char in letters]
    return set(deletes + transposes + replaces + inserts)


def _compatible_audiences(audience):
    folded = (audience or '').casefold()
    ladies = {'ladieswear', 'ladies accessories', 'lingeries/tights', 'divided', 'sport'}
    men = {'menswear', 'divided', 'sport'}
    youth = {
        'children sizes 92-140', 'children sizes 134-170',
        'children accessories, swimwear', 'baby sizes 50-98',
    }
    if folded.startswith('children') or folded.startswith('baby'):
        return youth
    if folded == 'menswear':
        return men
    if folded in ladies or folded == 'sport':
        return ladies | {folded}
    return {folded} if folded else set()


class Catalog:
    def __init__(self, products):
        self.products = sorted(products, key=lambda product: product['id'])
        self.n = len(self.products)
        self._lock = threading.Lock()
        self._cache = {}
        self._build_index()

    @classmethod
    def load(cls, path):
        raw = Path(path).read_bytes()
        try:
            import orjson
            payload = orjson.loads(raw)
        except ImportError:
            payload = json.loads(raw)
        return cls(payload)

    def _build_index(self):
        import time
        started = time.perf_counter()
        products = self.products
        n = self.n
        self.id_index = {product['id']: index for index, product in enumerate(products)}
        self.field_vocab = {}
        self.field_codes = {}
        for key in STRING_FILTERS:
            vocab = {}
            codes = np.empty(n, dtype=np.int16)
            for index, product in enumerate(products):
                value = str(product.get(key) or '').strip().casefold()
                code = vocab.get(value)
                if code is None:
                    code = len(vocab)
                    vocab[value] = code
                codes[index] = code
            self.field_vocab[key] = vocab
            self.field_codes[key] = codes
        self.prices = np.empty(n, dtype=np.float64)
        self.ratings = np.empty(n, dtype=np.float64)
        self.counts = np.empty(n, dtype=np.int32)
        self.name_cf = [''] * n
        postings = {}
        name_postings = {}
        jean_text = np.zeros(n, dtype=bool)
        for index, product in enumerate(products):
            self.prices[index] = product['price']['amount']
            average = product['rating']['average']
            self.ratings[index] = np.nan if average is None else float(average)
            self.counts[index] = int(product['rating']['count'])
            name = product.get('name') or ''
            self.name_cf[index] = name.casefold()
            description = product.get('description') or ''
            fields = ' '.join(str(product.get(key) or '') for key in STRING_FILTERS)
            name_words = set(tokens(name))
            all_words = set(tokens(f'{name} {description} {fields}'))
            if 'jean' in all_words or 'jeans' in all_words:
                jean_text[index] = True
            for token in all_words:
                if len(token) <= 1 or token.isdigit():
                    continue
                postings.setdefault(token, []).append(index)
                if token in name_words:
                    name_postings.setdefault(token, []).append(index)
        self.postings = {token: np.asarray(indexes, dtype=np.int32) for token, indexes in postings.items()}
        self.name_postings = {token: np.asarray(indexes, dtype=np.int32) for token, indexes in name_postings.items()}
        self.df = {token: int(len(indexes)) for token, indexes in self.postings.items()}
        self.idf = {
            token: math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            for token, df in self.df.items()
        } if n else {}
        self._known = set(self.postings) | protected_terms()
        self._correctable = {token for token in self.postings if len(token) >= 4 and token not in OOD}
        self._corrections = {}
        audience = self.field_vocab['audience']
        youth_codes = [code for value, code in audience.items() if value.startswith('children') or value.startswith('baby')]
        self.youth_mask = np.isin(self.field_codes['audience'], youth_codes) if youth_codes else np.zeros(n, dtype=bool)
        trousers = self.field_vocab['product_type'].get('trousers')
        denim = self.field_vocab['pattern'].get('denim')
        if trousers is None:
            self.is_jeans = np.zeros(n, dtype=bool)
        else:
            type_mask = self.field_codes['product_type'] == trousers
            denim_mask = self.field_codes['pattern'] == denim if denim is not None else np.zeros(n, dtype=bool)
            self.is_jeans = type_mask & (denim_mask | jean_text)
        LOG.info('indexed %s products and %s tokens in %.2fs', n, len(self.postings), time.perf_counter() - started)

    def correct_token(self, token):
        if token in self._known or len(token) < 4 or token.isdigit():
            return token
        cached = self._corrections.get(token)
        if cached is not None:
            return cached
        candidates = [word for word in _edits(token) if word in self._correctable]
        if token.endswith('s') and token[:-1] in self._correctable:
            candidates.append(token[:-1])
        if token.endswith('es') and token[:-2] in self._correctable:
            candidates.append(token[:-2])
        best = token if not candidates else max(candidates, key=lambda word: self.df.get(word, 0))
        with self._lock:
            self._corrections[token] = best
        return best

    def _resolve_token(self, token):
        if token in self.postings:
            return token
        if token.endswith('s') and token[:-1] in self.postings:
            return token[:-1]
        plural = token + 's'
        if plural in self.postings:
            return plural
        if token.endswith('s') and (token[:-1] + 'es') in self.postings:
            return token[:-1] + 'es'
        return None

    def relevance(self, product, query_tokens):
        """Lexical overlap used by the original extension point."""
        if not query_tokens:
            return 0
        index = self.id_index.get(product['id'])
        if index is None:
            return 0
        if any(not self._contains(self.postings, index, token) for token in query_tokens):
            return 0
        return 1 + sum(self._contains(self.name_postings, index, token) for token in query_tokens)

    @staticmethod
    def _contains(postings, index, token):
        array = postings.get(token)
        if array is None:
            return False
        at = int(np.searchsorted(array, index))
        return at < array.size and int(array[at]) == index

    @staticmethod
    def matches(product, filters):
        for key in STRING_FILTERS:
            if key in filters and str(product.get(key) or '').strip().casefold() != filters[key].strip().casefold():
                return False
        price = product['price']['amount']
        average = product['rating']['average']
        return (price >= filters.get('min_price', 0)
                and price <= filters.get('max_price', math.inf)
                and ('min_rating' not in filters or
                     (average is not None and average >= filters['min_rating']))
                and product['rating']['count'] >= filters.get('min_review_count', 0))

    def _explicit_mask(self, filters):
        mask = np.ones(self.n, dtype=bool)
        for key in STRING_FILTERS:
            if key not in filters:
                continue
            code = self.field_vocab[key].get(filters[key].strip().casefold())
            if code is None:
                return np.zeros(self.n, dtype=bool)
            mask &= self.field_codes[key] == code
        if 'min_price' in filters:
            mask &= self.prices >= filters['min_price']
        if 'max_price' in filters:
            mask &= self.prices <= filters['max_price']
        if 'min_rating' in filters:
            mask &= ~np.isnan(self.ratings) & (self.ratings >= filters['min_rating'])
        if 'min_review_count' in filters:
            mask &= self.counts >= filters['min_review_count']
        return mask

    def _values_mask(self, field, values):
        mask = np.zeros(self.n, dtype=bool)
        vocab = self.field_vocab[field]
        codes = self.field_codes[field]
        for value in values:
            code = vocab.get(str(value).strip().casefold())
            if code is not None:
                mask |= codes == code
        return mask

    def _combine_price(self, filters, choice):
        explicit_lo = filters.get('min_price')
        explicit_hi = filters.get('max_price')
        query_lo = choice.min_price
        query_hi = choice.max_price
        lo = 0.0 if explicit_lo is None else float(explicit_lo)
        hi = math.inf if explicit_hi is None else float(explicit_hi)
        if explicit_lo is None and query_lo is not None:
            lo = float(query_lo)
        if explicit_hi is None and query_hi is not None:
            hi = float(query_hi)
        if explicit_lo is not None and query_lo is not None and query_lo > lo and (explicit_hi is None or query_lo <= hi):
            lo = float(query_lo)
        if explicit_hi is not None and query_hi is not None and query_hi < hi and query_hi >= lo:
            hi = float(query_hi)
        if lo > hi:
            lo = 0.0 if explicit_lo is None else float(explicit_lo)
            hi = math.inf if explicit_hi is None else float(explicit_hi)
        return lo, hi

    def _neutral_choice(self, choice, filters):
        required = list(choice.required_tokens)
        types = choice.types
        jeans = choice.jeans
        colors = choice.colors
        audiences = choice.audiences
        exclude = choice.exclude_audiences
        sections = choice.sections
        patterns = choice.patterns
        occasion_types = choice.occasion_types
        if 'product_type' in filters:
            types, jeans, occasion_types = (), False, ()
            required = [token for token in required if token not in TYPE_TOKENS]
        if 'color' in filters:
            colors = ()
            required = [token for token in required if token not in COLOR_TOKENS]
        if 'audience' in filters:
            audiences, exclude = (), ()
        if 'section' in filters:
            sections = ()
        if 'pattern' in filters:
            patterns = ()
        if 'category' in filters:
            pass
        return Choice(
            types=types, jeans=jeans, colors=colors, audiences=audiences,
            exclude_audiences=exclude, sections=sections, patterns=patterns,
            min_price=choice.min_price, max_price=choice.max_price,
            min_rating=choice.min_rating, required_tokens=tuple(required),
            boost_tokens=choice.boost_tokens, occasion_types=occasion_types,
            youth=choice.youth, text=choice.text,
        )

    def _choice_mask(self, choice, filters, apply_explicit=True):
        mask = self._explicit_mask(filters) if apply_explicit else np.ones(self.n, dtype=bool)
        if choice.jeans:
            mask &= self.is_jeans
        elif choice.types:
            mask &= self._values_mask('product_type', choice.types)
        elif choice.occasion_types:
            mask &= self._values_mask('product_type', choice.occasion_types)
        if choice.colors and 'color' not in filters:
            mask &= self._values_mask('color', choice.colors)
        if choice.audiences and 'audience' not in filters:
            mask &= self._values_mask('audience', choice.audiences)
        if choice.exclude_audiences and 'audience' not in filters:
            for audience in choice.exclude_audiences:
                code = self.field_vocab['audience'].get(audience)
                if code is not None:
                    mask &= self.field_codes['audience'] != code
        if choice.sections and 'section' not in filters:
            mask &= self._values_mask('section', choice.sections)
        if choice.patterns and 'pattern' not in filters:
            mask &= self._values_mask('pattern', choice.patterns)
        lo, hi = self._combine_price(filters if apply_explicit else {}, choice)
        if lo > 0:
            mask &= self.prices >= lo
        if math.isfinite(hi):
            mask &= self.prices <= hi
        min_rating = filters.get('min_rating') if apply_explicit else None
        if min_rating is None:
            min_rating = choice.min_rating
        elif choice.min_rating is not None:
            min_rating = max(min_rating, choice.min_rating)
        if min_rating is not None:
            mask &= ~np.isnan(self.ratings) & (self.ratings >= min_rating)
        if apply_explicit and 'min_review_count' in filters:
            mask &= self.counts >= filters['min_review_count']
        required = choice.required_tokens
        known = [resolved for token in required if (resolved := self._resolve_token(token))]
        structured = bool(
            choice.types or choice.jeans or choice.occasion_types or choice.colors
            or choice.audiences or choice.sections or choice.patterns or choice.exclude_audiences
        )
        if known:
            token_mask = np.ones(self.n, dtype=bool)
            for token in known:
                bit = np.zeros(self.n, dtype=bool)
                bit[self.postings[token]] = True
                token_mask &= bit
            narrowed = mask & token_mask
            if narrowed.any():
                return narrowed
            if not structured:
                return np.zeros(self.n, dtype=bool)
            return mask
        if required and not structured:
            return np.zeros(self.n, dtype=bool)
        if not structured and not known:
            return np.zeros(self.n, dtype=bool)
        return mask

    def _score_matrix(self, choice):
        score = np.zeros(self.n, dtype=np.float64)
        for token in tuple(choice.required_tokens) + tuple(choice.boost_tokens):
            weight = self.idf.get(token)
            if weight is None:
                continue
            posted = self.postings.get(token)
            if posted is not None:
                score[posted] += weight
            named = self.name_postings.get(token)
            if named is not None:
                score[named] += 2.0 * weight
        if choice.boost_tokens and any(token in ('cheap', 'affordable', 'budget', 'inexpensive') for token in choice.boost_tokens):
            score += (1.0 - (self.prices / max(float(self.prices.max()), 1.0))) * 2.0
        if choice.boost_tokens and any(token in ('premium', 'luxury', 'luxurious', 'expensive') for token in choice.boost_tokens):
            score += (self.prices / max(float(self.prices.max()), 1.0)) * 2.0
        if choice.boost_tokens and any(token in ('best', 'rated', 'rating', 'quality', 'popular') for token in choice.boost_tokens):
            rated = np.where(np.isnan(self.ratings), 0.0, self.ratings)
            score += rated
        if not choice.youth and not choice.audiences:
            score[self.youth_mask] -= 40.0
        return score

    def _order(self, idxs, sort_by, sort_order, scores=None):
        if idxs.size == 0:
            return idxs
        descending = sort_order == 'desc'
        if sort_by == 'relevance':
            key = -scores if descending else scores
            return idxs[np.lexsort((idxs, key))]
        if sort_by == 'id':
            ordered = np.sort(idxs)
            return ordered[::-1] if descending else ordered
        if sort_by == 'price':
            key = -self.prices[idxs] if descending else self.prices[idxs]
            return idxs[np.lexsort((idxs, key))]
        if sort_by == 'review_count':
            key = -self.counts[idxs].astype(np.int32) if descending else self.counts[idxs]
            return idxs[np.lexsort((idxs, key))]
        ratings = self.ratings[idxs]
        missing = np.isnan(ratings)
        signed = np.where(missing, 0.0, -ratings if descending else ratings)
        return idxs[np.lexsort((idxs, signed, missing.astype(np.int8)))]

    def _diversify(self, idxs):
        if idxs.size < 3:
            return idxs
        out = []
        deferred = []
        counts = {}
        values = idxs.tolist()
        for position, index in enumerate(values):
            if len(out) >= 30:
                return np.asarray(out + deferred + values[position:], dtype=np.int32)
            name = self.name_cf[index]
            if counts.get(name, 0) >= 2:
                deferred.append(index)
                continue
            counts[name] = counts.get(name, 0) + 1
            out.append(index)
        return np.asarray(out + deferred, dtype=np.int32)

    def _rank_choice(self, choice, filters, sort_by, sort_order):
        mask = self._choice_mask(choice, filters, apply_explicit=True)
        idxs = np.flatnonzero(mask).astype(np.int32, copy=False)
        if sort_by != 'relevance':
            return self._order(idxs, sort_by, sort_order)
        if idxs.size == 0:
            return idxs
        scores = self._score_matrix(choice)[idxs]
        ordered = self._order(idxs, 'relevance', sort_order, scores)
        if sort_order == 'desc':
            return self._diversify(ordered)
        return ordered

    @staticmethod
    def _interleave(groups):
        seen = set()
        pointers = [0] * len(groups)
        merged = []
        remaining = True
        while remaining:
            remaining = False
            for index, group in enumerate(groups):
                while pointers[index] < group.size and int(group[pointers[index]]) in seen:
                    pointers[index] += 1
                if pointers[index] < group.size:
                    value = int(group[pointers[index]])
                    pointers[index] += 1
                    seen.add(value)
                    merged.append(value)
                    remaining = True
        return np.asarray(merged, dtype=np.int32)

    def _query_order(self, intent, filters, sort_by, sort_order):
        if intent.abstain or not intent.choices:
            return np.empty(0, dtype=np.int32)
        choices = [self._neutral_choice(choice, filters) for choice in intent.choices]
        if (sort_by == 'relevance' and len(choices) == 1 and choices[0].occasion_types
                and not choices[0].types and not choices[0].jeans):
            groups = []
            for type_name in choices[0].occasion_types[:8]:
                narrowed = Choice(**{**choices[0].__dict__, 'occasion_types': (), 'types': (type_name,)})
                groups.append(self._rank_choice(narrowed, filters, sort_by, sort_order))
            return self._interleave([group for group in groups if group.size])
        if sort_by == 'relevance' and len(choices) > 1:
            return self._interleave([
                self._rank_choice(choice, filters, sort_by, sort_order) for choice in choices
            ])
        if len(choices) == 1:
            return self._rank_choice(choices[0], filters, sort_by, sort_order)
        mask = np.zeros(self.n, dtype=bool)
        for choice in choices:
            mask |= self._choice_mask(choice, filters, apply_explicit=True)
        return self._order(np.flatnonzero(mask).astype(np.int32, copy=False), sort_by, sort_order)

    def _empty_order(self, filters, sort_by, sort_order):
        idxs = np.flatnonzero(self._explicit_mask(filters)).astype(np.int32, copy=False)
        if sort_by == 'relevance':
            return idxs
        return self._order(idxs, sort_by, sort_order)

    def recommend(self, results, arguments):
        """Return up to five complements when the query asks for an accompanying item."""
        if not results or not arguments.get('include_recommendations', False):
            return []
        intent = parse_intent(arguments.get('query', ''), self.correct_token)
        complement = intent.complement
        if complement is None or not results:
            return []
        primary = intent.choices[0] if intent.choices else None
        if primary is not None and not complement.audiences and not complement.exclude_audiences:
            complement = Choice(
                **{**complement.__dict__,
                   'audiences': primary.audiences,
                   'exclude_audiences': primary.exclude_audiences,
                   'youth': primary.youth or complement.youth}
            )
        anchor = self.products[self.id_index[results[0]['id']]]
        allowed = _compatible_audiences(anchor['audience'])
        blocked = {item['id'] for item in results}
        mask = self._choice_mask(complement, {}, apply_explicit=False)
        if allowed:
            mask &= self._values_mask('audience', allowed)
        anchor_type = self.field_vocab['product_type'].get(str(anchor.get('product_type') or '').casefold())
        if anchor_type is not None:
            mask &= self.field_codes['product_type'] != anchor_type
        candidates = np.flatnonzero(mask)
        if candidates.size == 0 and allowed:
            mask = self._choice_mask(complement, {}, apply_explicit=False)
            if anchor_type is not None:
                mask &= self.field_codes['product_type'] != anchor_type
            candidates = np.flatnonzero(mask)
        if candidates.size == 0:
            return []
        anchor_color = str(anchor.get('color') or '')
        ranked = sorted(
            (int(index) for index in candidates),
            key=lambda index: (
                -_harmony(anchor_color, self.products[index].get('color') or ''),
                -(0.0 if np.isnan(self.ratings[index]) else float(self.ratings[index])),
                self.products[index]['id'],
            ),
        )
        picked = []
        seen_types = {}
        for index in ranked:
            product = self.products[index]
            if product['id'] in blocked:
                continue
            product_type = product.get('product_type') or ''
            if seen_types.get(product_type, 0) >= 2:
                continue
            seen_types[product_type] = seen_types.get(product_type, 0) + 1
            reason = _reason(anchor, product)
            picked.append({
                'id': product['id'],
                'for_product_id': anchor['id'],
                'reason': reason,
            })
            blocked.add(product['id'])
            if len(picked) == 5:
                break
        return picked

    def search(self, arguments):
        validate_arguments(arguments)
        key = _freeze(arguments)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return {
                'results': [dict(item) for item in cached['results']],
                'recommendations': [dict(item) for item in cached['recommendations']],
            }
        query = arguments.get('query', '').strip()
        filters = arguments.get('filters') or {}
        sort_by = arguments.get('sort_by', 'relevance')
        sort_order = arguments.get('sort_order', 'desc')
        offset = arguments.get('offset', 0)
        limit = arguments.get('limit', 10)
        if not query:
            ordered = self._empty_order(filters, sort_by, sort_order)
        else:
            intent = parse_intent(query, self.correct_token)
            ordered = self._query_order(intent, filters, sort_by, sort_order)
        page = ordered[offset:offset + limit]
        results = [{'id': self.products[int(index)]['id']} for index in page]
        recommendations = self.recommend(results, arguments) if results and arguments.get('include_recommendations', False) else []
        payload = {'results': results, 'recommendations': recommendations}
        with self._lock:
            if len(self._cache) > 1024:
                self._cache.clear()
            self._cache[key] = payload
        return {
            'results': [dict(item) for item in results],
            'recommendations': [dict(item) for item in recommendations],
        }


def _harmony(anchor_color, other_color):
    left = anchor_color.casefold()
    right = other_color.casefold()
    if left == right:
        return 3
    if left.split()[-1:] == right.split()[-1:] and left.split()[-1:] not in (['other'], ['unknown'], []):
        return 2
    if left in NEUTRALS or right in NEUTRALS:
        return 1
    return 0


def _reason(anchor, product):
    pattern = product.get('pattern') or ''
    pattern_text = '' if pattern in ('', 'Solid', 'Unknown') else f'{pattern.casefold()} '
    reason = (
        f"A {product.get('color')} {pattern_text}{product.get('product_type')} "
        f"to accompany this {anchor.get('color')} {anchor.get('product_type')}."
    )
    reason = ' '.join(reason.split())
    return reason[:300]


def _freeze(arguments):
    filters = arguments.get('filters') or {}
    return (
        arguments.get('query', ''),
        tuple(sorted((key, _freeze_value(value)) for key, value in filters.items())),
        arguments.get('sort_by', 'relevance'),
        arguments.get('sort_order', 'desc'),
        arguments.get('offset', 0),
        arguments.get('limit', 10),
        bool(arguments.get('include_recommendations', False)),
    )


def _freeze_value(value):
    if isinstance(value, float):
        return round(value, 6)
    return value
