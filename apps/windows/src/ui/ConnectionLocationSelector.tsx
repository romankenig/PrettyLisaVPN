import { t, useLanguage, getLanguage } from "../i18n";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { ApiError, type VpnCountriesResponse } from "../api/client";
import { useApplication } from "../state/application";
import type { VpnLocationSelection } from "../vpn/selection";
import { CountryIcon } from "./CountryIcon";

const AVAILABILITY_MAX_AGE_MS = 60_000;
type AvailabilityState =
  | { readonly phase: "loading" }
  | {
      readonly phase: "ready" | "refreshing" | "stale";
      readonly data: VpnCountriesResponse;
      readonly message?: string;
    }
  | { readonly phase: "error"; readonly message: string };
type Choice = {
  readonly key: string;
  readonly selection: VpnLocationSelection;
  readonly name: string;
  readonly quality: number;
  readonly available: boolean;
};

export function ConnectionLocationSelector({
  selection,
  onSelectionChange,
  onConnectabilityChange,
  disabled = false,
}: {
  readonly selection: VpnLocationSelection;
  readonly onSelectionChange: (selection: VpnLocationSelection) => void;
  readonly onConnectabilityChange: (available: boolean) => void;
  readonly disabled?: boolean;
}) {
  useLanguage();
  const { api, session } = useApplication();
  const activeSession = session.current();
  const [state, setState] = useState<AvailabilityState>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();

  useEffect(() => {
    if (!activeSession) return;
    const controller = new AbortController();
    setState((current) =>
      "data" in current
        ? { phase: "refreshing", data: current.data }
        : { phase: "loading" },
    );
    void api
      .listVpnCountries(activeSession.accessToken, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ phase: "ready", data });
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
      () => setAttempt((value) => value + 1),
      AVAILABILITY_MAX_AGE_MS,
    );
    return () => globalThis.clearTimeout(timer);
  }, [state]);

  useEffect(() => {
    if (state.phase !== "ready" || selection.mode !== "COUNTRY" || disabled)
      return;
    if (
      !state.data.countries.some(
        (country) =>
          country.country_code === selection.country_code && country.available,
      )
    ) {
      onSelectionChange({ mode: "AUTO" });
    }
  }, [disabled, onSelectionChange, selection, state]);

  useEffect(() => {
    onConnectabilityChange(
      state.phase === "ready" &&
        (selection.mode === "AUTO"
          ? state.data.autopilot.available
          : state.data.countries.some(
              (country) =>
                country.country_code === selection.country_code &&
                country.available,
            )),
    );
  }, [onConnectabilityChange, selection, state]);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  useEffect(() => {
    if (open)
      document
        .getElementById(`${id}-${active}`)
        ?.scrollIntoView?.({ block: "nearest" });
  }, [active, id, open]);

  const countries =
    "data" in state
      ? state.data.countries
          .filter((country) => country.available)
          .map((country): Choice => ({
            key: country.country_code,
            selection: { mode: "COUNTRY", country_code: country.country_code },
            name: countryName(country.country_code),
            quality: country.quality,
            available: true,
          }))
          .sort((a, b) => a.name.localeCompare(b.name, getLanguage()))
      : [];
  const top = [...countries]
    .sort(
      (a, b) =>
        b.quality - a.quality || a.name.localeCompare(b.name, getLanguage()),
    )
    .slice(0, 3);
  const autopilot: Choice = {
    key: "auto",
    selection: { mode: "AUTO" },
    name: "автопилот",
    quality: "data" in state ? state.data.autopilot.quality : 0,
    available: "data" in state && state.data.autopilot.available,
  };
  const groups = [
    { name: "автопилот", choices: [autopilot] },
    { name: "топ", choices: top },
    { name: "все страны", choices: countries },
  ];
  const choices = groups.flatMap((group) => group.choices);
  const selected =
    selection.mode === "AUTO"
      ? autopilot
      : (countries.find(
          (choice) =>
            choice.selection.mode === "COUNTRY" &&
            choice.selection.country_code === selection.country_code,
        ) ?? autopilot);
  const usable = !disabled && state.phase === "ready";
  const expanded = open && usable;
  function choose(choice: Choice) {
    if (!usable || !choice.available) return;
    onSelectionChange(choice.selection);
    setOpen(false);
    trigger.current?.focus();
  }
  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (!usable) return;
    const enabled = choices
      .map((choice, index) => (choice.available ? index : -1))
      .filter((index) => index >= 0);
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      setOpen(true);
      if (!enabled.length) return;
      if (event.key === "Home") setActive(enabled[0]);
      else if (event.key === "End") setActive(enabled[enabled.length - 1]);
      else {
        const current = enabled.indexOf(active);
        const next = !expanded
          ? event.key === "ArrowUp"
            ? enabled.length - 1
            : 0
          : (current + (event.key === "ArrowUp" ? -1 : 1) + enabled.length) %
            enabled.length;
        setActive(enabled[next]);
      }
    } else if ((event.key === "Enter" || event.key === " ") && expanded) {
      event.preventDefault();
      if (choices[active]) choose(choices[active]);
    } else if (event.key.length === 1 && event.key !== " ") {
      const index = choices.findIndex(
        (choice) =>
          choice.available &&
          choice.name
            .toLocaleLowerCase("ru")
            .startsWith(event.key.toLocaleLowerCase("ru")),
      );
      if (index >= 0) {
        event.preventDefault();
        setOpen(true);
        setActive(index);
      }
    }
  }
  let index = 0;
  return (
    <div
      className="location-selector"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <div className="location-selector__heading">
        <h2 id={`${id}-title`}>{t("куда подключиться")}</h2>
        <button
          type="button"
          className="location-refresh"
          aria-label={t("обновить страны")}
          title={t("обновить страны")}
          disabled={
            disabled ||
            state.phase === "refreshing" ||
            state.phase === "loading"
          }
          onClick={() => {
            setOpen(false);
            setAttempt((value) => value + 1);
          }}
        >
          ↻
        </button>
      </div>
      <button
        ref={trigger}
        type="button"
        role="combobox"
        className="location-trigger"
        aria-labelledby={`${id}-title ${id}-selection`}
        aria-controls={`${id}-list`}
        aria-expanded={expanded}
        aria-haspopup="listbox"
        aria-activedescendant={expanded ? `${id}-${active}` : undefined}
        disabled={!usable}
        onKeyDown={keyDown}
        onClick={() => {
          setOpen(!expanded);
          const selectedIndex = choices.indexOf(selected);
          setActive(Math.max(0, selectedIndex));
        }}
      >
        <ChoiceLabel choice={selected} id={`${id}-selection`} />
        <span className="location-chevron" aria-hidden="true">
          ⌄
        </span>
      </button>
      {expanded ? (
        <div
          className="location-dropdown"
          id={`${id}-list`}
          role="listbox"
          aria-labelledby={`${id}-title`}
        >
          {groups.map((group) => (
            <div role="group" aria-label={t(group.name)} key={group.name}>
              <p className="location-group-label" aria-hidden="true">
                {t(group.name)}
              </p>
              {group.choices.length ? (
                group.choices.map((choice) => {
                  const optionIndex = index++;
                  return (
                    <button
                      type="button"
                      role="option"
                      id={`${id}-${optionIndex}`}
                      key={choice.key}
                      className={`location-option${active === optionIndex ? " location-option--active" : ""}`}
                      aria-selected={selected.key === choice.key}
                      disabled={!choice.available}
                      tabIndex={-1}
                      onMouseDown={(event) => event.preventDefault()}
                      onMouseEnter={() => setActive(optionIndex)}
                      onClick={() => choose(choice)}
                    >
                      <ChoiceLabel choice={choice} />
                    </button>
                  );
                })
              ) : (
                <p className="location-empty">{t("нет доступных стран")}</p>
              )}
            </div>
          ))}
        </div>
      ) : null}
      {state.phase === "loading" || state.phase === "refreshing" ? (
        <p className="availability-note" role="status">
          {t("загружаем доступные локации…")}
        </p>
      ) : null}
      {state.phase === "error" || state.phase === "stale" ? (
        <p className="availability-warning" role="alert">
          {t(state.message)}
          {t(" ")}
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            {t("повторить")}
          </button>
        </p>
      ) : null}
    </div>
  );
}

function ChoiceLabel({
  choice,
  id,
}: {
  readonly choice: Choice;
  readonly id?: string;
}) {
  useLanguage();
  return (
    <>
      <CountryIcon
        code={
          choice.selection.mode === "COUNTRY"
            ? choice.selection.country_code
            : null
        }
      />
      <span className="location-option__name" id={id}>
        {t(choice.name)}
      </span>
      <span
        className="location-option__quality"
        aria-label={t(`доступность ${choice.quality} из 100`)}
      >
        {t(choice.quality)}
      </span>
    </>
  );
}

export function countryName(countryCode: string): string {
  try {
    return (
      new Intl.DisplayNames([getLanguage()], { type: "region" }).of(
        countryCode,
      ) ?? countryCode
    );
  } catch {
    return countryCode;
  }
}

function availabilityError(error: unknown): string {
  return error instanceof ApiError &&
    (error.code === "NETWORK_ERROR" || error.code === "TIMEOUT")
    ? "Не удалось обновить локации. Проверьте сеть и попробуйте снова."
    : "Не удалось обновить доступные локации. Попробуйте позже.";
}
