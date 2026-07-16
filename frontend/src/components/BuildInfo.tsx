import { BUILD_INFO } from "../config/brand";

export function BuildInfo({ compact = false }: { compact?: boolean }) {
  const shortSha = BUILD_INFO.commitSha === "unknown" ? "unknown" : BUILD_INFO.commitSha.slice(0, 8);
  if (compact) {
    return <span className="build-info">v{BUILD_INFO.version} · {shortSha}</span>;
  }
  return (
    <dl className="build-details">
      <div><dt>Версия</dt><dd>{BUILD_INFO.version}</dd></div>
      <div><dt>Commit</dt><dd>{shortSha}</dd></div>
      <div><dt>Дата сборки</dt><dd>{BUILD_INFO.buildDate}</dd></div>
    </dl>
  );
}
