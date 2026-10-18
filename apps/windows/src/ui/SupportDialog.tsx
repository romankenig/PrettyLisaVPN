import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";
import { useApplication } from "../state/application";
import {
  type SupportSubmission,
  type SupportReceipt,
  supportDiagnostics,
  validateScreenshots,
} from "../support/model";

export function SupportDialog({
  frontend,
  backend,
  onClose,
}: {
  readonly frontend: string;
  readonly backend: string;
  readonly onClose: () => void;
}) {
  const { session, vpnConnection, support } = useApplication();
  const active = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const vpn = useSyncExternalStore(
    vpnConnection.subscribe,
    vpnConnection.current,
    vpnConnection.current,
  );
  const diagnostics = useMemo(
    () => supportDiagnostics(frontend, backend, active, vpn),
    [frontend, backend, active, vpn],
  );
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState(active?.profile?.email ?? "");
  const [screenshots, setScreenshots] = useState<File[]>([]);
  const [includeDiagnostics, setIncludeDiagnostics] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [checkingFiles, setCheckingFiles] = useState(false);
  const [receipt, setReceipt] = useState<SupportReceipt | null>(null);
  const attempt = useRef<SupportSubmission | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const controller = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const inFlight = useRef(false);
  const selecting = useRef(false);
  const owner = useRef(active?.sessionId);
  useEffect(() => {
    if (owner.current !== active?.sessionId) onClose();
  }, [active?.sessionId, onClose]);
  useEffect(() => {
    alive.current = true;
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => {
      alive.current = false;
      controller.current?.abort();
      previous?.focus();
    };
  }, []);

  async function addFiles(files: File[]) {
    if (selecting.current || inFlight.current) return;
    selecting.current = true;
    setCheckingFiles(true);
    setError(null);
    try {
      const next = [...screenshots, ...files];
      const message = await validateScreenshots(next);
      if (!alive.current) return;
      if (message) setError(message);
      else setScreenshots(next);
    } catch {
      if (alive.current) setError("не удалось прочитать скриншот");
    } finally {
      selecting.current = false;
      if (alive.current) setCheckingFiles(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || selecting.current || !support || !active) return;
    if (
      !subject.trim() ||
      !description.trim() ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
    ) {
      setError("заполните тему, описание и email для ответа");
      return;
    }
    inFlight.current = true;
    setPending(true);
    setError(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      // Keep the complete snapshot, including collected_at, stable after an
      // uncertain network result. Editing the draft explicitly starts a new report.
      const previous = attempt.current;
      if (
        !previous ||
        previous.subject !== subject.trim() ||
        previous.description !== description.trim() ||
        previous.reply_email !== email.trim() ||
        (previous.diagnostics !== null) !== includeDiagnostics ||
        previous.screenshots.length !== screenshots.length ||
        previous.screenshots.some((file, index) => file !== screenshots[index])
      ) {
        attempt.current = {
          request_id: crypto.randomUUID(),
          subject: subject.trim(),
          description: description.trim(),
          reply_email: email.trim(),
          diagnostics: includeDiagnostics ? diagnostics : null,
          screenshots,
        };
      }
      const result = await support.send(
        attempt.current!,
        active.accessToken,
        abort.signal,
      );
      if (
        !alive.current ||
        abort.signal.aborted ||
        session.current()?.sessionId !== active.sessionId
      )
        return;
      if (!result.request_id.trim()) throw new Error("INVALID_SUPPORT_RECEIPT");
      setReceipt(result);
      setScreenshots([]);
    } catch {
      if (alive.current && !abort.signal.aborted)
        setError(
          "не удалось подтвердить отправку. обращение не отмечено как отправленное",
        );
    } finally {
      inFlight.current = false;
      if (alive.current) setPending(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="support-dialog"
      aria-labelledby="support-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header className="support-dialog-heading">
        <h2 id="support-dialog-title">помощь и поддержка</h2>
        <button
          type="button"
          className="support-close"
          aria-label="закрыть обращение"
          onClick={onClose}
        >
          ×
        </button>
      </header>
      {receipt ? (
        <div className="support-receipt" role="status">
          <h3>обращение принято</h3>
          <p>адрес для ответа: {email}</p>
          <p>номер: {receipt.request_id}</p>
          <p>
            {
              {
                ACCEPTED: "обращение сохранено и ожидает отправки письма",
                RETRYING: "отправка письма будет повторена",
                SENT: "почтовый сервер принял письмо",
                FAILED: "письмо пока не отправлено; обращение сохранено",
                EXPIRED: "срок хранения содержимого истёк",
              }[receipt.status ?? "ACCEPTED"]
            }
          </p>
          {support?.getStatus ? (
            <button
              type="button"
              disabled={pending}
              onClick={() => {
                if (!active || !support.getStatus) return;
                setPending(true);
                setError(null);
                const abort = new AbortController();
                controller.current = abort;
                void support
                  .getStatus(
                    receipt.request_id,
                    active.accessToken,
                    abort.signal,
                  )
                  .then((value) => {
                    if (alive.current && !abort.signal.aborted) {
                      if (value) setReceipt(value);
                      else setError("не удалось получить статус обращения");
                    }
                  })
                  .catch(() => {
                    if (alive.current && !abort.signal.aborted)
                      setError("не удалось получить статус обращения");
                  })
                  .finally(() => {
                    if (alive.current) setPending(false);
                  });
              }}
            >
              проверить статус
            </button>
          ) : null}
          {error ? <p role="alert">{error}</p> : null}
          <button type="button" onClick={onClose}>
            готово
          </button>
        </div>
      ) : (
        <form onSubmit={(event) => void submit(event)} noValidate>
          <div className="support-fields">
            <label>
              тема
              <input
                name="subject"
                autoFocus
                maxLength={120}
                required
                value={subject}
                disabled={pending}
                onChange={(event) => setSubject(event.target.value)}
                placeholder="кратко о проблеме"
              />
            </label>
            <label>
              описание проблемы
              <textarea
                name="description"
                maxLength={4000}
                required
                value={description}
                disabled={pending}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="что произошло и что вы ожидали"
              />
            </label>
            <label>
              email для ответа
              <input
                name="reply_email"
                type="email"
                maxLength={254}
                required
                value={email}
                disabled={pending}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="example@email.com"
              />
            </label>
          </div>
          <div className="support-attachments">
            <label className="support-file-label">
              прикрепить скриншоты
              <input
                type="file"
                className="visually-hidden"
                aria-label="прикрепить скриншоты"
                accept="image/png,image/jpeg,image/webp"
                multiple
                disabled={pending || checkingFiles}
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  event.target.value = "";
                  void addFiles(files);
                }}
              />
            </label>
            <span>
              до 3 файлов · PNG, JPEG, WebP · до 5 МБ каждый, 10 МБ всего
            </span>
            {screenshots.length ? (
              <ul>
                {screenshots.map((file, index) => (
                  <li key={index}>
                    <span>{file.name}</span>
                    <button
                      type="button"
                      disabled={pending || checkingFiles}
                      aria-label={`убрать ${file.name}`}
                      onClick={() =>
                        setScreenshots(
                          screenshots.filter(
                            (_, position) => position !== index,
                          ),
                        )
                      }
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="support-diagnostics">
            <label>
              <input
                type="checkbox"
                checked={includeDiagnostics}
                disabled={pending}
                onChange={(event) =>
                  setIncludeDiagnostics(event.target.checked)
                }
              />
              приложить технические данные
            </label>
            {includeDiagnostics ? (
              <details>
                <summary>что будет приложено</summary>
                <pre>{JSON.stringify(diagnostics, null, 2)}</pre>
              </details>
            ) : null}
          </div>
          {!support ? (
            <p className="support-unavailable">отправка пока недоступна</p>
          ) : null}
          {!active ? (
            <p className="support-unavailable">
              войдите в аккаунт для отправки
            </p>
          ) : null}
          {error ? (
            <p className="support-error" role="alert">
              {error}
            </p>
          ) : null}
          <p>закрытие окна не отменяет уже принятое обращение</p>
          <footer className="support-actions">
            <button type="button" className="support-cancel" onClick={onClose}>
              отмена
            </button>
            <button
              type="submit"
              disabled={pending || checkingFiles || !support || !active}
            >
              {pending ? "отправляем…" : "отправить"}
            </button>
          </footer>
        </form>
      )}
    </dialog>
  );
}
