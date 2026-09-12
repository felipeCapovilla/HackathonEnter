import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
// Newsreader: face de display. Serifada de propósito — dá o peso editorial que
// um produto jurídico pede e separa o que se LÊ do que se OPERA, papel que o
// Inter sozinho não conseguia marcar.
import "@fontsource-variable/newsreader";
import "./styles.css";

createRoot(document.getElementById("root")).render(<BrowserRouter><App /></BrowserRouter>);

