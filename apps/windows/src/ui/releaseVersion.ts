// Same display contract as Android: validated SemVer core from the actual API.
export function releaseVersion(raw: string): string | null {
  if (raw.length > 256) return null;
  const number = "(?:0|[1-9][0-9]*)";
  const identifier = "(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)";
  const version = new RegExp(
    `^(${number}\\.${number}\\.${number})(?:-${identifier}(?:\\.${identifier})*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$`,
  ).exec(raw);
  return version?.[0] === raw && version[1].length <= 20 ? version[1] : null;
}
