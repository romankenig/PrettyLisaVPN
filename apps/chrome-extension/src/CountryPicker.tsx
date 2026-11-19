import { useEffect, useId, useRef, useState } from "react";
import { translate, type Language } from "./i18n";
import type { Country } from "./model";

export function countryName(code: string | null, language: Language) {
  return code && /^[A-Z]{2}$/.test(code)
    ? (new Intl.DisplayNames([language], { type: "region" }).of(code) ?? code)
    : translate("unavailable", language);
}

export function CountryLabel({
  code,
  language,
}: {
  code: string | null;
  language: Language;
}) {
  return (
    <span className="country-label">
      {code && /^[A-Z]{2}$/.test(code) && (
        <svg
          className="country-flag"
          width="20"
          height="20"
          viewBox="0 0 512 512"
          aria-hidden="true"
        >
          <use href={`flags/countries.svg#${code.toLowerCase()}`} />
        </svg>
      )}
      <span>{countryName(code, language)}</span>
    </span>
  );
}

export function CountryPicker({
  value,
  countries,
  language,
  disabled,
  onChange,
}: {
  value: string;
  countries: Country[];
  language: Language;
  disabled: boolean;
  onChange(value: string): void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [above, setAbove] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const options = [{ country_code: "AUTO", available: true }, ...countries];
  const shown = open && !disabled;
  const selected = Math.max(
    0,
    options.findIndex((option) => option.country_code === value),
  );
  useEffect(() => {
    if (!shown) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [shown]);
  const choose = (index: number) => {
    const option = options[index];
    if (!option?.available) return;
    onChange(option.country_code);
    setOpen(false);
    trigger.current?.focus();
  };
  const expand = (index: number) => {
    const rect = root.current?.getBoundingClientRect();
    const height = Math.min(230, options.length * 44 + 12);
    setAbove(
      !!rect && window.innerHeight - rect.bottom < height && rect.top > height,
    );
    setActive(index);
    setOpen(true);
  };
  const label = (code: string) =>
    code === "AUTO" ? (
      translate("auto", language)
    ) : (
      <CountryLabel code={code} language={language} />
    );
  return (
    <div
      className="country-picker"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <button
        type="button"
        className="country"
        ref={trigger}
        role="combobox"
        aria-label={translate("destination", language)}
        aria-haspopup="listbox"
        aria-expanded={shown}
        aria-controls={id}
        aria-activedescendant={shown ? `${id}-${active}` : undefined}
        disabled={disabled}
        onClick={() => {
          if (shown) setOpen(false);
          else expand(selected);
        }}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            const enabled = options
              .map((option, index) => (option.available ? index : -1))
              .filter((index) => index >= 0);
            const position = enabled.indexOf(shown ? active : selected);
            const next =
              event.key === "Home"
                ? enabled[0]
                : event.key === "End"
                  ? enabled.at(-1)!
                  : enabled[
                      (position +
                        (event.key === "ArrowDown" ? 1 : -1) +
                        enabled.length) %
                        enabled.length
                    ];
            if (shown) setActive(next);
            else expand(next);
          } else if (event.key === "Escape") {
            event.preventDefault();
            setOpen(false);
          } else if (shown && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            choose(active);
          }
        }}
      >
        {label(value)}
        <span aria-hidden="true">⌄</span>
      </button>
      {shown && (
        <div
          id={id}
          className={`country-options${above ? " above" : ""}`}
          role="listbox"
          aria-label={translate("destination", language)}
        >
          {options.map((option, index) => (
            <button
              key={option.country_code}
              id={`${id}-${index}`}
              type="button"
              role="option"
              tabIndex={-1}
              aria-selected={value === option.country_code}
              disabled={!option.available}
              className={active === index ? "highlighted" : ""}
              onClick={() => choose(index)}
            >
              {label(option.country_code)}
              {!option.available && (
                <small>{translate("unavailable", language)}</small>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
