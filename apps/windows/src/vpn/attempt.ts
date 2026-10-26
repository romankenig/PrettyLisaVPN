export interface ConnectionAttempt {
  readonly method: string;
  readonly previousMethod: string | null;
  readonly retry: boolean;
}
export function attemptMessage(attempt: ConnectionAttempt): string {
  return attempt.previousMethod
    ? `${attempt.previousMethod} не подключился, пробую ${attempt.method}…`
    : `Пробую ${attempt.method}…`;
}
