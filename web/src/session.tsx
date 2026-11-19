import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import {
  deconnecter, fermerSession, ouvrirSession, quandSessionExpire, rafraichir, secondesAvantExpiration,
  type Jetons, type Utilisateur,
} from "./api";

/** Durée d'inactivité au-delà de laquelle la session est fermée (identique au serveur). */
export const INACTIVITE_MAX_S = 15 * 60;

interface Session {
  utilisateur: Utilisateur | null;
  minutesRestantes: number;
  messageFin: string | null;
  connecter: (j: Jetons) => void;
  quitter: (message?: string) => Promise<void>;
  effacerMessage: () => void;
}

const Contexte = createContext<Session | null>(null);

export function FournisseurSession({ children }: { children: ReactNode }) {
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null);
  const [messageFin, setMessageFin] = useState<string | null>(null);
  const [restant, setRestant] = useState(INACTIVITE_MAX_S);
  const derniereActivite = useRef(Date.now());

  const quitter = useCallback(async (message?: string) => {
    await deconnecter();
    setUtilisateur(null);
    setMessageFin(message ?? null);
  }, []);

  const connecter = useCallback((j: Jetons) => {
    ouvrirSession(j);
    derniereActivite.current = Date.now();
    setUtilisateur(j.utilisateur);
    setMessageFin(null);
  }, []);

  useEffect(() => {
    quandSessionExpire(() => {
      fermerSession();
      setUtilisateur(null);
      setMessageFin("Votre session a expiré. Veuillez vous reconnecter.");
    });
  }, []);

  // Suivi de l'activité : toute interaction repousse la fin de session et,
  // si le jeton d'accès arrive à échéance, déclenche son renouvellement.
  useEffect(() => {
    if (!utilisateur) return;
    let dernierSignal = 0;
    const activite = () => {
      const t = Date.now();
      if (t - dernierSignal < 5000) return;
      dernierSignal = t;
      derniereActivite.current = t;
      if (secondesAvantExpiration() < 180) void rafraichir();
    };
    const evenements = ["mousedown", "keydown", "scroll", "touchstart"];
    evenements.forEach((e) => window.addEventListener(e, activite, { passive: true }));
    const minuterie = window.setInterval(() => {
      const ecoule = (Date.now() - derniereActivite.current) / 1000;
      const reste = Math.max(0, INACTIVITE_MAX_S - ecoule);
      setRestant(reste);
      if (reste <= 0) void quitter("Session fermée après 15 minutes d'inactivité.");
    }, 1000);
    return () => {
      evenements.forEach((e) => window.removeEventListener(e, activite));
      window.clearInterval(minuterie);
    };
  }, [utilisateur, quitter]);

  return (
    <Contexte.Provider value={{
      utilisateur, minutesRestantes: Math.ceil(restant / 60), messageFin, connecter, quitter,
      effacerMessage: () => setMessageFin(null),
    }}>
      {children}
    </Contexte.Provider>
  );
}

export function useSession(): Session {
  const s = useContext(Contexte);
  if (!s) throw new Error("FournisseurSession manquant");
  return s;
}
