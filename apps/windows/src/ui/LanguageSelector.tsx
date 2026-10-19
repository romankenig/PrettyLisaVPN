import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { languages, languagePreference, t, useLanguage, type Language } from "../i18n";
import { CountryIcon } from "./CountryIcon";

export function LanguageSelector() {
  const language = useLanguage();
  const selected = languages.find((item) => item.code === language)!;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);
  function choose(code: Language) {
    languagePreference.choose(code);
    setOpen(false);
    trigger.current?.focus();
  }
  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Escape") { event.preventDefault(); setOpen(false); return; }
    if (event.key === "Tab") { setOpen(false); return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => open ? (value + (event.key === "ArrowDown" ? 1 : languages.length - 1)) % languages.length : languages.indexOf(selected));
      setOpen(true);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault(); setActive(event.key === "Home" ? 0 : languages.length - 1); setOpen(true);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) choose(languages[active].code);
      else { setActive(languages.indexOf(selected)); setOpen(true); }
    }
  }
  return (
    <div className="language-selector" ref={root} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      <button className="language-trigger" type="button" role="combobox" ref={trigger}
        aria-label={t("язык интерфейса")} title={t("выберите язык")}
        aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-list`}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        onKeyDown={keyDown} onClick={() => { setActive(languages.indexOf(selected)); setOpen(!open); }}>
        <CountryIcon code={selected.country} />
        <span className="language-names"><strong>{selected.english}</strong><small>{selected.native}</small></span>
        <span aria-hidden="true" className="language-chevron">⌃</span>
      </button>
      {open ? <div className="language-menu" role="listbox" id={`${id}-list`} aria-label={t("выберите язык")}>
        {languages.map((item, index) => <button key={item.code} type="button" role="option" tabIndex={-1}
          id={`${id}-${index}`} aria-selected={item.code === language} data-language={item.code}
          className={index === active ? "language-option is-active" : "language-option"}
          onPointerMove={() => setActive(index)} onClick={() => choose(item.code)}>
          <CountryIcon code={item.country} />
          <span className="language-names"><strong>{item.english}</strong><small>{item.native}</small></span>
          {item.code === language ? <span aria-hidden="true">✓</span> : null}
        </button>)}
      </div> : null}
    </div>
  );
}
