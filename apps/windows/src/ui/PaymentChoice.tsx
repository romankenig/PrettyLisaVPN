import { useEffect, useRef, useState } from "react";
import {
  formatPrice,
  type Currency,
  type Offer,
  type PaymentRoute,
} from "../billing/model";

const routes = {
  MIR: { title: "карта «мир»", description: "российская банковская карта" },
  BANK_CARD: {
    title: "банковская карта",
    description: "Visa · Mastercard · UnionPay · American Express",
  },
  ALIPAY_WECHAT: {
    title: "Alipay / WeChat Pay",
    description: "электронные кошельки",
  },
  CRYPTO: { title: "криптовалюта", description: "оплата через криптосервис" },
} as const;

export function PaymentChoice({
  currency,
  offer,
  onConfirm,
  onClose,
}: {
  readonly currency: Currency;
  readonly offer: Offer;
  readonly onConfirm: (route: PaymentRoute) => void;
  readonly onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const preferred = currency === "RUB" ? "MIR" : "BANK_CARD";
  const [selected, setSelected] = useState<PaymentRoute>(preferred);
  const order: readonly PaymentRoute[] = [
    preferred,
    preferred === "MIR" ? "BANK_CARD" : "MIR",
    "ALIPAY_WECHAT",
    "CRYPTO",
  ];
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => previous?.focus();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="billing-dialog payment-choice"
      aria-labelledby="payment-choice-title"
      aria-describedby="payment-choice-summary"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <h2 id="payment-choice-title">как оплатить</h2>
      <p id="payment-choice-summary" className="payment-choice-summary">
        {offer.plan.toLowerCase()} · месяц ·{" "}
        {formatPrice(offer.prices[currency].amount_minor, currency)}
      </p>
      <fieldset className="payment-choice-options">
        <legend className="sr-only">способ оплаты</legend>
        {order.map((route) => (
          <label
            key={route}
            className={`payment-choice-option ${selected === route ? "payment-choice-option--selected" : ""}`}
          >
            <input
              type="radio"
              name="payment-route"
              value={route}
              checked={selected === route}
              onChange={() => setSelected(route)}
              aria-label={routes[route].title}
              aria-describedby={`payment-route-description-${route}`}
            />
            <span className="payment-choice-icon">
              <PaymentIcon route={route} />
            </span>
            <span className="payment-choice-label">
              <strong>{routes[route].title}</strong>
              <small id={`payment-route-description-${route}`}>
                {routes[route].description}
              </small>
            </span>
            <span className="payment-choice-check" aria-hidden="true">
              {selected === route ? "✓" : ""}
            </span>
          </label>
        ))}
      </fieldset>
      <p className="payment-choice-hint">
        подтверждение откроется на сайте платёжного сервиса
      </p>
      <div className="payment-choice-actions">
        <button className="billing-secondary" type="button" onClick={onClose}>
          назад
        </button>
        <button
          className="billing-primary"
          type="button"
          onClick={() => onConfirm(selected)}
        >
          перейти к оплате
        </button>
      </div>
    </dialog>
  );
}

function PaymentIcon({ route }: { readonly route: PaymentRoute }) {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {route === "MIR" ? (
        <>
          <rect x="3" y="5" width="22" height="18" rx="3" />
          <path d="M3 11h22M7 17h4m-4 3h7m4-3 2 3 3-5" />
        </>
      ) : route === "BANK_CARD" ? (
        <>
          <rect x="2" y="5" width="21" height="16" rx="3" />
          <path d="M2 10h21M6 16h4" />
          <circle cx="20" cy="19" r="6" fill="var(--color-mercury)" />
          <path d="M14 19h12m-6-6c-4 4-4 8 0 12 4-4 4-8 0-12Z" />
        </>
      ) : route === "ALIPAY_WECHAT" ? (
        <>
          <path d="M16 15a7 7 0 1 0-10 1l-1 4 5-2m15 4 1 4-5-2a7 7 0 1 1 4-2Z" />
          <path d="M7 10h.01M12 10h.01M17 18h.01M22 18h.01" />
        </>
      ) : (
        <>
          <circle cx="14" cy="14" r="11" />
          <path d="M14 6 8 14l6 4 6-4-6-8Zm-6 11 6 6 6-6m-6-11v12" />
        </>
      )}
    </svg>
  );
}
