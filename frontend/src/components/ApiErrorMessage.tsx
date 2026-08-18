import { CircleAlert, RotateCcw } from 'lucide-react'
import {
  getApiErrorMessage,
  type ApiError,
  type ApiFieldError,
} from '../api/client'

interface ApiErrorMessageProps {
  error: ApiError | null
  fieldErrors?: ApiFieldError[]
  message?: string
  onRetry?: () => void
  retryDisabled?: boolean
}

export function ApiErrorMessage({
  error,
  fieldErrors,
  message,
  onRetry,
  retryDisabled = false,
}: ApiErrorMessageProps) {
  if (!error) return null

  const visibleFieldErrors = fieldErrors ?? error.fieldErrors

  return (
    <div className="api-error-message" role="alert">
      <CircleAlert size={17} strokeWidth={1.9} aria-hidden="true" />
      <div className="api-error-message__copy">
        <strong>요청을 완료하지 못했습니다</strong>
        <p>{message ?? getApiErrorMessage(error)}</p>
        {visibleFieldErrors.length > 0 && (
          <ul>
            {visibleFieldErrors.map((fieldError, index) => (
              <li key={`${fieldError.field}-${index}`}>{fieldError.message}</li>
            ))}
          </ul>
        )}
        {error.traceId && <small>요청 ID: {error.traceId}</small>}
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} disabled={retryDisabled}>
          <RotateCcw size={14} strokeWidth={1.9} aria-hidden="true" />
          재시도
        </button>
      )}
    </div>
  )
}
