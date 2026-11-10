import { useEffect, useId, useRef, type ReactNode } from "react";
import { t } from "../i18n";

export function ActionConfirmation({
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
  danger = false,
  children,
}: {
  readonly title: string;
  readonly description: string;
  readonly confirmLabel: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
  readonly busy?: boolean;
  readonly danger?: boolean;
  readonly children?: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    cancel.current?.focus();
    return () => {
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="billing-dialog action-confirmation"
      role="alertdialog"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 id={`${id}-title`}>{t(title)}</h2>
      <p id={`${id}-description`}>{t(description)}</p>
      {children}
      <div className="confirmation-actions">
        <button
          ref={cancel}
          className="billing-secondary"
          type="button"
          disabled={busy}
          onClick={onCancel}
        >
          {t("отмена")}
        </button>
        <button
          className={danger ? "revoke-button" : "billing-primary"}
          type="button"
          disabled={busy}
          onClick={onConfirm}
        >
          {t(confirmLabel)}
        </button>
      </div>
    </dialog>
  );
}
