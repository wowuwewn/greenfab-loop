"""Compare BGE-M3 and a small word TF-IDF baseline on synthetic DEMO queries.

This is a functional smoke evaluation, not an industrial performance claim.
It reads the immutable DEMO Demand seed and never mutates application data.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import settings
from app.seed import DEMO_DEMANDS

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def build_tfidf_vectors(texts: list[str]) -> tuple[list[dict[str, float]], dict[str, float]]:
    tokenized = [tokenize(text) for text in texts]
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))
    idf = {
        token: math.log((1 + len(texts)) / (1 + frequency)) + 1
        for token, frequency in document_frequency.items()
    }
    return [tfidf_vector(tokens, idf) for tokens in tokenized], idf


def tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(token for token in tokens if token in idf)
    if not counts:
        return {}
    total = sum(counts.values())
    weighted = {token: count / total * idf[token] for token, count in counts.items()}
    norm = math.sqrt(sum(value * value for value in weighted.values()))
    return {token: value / norm for token, value in weighted.items()} if norm else {}


def sparse_cosine(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(value * right.get(token, 0.0) for token, value in left.items())


def ranks(scores: list[float], demand_ids: list[str]) -> list[dict[str, Any]]:
    ordered = sorted(zip(demand_ids, scores, strict=True), key=lambda item: item[1], reverse=True)
    return [
        {"rank": rank, "demand_id": demand_id, "score": float(score)}
        for rank, (demand_id, score) in enumerate(ordered, start=1)
    ]


def metrics(results: list[dict[str, Any]], key: str) -> dict[str, Any]:
    top1 = sum(row[key][0]["demand_id"] == row["expected_demand_id"] for row in results)
    hit3 = sum(
        row["expected_demand_id"] in {candidate["demand_id"] for candidate in row[key][:3]}
        for row in results
    )
    count = len(results)
    return {
        "query_count": count,
        "top_1_hits": top1,
        "top_1_accuracy": top1 / count if count else None,
        "hit_at_3_count": hit3,
        "hit_at_3": hit3 / count if count else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query_file", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.query_file.read_text(encoding="utf-8"))
    queries = payload["queries"]
    demand_ids = [str(demand["demand_id"]) for demand in DEMO_DEMANDS]
    demand_texts = [str(demand["demand_description"]) for demand in DEMO_DEMANDS]

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        settings.bge_model_name,
        revision=settings.bge_model_revision,
        device=settings.bge_device,
    )
    bge_vectors = model.encode(
        demand_texts + [row["text"] for row in queries],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    demand_bge = bge_vectors[: len(demand_texts)]
    query_bge = bge_vectors[len(demand_texts) :]

    demand_tfidf, idf = build_tfidf_vectors(demand_texts)
    results: list[dict[str, Any]] = []
    for row, vector in zip(queries, query_bge, strict=True):
        bge_scores = [float(vector @ demand_vector) for demand_vector in demand_bge]
        query_tfidf = tfidf_vector(tokenize(row["text"]), idf)
        tfidf_scores = [sparse_cosine(query_tfidf, vector) for vector in demand_tfidf]
        results.append(
            {
                "query_id": row["query_id"],
                "text": row["text"],
                "expected_demand_id": row["expected_demand_id"],
                "bge_top3": ranks(bge_scores, demand_ids),
                "tfidf_top3": ranks(tfidf_scores, demand_ids),
            }
        )

    output = {
        "scope": payload["scope"],
        "notice": payload["notice"],
        "model": settings.bge_model_name,
        "model_revision": settings.bge_model_revision,
        "device": settings.bge_device,
        "tfidf_baseline": "word unigram TF-IDF fitted on the three DEMO Demand descriptions",
        "metrics": {
            "bge": metrics(results, "bge_top3"),
            "tfidf": metrics(results, "tfidf_top3"),
        },
        "results": results,
    }
    if args.compact:
        print(json.dumps(output["metrics"], ensure_ascii=False, separators=(",", ":")))
        for row in results:
            bge = "|".join(
                f"{candidate['demand_id']}:{candidate['score']:.6f}"
                for candidate in row["bge_top3"]
            )
            tfidf = "|".join(
                f"{candidate['demand_id']}:{candidate['score']:.6f}"
                for candidate in row["tfidf_top3"]
            )
            print(
                f"{row['query_id']}\texpected={row['expected_demand_id']}\tbge={bge}\ttfidf={tfidf}"
            )
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
