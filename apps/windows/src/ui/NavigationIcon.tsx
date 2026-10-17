export function NavigationIcon({
  name,
}: {
  readonly name:
    "home" | "settings" | "about" | "devices" | "subscription" | "logout";
}) {
  const paths = {
    home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
    settings:
      "M9.13 5.071L9.921 2.219L14.079 2.219L14.87 5.071L14.87 5.071L17.446 3.613L20.387 6.554L18.929 9.13L18.929 9.13L21.781 9.921L21.781 14.079L18.929 14.87L18.929 14.87L20.387 17.446L17.446 20.387L14.87 18.929L14.87 18.929L14.079 21.781L9.921 21.781L9.13 18.929L9.13 18.929L6.554 20.387L3.613 17.446L5.071 14.87L5.071 14.87L2.219 14.079L2.219 9.921L5.071 9.13L5.071 9.13L3.613 6.554L6.554 3.613L9.13 5.071Z",
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
