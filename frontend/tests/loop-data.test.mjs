import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const dataset = JSON.parse(await readFile(new URL("../app/loop_dataset.json", import.meta.url), "utf8"));
const matches = JSON.parse(await readFile(new URL("../app/match_results.json", import.meta.url), "utf8"));

test("synthetic resource-demand contract is internally consistent", () => {
  assert.equal(dataset.metadata.provenance, "SYNTHETIC_DEMO");
  assert.equal(dataset.resources.length, 12);
  assert.equal(dataset.demands.length, 24);
  assert.equal(new Set(dataset.resources.map((item) => item.id)).size, dataset.resources.length);
  assert.equal(new Set(dataset.demands.map((item) => item.id)).size, dataset.demands.length);

  const demandIds = new Set(dataset.demands.map((item) => item.id));
  for (const resource of dataset.resources) assert.ok(demandIds.has(resource.expectedDemandId));
});

test("BGE-M3 snapshot covers every synthetic resource", () => {
  assert.equal(matches.engine, "PRECOMPUTED_BGE_M3");
  assert.equal(matches.metrics.resourceCount, dataset.resources.length);
  assert.equal(matches.metrics.demandCount, dataset.demands.length);
  assert.equal(matches.results.length, dataset.resources.length);
  assert.ok(matches.generatedAt);

  for (const result of matches.results) {
    assert.equal(result.tfidfTop3.length, 3);
    assert.equal(result.embeddingTop3.length, 3);
    assert.equal(new Set(result.embeddingTop3.map((item) => item.demandId)).size, 3);
    assert.ok(result.embeddingTop3.every((item) => Number.isFinite(item.score)));
  }
});

test("reported retrieval metrics are valid rates", () => {
  for (const key of ["tfidfHitAt1", "tfidfRecallAt3", "embeddingHitAt1", "embeddingRecallAt3"]) {
    assert.ok(matches.metrics[key] >= 0 && matches.metrics[key] <= 1, `${key} must be between zero and one`);
  }
});

test("reported retrieval metrics equal the stored ranking snapshot", () => {
  const rate = (engine, cutoff) => matches.results.filter((result) =>
    result[engine].slice(0, cutoff).some((item) => item.demandId === result.expectedDemandId),
  ).length / matches.results.length;

  assert.equal(matches.metrics.tfidfHitAt1, rate("tfidfTop3", 1));
  assert.equal(matches.metrics.tfidfRecallAt3, rate("tfidfTop3", 3));
  assert.equal(matches.metrics.embeddingHitAt1, rate("embeddingTop3", 1));
  assert.equal(matches.metrics.embeddingRecallAt3, rate("embeddingTop3", 3));
});
