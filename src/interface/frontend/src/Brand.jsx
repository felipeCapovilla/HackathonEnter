import wordmark from "../../../assets/enter-wordmark.svg";
import symbol from "../../../assets/enter-symbol.svg";

export function Brand({ compact = false }) {
  return <img className={compact ? "brand-symbol" : "brand-wordmark"} src={compact ? symbol : wordmark} alt="Enter" />;
}

const paths = {
  files: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9M14 3v6h6M14 3l6 6M8 13h8M8 17h5",
  chart: "M4 20V12h4v8H4Zm6 0V8h4v12h-4Zm6 0V4h4v16h-4Z",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  logout: "M9 5H5v14h4M12 12h9m-4-4 4 4-4 4",
  check: "m5 12 4 4L19 6",
  shield: "M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Zm-4 9 3 3 5-6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  trash: "M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3",
  trophy: "M8 21h8m-4-4v4M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4v2a3 3 0 0 0 3 3M17 6h3v2a3 3 0 0 1-3 3",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2",
  archive: "M3 8h18v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8ZM3 8V5a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v3M10 12h4",
  scale: "M12 4v16M7 20h10M12 6 6 9m6-3 6 3M6 9l-3 5a3 3 0 0 0 6 0L6 9Zm12 0-3 5a3 3 0 0 0 6 0l-3-5Z",
  lock: "M5 11h14v10H5V11Zm3 0V7a4 4 0 0 1 8 0v4M12 15v2",
};

export function Icon({ name, className = "" }) {
  return <svg className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name] || paths.files} /></svg>;
}
