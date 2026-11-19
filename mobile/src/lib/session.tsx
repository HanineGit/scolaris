import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AppState } from "react-native";

import { connecter as apiConnecter, deconnecter, fermer, quandSessionExpire, reprendre, type Utilisateur } from "./api";
import { INACTIVITE_MAX_MS } from "./config";

interface Session {
  utilisateur: Utilisateur | null;
  pret: boolean;
  messageFin: string | null;
  connecter: (identifiant: string, mdp: string) => Promise<void>;
  quitter: (message?: string) => Promise<void>;
  signalerActivite: () => void;
}

const Contexte = createContext<Session | null>(null);

export function FournisseurSession({ children }: { children: ReactNode }) {
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null);
  const [pret, setPret] = useState(false);
  const [messageFin, setMessageFin] = useState<string | null>(null);
  const derniereActivite = useRef(Date.now());

  const quitter = useCallback(async (message?: string) => {
    await deconnecter();
    setUtilisateur(null);
    setMessageFin(message ?? null);
  }, []);

  // Au démarrage : reprise de session si le coffre contient un jeton encore valide.
  useEffect(() => {
    quandSessionExpire(() => { setUtilisateur(null); setMessageFin("Votre session a expiré. Reconnectez-vous."); });
    reprendre().then((u) => setUtilisateur(u)).catch(() => undefined).finally(() => setPret(true));
  }, []);

  // Retour au premier plan après plus de 15 minutes : la session est fermée.
  useEffect(() => {
    const abonnement = AppState.addEventListener("change", (etat) => {
      if (etat === "active" && utilisateur && Date.now() - derniereActivite.current > INACTIVITE_MAX_MS) {
        void fermer().then(() => { setUtilisateur(null); setMessageFin("Session fermée après 15 minutes d'inactivité."); });
      }
    });
    const minuterie = setInterval(() => {
      if (utilisateur && Date.now() - derniereActivite.current > INACTIVITE_MAX_MS) {
        void quitter("Session fermée après 15 minutes d'inactivité.");
      }
    }, 30_000);
    return () => { abonnement.remove(); clearInterval(minuterie); };
  }, [utilisateur, quitter]);

  const connecter = useCallback(async (identifiant: string, mdp: string) => {
    const u = await apiConnecter(identifiant, mdp);
    derniereActivite.current = Date.now();
    setMessageFin(null);
    setUtilisateur(u);
  }, []);

  return (
    <Contexte.Provider value={{
      utilisateur, pret, messageFin, connecter, quitter,
      signalerActivite: () => { derniereActivite.current = Date.now(); },
    }}>
      {children}
    </Contexte.Provider>
  );
}

export function useSession() {
  const s = useContext(Contexte);
  if (!s) throw new Error("FournisseurSession manquant");
  return s;
}
