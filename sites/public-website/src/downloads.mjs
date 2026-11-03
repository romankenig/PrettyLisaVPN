// Binary/source URLs are fixed allowlisted paths. Ignore redirect URLs in metadata.
export function releaseMetadata(index, platform, language = "en") {
  if (!["android", "windows"].includes(platform) || index?.schema !== 1)
    return null;
  const data = index.clients?.[platform];
  if (
    !data ||
    !/^\d+\.\d+\.\d+$/.test(data.version) ||
    !/^[a-f0-9]{64}$/.test(data.sha256) ||
    !Number.isSafeInteger(data.bytes) ||
    data.bytes <= 0
  )
    return null;
  return {
    version: data.version,
    size: new Intl.NumberFormat(language, {
      style: "unit",
      unit: "megabyte",
      maximumFractionDigits: 1,
    }).format(data.bytes / 1_000_000),
    sha256: data.sha256,
  };
}
