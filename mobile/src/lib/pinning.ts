/**
 * Épinglage de la clé publique du certificat du serveur (risque R21).
 *
 * Avec un proxy d'interception, même muni d'un certificat « de confiance »,
 * l'application refuse la connexion. En version publiée, l'absence du module
 * natif ou d'empreintes bloque tout appel (échec sécurisé). En développement
 * (Expo Go), l'épinglage est seulement signalé comme inactif.
 */
import { EMPREINTES_TLS, HOTE_API } from "./config";

let etat: "actif" | "inactif-dev" | "impossible" = "impossible";

export async function initialiserEpinglage(): Promise<void> {
  try {
    const module = await import("react-native-ssl-public-key-pinning");
    if (!module.isSslPinningAvailable() || EMPREINTES_TLS.length < 2) throw new Error("indisponible");
    await module.initializeSslPinning({
      [HOTE_API]: { includeSubdomains: false, publicKeyHashes: EMPREINTES_TLS },
    });
    etat = "actif";
  } catch {
    etat = __DEV__ ? "inactif-dev" : "impossible";
  }
}

export function appelsAutorises(): boolean {
  return etat !== "impossible";
}

export function etatEpinglage() {
  return etat;
}
