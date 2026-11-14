import { useEffect, useRef, useState } from "react";
import { languages, translate, type Language } from "./i18n";

export function LanguagePicker({
  language,
  onChange,
}: {
  language: Language;
  onChange(value: Language): void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const current = languages.find((item) => item.code === language)!;
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return (
    <div
      className="language-picker"
      ref={root}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          trigger.current?.focus();
        }
      }}
    >
      <button
        ref={trigger}
        className="language-trigger"
        aria-label={translate("language", language)}
        aria-expanded={open}
        aria-controls="language-options"
        onClick={() => setOpen(!open)}
      >
        <img src={`flags/${current.flag}.svg`} alt="" width="18" height="18" />
        <span>{language}</span>
      </button>
      {open && (
        <div
          id="language-options"
          className="language-options"
          role="group"
          aria-label={translate("language", language)}
        >
          {languages.map((item) => (
            <button
              key={item.code}
              lang={item.code}
              aria-pressed={language === item.code}
              onClick={() => {
                onChange(item.code);
                setOpen(false);
                trigger.current?.focus();
              }}
            >
              <img
                src={`flags/${item.flag}.svg`}
                alt=""
                width="18"
                height="18"
              />
              {item.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
