import wordmark from "../../../assets/enter-wordmark.webp";
import symbol from "../../../assets/enter-symbol.webp";

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
};

export function Icon({ name, className = "" }) {
  return <svg className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name] || paths.files} /></svg>;
}
