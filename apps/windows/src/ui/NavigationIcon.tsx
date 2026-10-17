export function NavigationIcon({
  name,
}: {
  readonly name:
    "home" | "settings" | "about" | "devices" | "subscription" | "logout";
}) {
  const paths = {
    home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
    settings:
      "m10 3-1 3-3 1-3-1-1 4 2 2-1 3 2 3 3-1 2 2h4l1-3 3-1 3 1 1-4-2-2 1-3-2-3-3 1-2-2Z",
    about: "M12 11v6m0-10h.01",
    devices: "M3 4h18v12H3ZM8 21h8m-4-5v5",
    subscription: "M3 5h18v14H3ZM3 9h18M7 15h3",
    logout: "M9 4H4v16h5m4-4 4-4-4-4m-5 4h13",
  };
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {name === "about" ? <circle cx="12" cy="12" r="9" /> : null}
      {name === "settings" ? <circle cx="12" cy="12" r="3" /> : null}
      <path d={paths[name]} />
    </svg>
  );
}
