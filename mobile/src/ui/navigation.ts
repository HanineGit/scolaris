import { router } from "expo-router";

import type { Onglet } from "./composants";

const ROUTES: Record<Onglet, "/accueil" | "/notes" | "/reclamations" | "/compte"> = {
  accueil: "/accueil", notes: "/notes", reclamations: "/reclamations", compte: "/compte",
};

/** Changement d'onglet : remplace l'écran courant (pas d'empilement infini dans l'historique). */
export const allerA = (o: Onglet) => router.replace(ROUTES[o]);
