import { useState, type FormEvent } from 'react'
import { AlertCircle, KeyRound, LoaderCircle, RefreshCw } from 'lucide-react'
import type { ApiError } from '../api/client'

interface ApiBlockingStateProps {
  error: ApiError | null
  onRetry: () => void
}

export function ApiBlockingState({ error, onRetry }: ApiBlockingStateProps) {
  return (
    <main className="api-blocking-state">
      <span aria-hidden="true">
        {error ? (
          <AlertCircle size={27} strokeWidth={1.8} />
        ) : (
          <LoaderCircle className="is-spinning" size={27} strokeWidth={1.8} />
        )}
      </span>
      <h1>
        {error
          ? 'GreenFab Loop를 불러오지 못했습니다'
          : 'Case를 불러오는 중입니다'}
      </h1>
      <p>
        {error
          ? error.message
          : 'FastAPI에서 Case 목록과 상세 상태를 확인하고 있습니다.'}
      </p>
      {error?.traceId && <small>Trace ID · {error.traceId}</small>}
      {error && (
        <button className="primary-button" type="button" onClick={onRetry}>
          <RefreshCw size={16} aria-hidden="true" />
          다시 시도
        </button>
      )}
    </main>
  )
}

interface ApiCredentialGateProps {
  error: ApiError | null
  isConnecting: boolean
  onConnect: (apiKey: string) => void
}

export function ApiCredentialGate({
  error,
  isConnecting,
  onConnect,
}: ApiCredentialGateProps) {
  const [apiKey, setApiKey] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalized = apiKey.trim()
    if (normalized.length < 16 || normalized.length > 512) {
      setValidationError('16자 이상 512자 이하의 발급된 Access Key를 입력해주세요.')
      return
    }
    setValidationError(null)
    onConnect(normalized)
  }

  return (
    <main className="api-credential-gate">
      <section aria-labelledby="api-access-title">
        <span className="api-credential-gate__icon" aria-hidden="true">
          <KeyRound size={25} strokeWidth={1.8} />
        </span>
        <p className="api-credential-gate__eyebrow">
          GREENFAB LOOP · SECURE API
        </p>
        <h1 id="api-access-title">운영 워크스페이스에 연결합니다</h1>
        <p>
          발급받은 API Access Key를 입력하세요. 키는 빌드 파일이나 서버에
          저장하지 않고 이 브라우저 탭의 세션에만 보관합니다.
        </p>
        <form onSubmit={submit} noValidate>
          <label>
            <span>API Access Key</span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value)
                setValidationError(null)
              }}
              aria-invalid={Boolean(validationError || error)}
              disabled={isConnecting}
            />
          </label>
          {(validationError || error) && (
            <p className="api-credential-gate__error" role="alert">
              {validationError ?? error?.message}
            </p>
          )}
          {error?.traceId && <small>Trace ID · {error.traceId}</small>}
          <button className="primary-button" type="submit" disabled={isConnecting}>
            {isConnecting ? (
              <LoaderCircle className="is-spinning" size={17} aria-hidden="true" />
            ) : (
              <KeyRound size={17} aria-hidden="true" />
            )}
            {isConnecting ? '연결 확인 중…' : '안전하게 연결'}
          </button>
        </form>
        <small className="api-credential-gate__note">
          공용 기기에서는 사용 후 탭을 닫아 세션 키를 제거하세요. 제품
          배포에서는 사용자 로그인 기반 BFF/세션 인증으로 교체해야 합니다.
        </small>
      </section>
    </main>
  )
}
