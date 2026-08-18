import type { Match } from '../types/loop'

/**
 * Match 결과가 실제 BGE-M3 런타임 추론인지, Golden Demo snapshot인지 구분한다.
 *
 * Backend 응답에는 별도의 provider 필드가 없지만 두 provider의 `model`과
 * `model_revision` 조합이 서로 겹치지 않는다.
 *
 * - MockMatchProvider: `Xenova/bge-m3` + `greenfab-loop-synthetic-v1@...`
 * - BgeChromaMatchProvider: `BAAI/bge-m3` + `BAAI/bge-m3@<revision>:<collection>`
 *
 * snapshot 판정을 먼저 수행해, snapshot 결과가 실제 추론처럼 표시되는 상황을 막는다.
 */
export type MatchProvenance = 'BGE_RUNTIME' | 'MOCK_SNAPSHOT' | 'UNSPECIFIED'

const RUNTIME_MODEL_NAME = 'BAAI/bge-m3'
const MOCK_SNAPSHOT_MODEL_NAME = 'Xenova/bge-m3'
const MOCK_SNAPSHOT_REVISION_PREFIX = 'greenfab-loop-synthetic-'

export const resolveMatchProvenance = (match: Match | null): MatchProvenance => {
  if (!match) return 'UNSPECIFIED'

  const model = match.model?.trim() ?? ''
  const revision = match.model_revision?.trim() ?? ''

  if (
    model === MOCK_SNAPSHOT_MODEL_NAME ||
    revision.startsWith(MOCK_SNAPSHOT_REVISION_PREFIX)
  ) {
    return 'MOCK_SNAPSHOT'
  }

  if (model === RUNTIME_MODEL_NAME && revision.startsWith(`${RUNTIME_MODEL_NAME}@`)) {
    return 'BGE_RUNTIME'
  }

  return 'UNSPECIFIED'
}
