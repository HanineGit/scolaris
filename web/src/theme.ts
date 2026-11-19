import { useEffect, useState } from "react";

/* Thème clair ou sombre : préférence du système par défaut, choix de l'utilisateur mémorisé
   dans ce navigateur (simple confort d'affichage, aucune donnée sensible). */
export type Theme = "light" | "dark";
const CLE = "scolaris.theme";

function lire(): Theme | null {
  try {
    const v = localStorage.getItem(CLE);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function systeme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Appliqué avant le premier rendu (main.tsx) pour éviter un éclair du mauvais thème. */
export function appliquerTheme(theme: Theme | null = lire()) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => lire() ?? systeme());
  useEffect(() => {
    appliquerTheme(theme);
    try {
      localStorage.setItem(CLE, theme);
    } catch {
      /* stockage indisponible : le choix vaut pour la session en cours */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}
