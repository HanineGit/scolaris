import Constants from "expo-constants";

/** Configuration publique (aucun secret) lue dans app.json → expo.extra. */
interface Extra {
  apiUrl: string;
  /** Empreintes SHA-256 (base64) des clés publiques TLS acceptées : clé active et clé de secours. */
  empreintesTls: string[];
}

const extra = (Constants.expoConfig?.extra ?? {}) as Partial<Extra>;

export const API_URL = extra.apiUrl ?? "https://localhost:9443/api/v1";
export const HOTE_API = new URL(API_URL).hostname;
export const EMPREINTES_TLS = extra.empreintesTls ?? [];

/** Inactivité au-delà de laquelle la session est fermée, comme côté serveur. */
export const INACTIVITE_MAX_MS = 15 * 60 * 1000;
