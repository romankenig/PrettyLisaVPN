import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { useApplication } from "../state/application";
import { supportDiagnostics, validateScreenshots } from "../support/model";

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
  const active = useSyncExternalStore(session.subscribe, session.current, session.current);
  const vpn = useSyncExternalStore(vpnConnection.subscribe, vpnConnection.current, vpnConnection.current);
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
  const [receipt, setReceipt] = useState<string | null>(null);
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
    if (!subject.trim() || !description.trim() ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("заполните тему, описание и email для ответа");
      return;
    }
    inFlight.current = true;
    setPending(true);
    setError(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const result = await support.send({
        request_id: crypto.randomUUID(),
        subject: subject.trim(),
        description: description.trim(),
        reply_email: email.trim(),
        diagnostics: includeDiagnostics ? diagnostics : null,
        screenshots,
      }, active.accessToken, abort.signal);
      if (!alive.current || abort.signal.aborted || session.current()?.sessionId !== active.sessionId) return;
      if (!result.request_id.trim()) throw new Error("INVALID_SUPPORT_RECEIPT");
      setReceipt(result.request_id);
      setScreenshots([]);
    } catch {
      if (alive.current && !abort.signal.aborted)
        setError("не удалось подтвердить отправку. обращение не отмечено как отправленное");
    } finally {
      inFlight.current = false;
      if (alive.current) setPending(false);
    }
  }

  return (
    <dialog ref={dialog} className="support-dialog" aria-labelledby="support-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <header className="support-dialog-heading">
        <h2 id="support-dialog-title">помощь и поддержка</h2>
        <button type="button" className="support-close" aria-label="закрыть обращение" onClick={onClose}>×</button>
      </header>
      {receipt ? (
        <div className="support-receipt" role="status">
          <h3>обращение принято</h3>
          <p>ответ придёт на {email}</p>
          <p>номер: {receipt}</p>
          <button type="button" onClick={onClose}>готово</button>
        </div>
      ) : (
        <form onSubmit={(event) => void submit(event)} noValidate>
          <div className="support-fields">
            <label>тема<input name="subject" autoFocus maxLength={120} required value={subject} disabled={pending} onChange={(event) => setSubject(event.target.value)} placeholder="кратко о проблеме" /></label>
            <label>описание проблемы<textarea name="description" maxLength={4000} required value={description} disabled={pending} onChange={(event) => setDescription(event.target.value)} placeholder="что произошло и что вы ожидали" /></label>
            <label>email для ответа<input name="reply_email" type="email" maxLength={254} required value={email} disabled={pending} onChange={(event) => setEmail(event.target.value)} placeholder="example@email.com" /></label>
          </div>
          <div className="support-attachments">
            <label className="support-file-label">прикрепить скриншоты
              <input type="file" className="visually-hidden" aria-label="прикрепить скриншоты" accept="image/png,image/jpeg,image/webp" multiple disabled={pending || checkingFiles} onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                void addFiles(files);
              }} />
            </label>
            <span>до 3 файлов · PNG, JPEG, WebP · до 5 МБ каждый, 10 МБ всего</span>
            {screenshots.length ? <ul>{screenshots.map((file, index) => (
              <li key={index}><span>{file.name}</span><button type="button" disabled={pending || checkingFiles} aria-label={`убрать ${file.name}`} onClick={() => setScreenshots(screenshots.filter((_, position) => position !== index))}>×</button></li>
            ))}</ul> : null}
          </div>
          <div className="support-diagnostics">
            <label><input type="checkbox" checked={includeDiagnostics} disabled={pending} onChange={(event) => setIncludeDiagnostics(event.target.checked)} />приложить технические данные</label>
            {includeDiagnostics ? <details><summary>что будет приложено</summary><pre>{JSON.stringify(diagnostics, null, 2)}</pre></details> : null}
          </div>
          {!support ? <p className="support-unavailable">отправка пока недоступна</p> : null}
          {!active ? <p className="support-unavailable">войдите в аккаунт для отправки</p> : null}
          {error ? <p className="support-error" role="alert">{error}</p> : null}
          <footer className="support-actions">
            <button type="button" className="support-cancel" onClick={onClose}>отмена</button>
            <button type="submit" disabled={pending || checkingFiles || !support || !active}>{pending ? "отправляем…" : "отправить"}</button>
          </footer>
        </form>
      )}
    </dialog>
  );
}
