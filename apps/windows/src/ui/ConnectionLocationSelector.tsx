import { useEffect, useState } from "react";
import { ApiError, type VpnCountriesResponse } from "../api/client";
import { useApplication } from "../state/application";
import type { VpnLocationSelection } from "../vpn/selection";

const AVAILABILITY_MAX_AGE_MS = 60_000;

type AvailabilityState =
  | { readonly phase: "loading" }
  | {
      readonly phase: "ready" | "refreshing" | "stale";
      readonly data: VpnCountriesResponse;
      readonly message?: string;
    }
  | { readonly phase: "error"; readonly message: string };

export function ConnectionLocationSelector({
  selection,
  onSelectionChange,
}: {
  readonly selection: VpnLocationSelection;
  readonly onSelectionChange: (selection: VpnLocationSelection) => void;
}) {
  const { api, session } = useApplication();
  const activeSession = session.current();
  const [state, setState] = useState<AvailabilityState>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!activeSession) return () => undefined;
    const controller = new AbortController();
    setState((current) =>
      "data" in current
        ? { phase: "refreshing", data: current.data }
        : { phase: "loading" },
    );
    void api
      .listVpnCountries(activeSession.accessToken, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setState({ phase: "ready", data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState((current) =>
          "data" in current
            ? {
                phase: "stale",
                data: current.data,
                message: availabilityError(error),
              }
            : { phase: "error", message: availabilityError(error) },
        );
      });
    return () => controller.abort();
  }, [activeSession, api, attempt]);

  useEffect(() => {
    if (state.phase !== "ready") return;
    const timer = globalThis.setTimeout(
      () =>
        setState((current) =>
          current.phase === "ready"
            ? { phase: "stale", data: current.data }
            : current,
        ),
      AVAILABILITY_MAX_AGE_MS,
    );
    return () => globalThis.clearTimeout(timer);
  }, [state]);

  useEffect(() => {
    if (state.phase !== "ready" || selection.mode !== "COUNTRY") return;
    const selectedCountry = state.data.countries.find(
      (country) => country.country_code === selection.country_code,
    );
    if (!selectedCountry?.available) onSelectionChange({ mode: "AUTO" });
  }, [onSelectionChange, selection, state]);

  if (state.phase === "loading") {
    return <p role="status">загружаем доступные локации…</p>;
  }
  if (state.phase === "error") {
    return (
      <AvailabilityNotice
        message={state.message}
        onRefresh={() => setAttempt((value) => value + 1)}
      />
    );
  }

  const disabled = state.phase === "stale";
  return (
    <section
      className="location-selector"
      aria-labelledby="location-selector-title"
    >
      <div className="location-selector__heading">
        <div>
          <p className="connection-card__label">локация</p>
          <h2 id="location-selector-title">Куда подключиться</h2>
        </div>
        <button
          type="button"
          onClick={() => setAttempt((value) => value + 1)}
          disabled={state.phase === "refreshing"}
        >
          {state.phase === "refreshing" ? "обновляем…" : "обновить"}
        </button>
      </div>

      {state.phase === "stale" ? (
        <p className="availability-warning" role="alert">
          {state.message ??
            "Данные устарели. Обновите список перед подключением."}
        </p>
      ) : null}

      <fieldset disabled={disabled} className="location-options">
        <legend className="sr-only">Режим подключения</legend>
        <LocationOption
          checked={selection.mode === "AUTO"}
          disabled={!state.data.autopilot.available}
          name="Автопилот"
          description="Рекомендуемый режим"
          quality={state.data.autopilot.quality}
          onSelect={() => onSelectionChange({ mode: "AUTO" })}
        />
        {state.data.countries.map((country) => (
          <LocationOption
            key={country.country_code}
            checked={
              selection.mode === "COUNTRY" &&
              selection.country_code === country.country_code
            }
            disabled={!country.available}
            name={countryName(country.country_code)}
            description={country.country_code}
            quality={country.quality}
            onSelect={() =>
              onSelectionChange({
                mode: "COUNTRY",
                country_code: country.country_code,
              })
            }
          />
        ))}
      </fieldset>
    </section>
  );
}

function LocationOption({
  checked,
  disabled,
  name,
  description,
  quality,
  onSelect,
}: {
  readonly checked: boolean;
  readonly disabled: boolean;
  readonly name: string;
  readonly description: string;
  readonly quality: number;
  readonly onSelect: () => void;
}) {
  return (
    <label
      className={`location-option${disabled ? " location-option--disabled" : ""}`}
    >
      <input
        type="radio"
        name="vpn-location"
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
      />
      <span className="location-option__name">
        <strong>{name}</strong>
        <small>{description}</small>
      </span>
      <span
        className="location-option__quality"
        aria-label={`Качество ${quality} из 100`}
      >
        {quality}
      </span>
    </label>
  );
}

function AvailabilityNotice({
  message,
  onRefresh,
}: {
  readonly message: string;
  readonly onRefresh: () => void;
}) {
  return (
    <div className="account-error" role="alert">
      <p>{message}</p>
      <button type="button" onClick={onRefresh}>
        повторить
      </button>
    </div>
  );
}

function countryName(countryCode: string): string {
  try {
    return (
      new Intl.DisplayNames(["ru"], { type: "region" }).of(countryCode) ??
      countryCode
    );
  } catch {
    return countryCode;
  }
}

function availabilityError(error: unknown): string {
  if (
    error instanceof ApiError &&
    (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT")
  ) {
    return "Не удалось обновить локации. Проверьте сеть и попробуйте снова.";
  }
  return "Не удалось обновить доступные локации. Попробуйте позже.";
}
