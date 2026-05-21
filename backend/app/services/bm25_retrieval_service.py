from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]+")


def _tokens(value: object) -> list[str]:
    text = str(value or "").casefold().replace("ё", "е")
    return [token for token in _TOKEN_RE.findall(text) if len(token) > 2 and not token.isdigit()]


@dataclass(frozen=True)
class BM25Document:
    content: str
    metadata: dict[str, Any]


class BM25Index:
    def __init__(
        self,
        documents: list[BM25Document],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._documents = documents
        self._k1 = k1
        self._b = b
        self._doc_tokens = [_tokens(document.content) for document in documents]
        self._doc_term_counts = [Counter(tokens) for tokens in self._doc_tokens]
        self._doc_lengths = [len(tokens) for tokens in self._doc_tokens]
        self._avg_doc_length = (
            sum(self._doc_lengths) / len(self._doc_lengths) if self._doc_lengths else 0.0
        )

        document_frequency: Counter[str] = Counter()
        for tokens in self._doc_tokens:
            document_frequency.update(set(tokens))
        total = len(documents)
        self._idf = {
            token: math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }

    def search(
        self,
        query: str,
        *,
        limit: int,
        include_document: Callable[[BM25Document], bool] | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0 or not self._documents:
            return []

        query_terms = _tokens(query)
        if not query_terms:
            return []

        query_counts = Counter(query_terms)
        scored: list[tuple[float, int, BM25Document]] = []
        for index, document in enumerate(self._documents):
            if include_document is not None and not include_document(document):
                continue
            score = self._score(index, query_counts)
            if score <= 0:
                continue
            scored.append((score, index, document))

        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [
            {
                **document.metadata,
                "score": round(score, 4),
                "rerank_score": round(score, 4),
                "rerank_reasons": ["bm25"],
                "threshold": None,
                "matched_query": query,
                "content": document.content,
            }
            for score, _, document in scored[:limit]
        ]

    def _score(self, document_index: int, query_counts: Counter[str]) -> float:
        doc_length = self._doc_lengths[document_index]
        if doc_length == 0:
            return 0.0
        term_counts = self._doc_term_counts[document_index]
        score = 0.0
        for term, query_count in query_counts.items():
            frequency = term_counts.get(term, 0)
            if frequency == 0:
                continue
            idf = self._idf.get(term, 0.0)
            denominator = frequency + self._k1 * (
                1 - self._b + self._b * doc_length / max(self._avg_doc_length, 1.0)
            )
            score += query_count * idf * frequency * (self._k1 + 1) / denominator
        return score
