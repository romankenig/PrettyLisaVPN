import type { ReactNode } from "react";

/** Keep the product name intact when surrounding UI uses lowercase typography. */
export function ProductText({ text }: { readonly text: ReactNode }) {
  if (typeof text !== "string") return <>{text}</>;
  return (
    <>
      {text.split(/(PrettyLisaVPN)/g).map((part, index) =>
        part === "PrettyLisaVPN" ? (
          <span className="product-name" key={index}>
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}
