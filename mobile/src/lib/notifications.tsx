/**
 * Centre de notifications de l'étudiant (F28).
 *
 * Choix de sécurité : aucun service de « push » tiers. L'application interroge le serveur
 * Scolaris lorsqu'elle est ouverte (puis toutes les minutes) et affiche une notification
 * locale pour chaque nouveauté. Le texte ne contient jamais de note : il invite seulement
 * à ouvrir l'application, où les droits sont vérifiés.
 */
import * as Notifications from "expo-notifications";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AppState, Platform } from "react-native";

import { notifications as lire, type Notification } from "./donnees";

Notifications.setNotificationHandler({
  handleNotification: async () => ({ shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false }),
});

interface Etat { nonLues: number; elements: Notification[]; recharger: () => void }
const Contexte = createContext<Etat>({ nonLues: 0, elements: [], recharger: () => undefined });

export function FournisseurNotifications({ children }: { children: ReactNode }) {
  const [etat, setEtat] = useState<{ nonLues: number; elements: Notification[] }>({ nonLues: 0, elements: [] });
  const dejaVues = useRef<Set<string> | null>(null);
  const autorise = useRef(false);

  useEffect(() => {
    void (async () => {
      if (Platform.OS === "android") {
        await Notifications.setNotificationChannelAsync("scolaris", { name: "Scolaris", importance: Notifications.AndroidImportance.DEFAULT });
      }
      const { status } = await Notifications.requestPermissionsAsync();
      autorise.current = status === "granted";
    })();
  }, []);

  const recharger = useCallback(() => {
    lire().then((d) => {
      setEtat({ nonLues: d.non_lues, elements: d.elements });
      // Au premier chargement, on mémorise l'existant sans alerter ; ensuite, seules les nouveautés sont signalées.
      if (dejaVues.current === null) {
        dejaVues.current = new Set(d.elements.map((n) => n.id));
        return;
      }
      for (const n of d.elements) {
        if (!n.lue && !dejaVues.current.has(n.id) && autorise.current) {
          void Notifications.scheduleNotificationAsync({ content: { title: n.titre, body: n.message }, trigger: null });
        }
        dejaVues.current.add(n.id);
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    recharger();
    let minuterie = setInterval(recharger, 60_000);
    const abonnement = AppState.addEventListener("change", (s) => {
      clearInterval(minuterie);
      if (s === "active") {
        recharger();
        minuterie = setInterval(recharger, 60_000);
      }
    });
    return () => { clearInterval(minuterie); abonnement.remove(); };
  }, [recharger]);

  return <Contexte.Provider value={{ ...etat, recharger }}>{children}</Contexte.Provider>;
}

export const useNotifications = () => useContext(Contexte);
