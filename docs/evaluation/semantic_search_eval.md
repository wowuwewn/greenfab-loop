# Semantic search 기능 검증

## 범위

이 평가는 DEMO Demand 3건과 합성 질의 6건을 이용한 소규모 기능 검증이다. 실제 기업 데이터나 실제 거래 결과를 사용하지 않았으며, 제조업 전반의 검색 성능을 입증하는 평가가 아니다.

- BGE: `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`, CPU
- Baseline: DEMO Demand 설명 3건에 맞춘 단어 unigram TF-IDF
- 정답: 질의 작성 시 지정한 관련 DEMO demand_id 1건
- 지표: Top-1 hit, Hit@3

## 결과

| 방식 | Top-1 | Hit@3 |
| --- | ---: | ---: |
| BGE-M3 | 6/6 | 6/6 |
| TF-IDF | 5/6 | 6/6 |

| 질의 | 기대 후보 | BGE Top-3 | TF-IDF Top-3 |
| --- | --- | --- | --- |
| Q01 | D01 | D01 · D11 · D15 | D01 · D15 · D11 |
| Q02 | D01 | D01 · D15 · D11 | D01 · D15 · D11 |
| Q03 | D15 | D15 · D11 · D01 | D15 · D01 · D11 |
| Q04 | D15 | D15 · D01 · D11 | D15 · D01 · D11 |
| Q05 | D11 | D11 · D15 · D01 | D01 · D11 · D15 |
| Q06 | D11 | D11 · D15 · D01 | D11 · D01 · D15 |

Q05에서 단어 TF-IDF는 표현이 달라 D01을 1위로 반환했지만 BGE-M3는 기대 후보 D11을 1위로 반환했다. 다만 질의가 6개뿐이고 후보도 3개뿐이므로, 이 차이를 일반적인 우수성이나 산업 성능으로 해석하면 안 된다.

세부 질의와 점수는 [semantic_search_queries.json](./semantic_search_queries.json)과 [semantic_search_eval.json](./semantic_search_eval.json)에 기록했다. `semantic_similarity`는 문장 의미의 가까움 정도이며 산업 적합도, 안전성 또는 재활용 성공 확률이 아니다.


## 검증한 것과 검증하지 못한 것

검증한 것은 UCI SECOM 기반 위험 우선순위 선별, 실제 BGE-M3 임베딩·Chroma Top-3 실행, semantic similarity와 deterministic Rule 및 Human Decision의 역할 분리, Golden Demo API E2E이다. Q05에서 단어 TF-IDF가 표현 차이 때문에 기대 후보를 Top-1으로 찾지 못한 사례도 확인했다.

검증하지 못한 것은 실제 산업 수요처 적합성, 실제 재활용 가능성·안전성, 실제 ESG 감축 효과, 제조업 전체로의 일반화이다. 의미 검색만으로 이 항목을 확정할 수 없기 때문에 BGE는 검토 후보만 제시하고, 명확한 조건은 Rule로 확인하며, 최종 결정은 사람이 기록하도록 설계했다.
