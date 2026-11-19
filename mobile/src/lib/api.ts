/**
 * Client de l'API pour l'application étudiante.
 *
 * - Jeton d'accès (15 min) en mémoire uniquement.
 * - Jeton de rafraîchissement dans le coffre du système (Keystore / Keychain)
 *   via expo-secure-store ; jamais dans AsyncStorage, qui n'est pas chiffré.
 * - Aucune note n'est écrite sur le téléphone : les données restent en mémoire.
 * - L'identité de l'étudiant n'est jamais envoyée : le serveur la lit dans le jeton.
 */
import * as SecureStore from "expo-secure-store";

import { API_URL } from "./config";
import { appelsAutorises } from "./pinning";

const CLE_RAFRAICHISSEMENT = "scolaris.rafraichissement";
const OPTIONS_COFFRE: SecureStore.SecureStoreOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

export interface Utilisateur { id: string; identifiant: string; role: string; nom: string | null; prenom: string | null }
interface Jetons { jeton_acces: string; jeton_rafraichissement: string; expire_dans: number; utilisateur: Utilisateur }

export class ErreurApi extends Error {
  constructor(public statut: number, public code: string, message: string) {
    super(message);
  }
}

let jetonAcces: string | null = null;
let expireA = 0;
let enCours: Promise<Utilisateur | null> | null = null;
let surExpiration: (() => void) | null = null;

export function quandSessionExpire(fn: () => void) {
  surExpiration = fn;
}

async function brut(methode: string, chemin: string, corps?: unknown, jeton?: string | null): Promise<Response> {
  if (!appelsAutorises()) {
    throw new ErreurApi(0, "EPINGLAGE", "Connexion sécurisée impossible : le certificat du serveur ne peut pas être vérifié.");
  }
  const entetes: Record<string, string> = { Accept: "application/json" };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  if (jeton) entetes.Authorization = `Bearer ${jeton}`;
  try {
    return await fetch(API_URL + chemin, {
      method: methode, headers: entetes, body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch {
    // Erreur réseau ou certificat refusé par l'épinglage : message générique.
    throw new ErreurApi(0, "RESEAU", "Serveur injoignable. Vérifiez votre connexion internet.");
  }
}

async function erreur(r: Response): Promise<ErreurApi> {
  try {
    const e = (await r.json())?.erreur ?? {};
    return new ErreurApi(r.status, e.code ?? `E${r.status}`, e.message ?? "Une erreur est survenue.");
  } catch {
    return new ErreurApi(r.status, `E${r.status}`, r.status === 429 ? "Trop de tentatives. Réessayez dans une minute." : "Une erreur est survenue.");
  }
}

async function ouvrir(j: Jetons): Promise<Utilisateur> {
  jetonAcces = j.jeton_acces;
  expireA = Date.now() + j.expire_dans * 1000;
  await SecureStore.setItemAsync(CLE_RAFRAICHISSEMENT, j.jeton_rafraichissement, OPTIONS_COFFRE);
  return j.utilisateur;
}

export async function fermer(): Promise<void> {
  jetonAcces = null;
  expireA = 0;
  await SecureStore.deleteItemAsync(CLE_RAFRAICHISSEMENT, OPTIONS_COFFRE).catch(() => undefined);
}

export async function connecter(identifiant: string, motDePasse: string): Promise<Utilisateur> {
  const r = await brut("POST", "/auth/connexion", { identifiant, mot_de_passe: motDePasse });
  if (r.status === 401) throw new ErreurApi(401, "IDENTIFIANTS", "Matricule ou mot de passe incorrect.");
  if (!r.ok) throw await erreur(r);
  const corps = await r.json();
  if (corps.mfa_requis || corps.utilisateur?.role !== "ETUDIANT") {
    // L'application est réservée aux étudiants ; le personnel utilise le back-office web.
    if (corps.jeton_acces) await brut("POST", "/auth/deconnexion", { jeton_rafraichissement: corps.jeton_rafraichissement }, corps.jeton_acces).catch(() => undefined);
    throw new ErreurApi(403, "ROLE", "Cette application est réservée aux étudiants. Le personnel utilise l'espace web.");
  }
  return ouvrir(corps);
}

/** Renouvelle la session à partir du jeton du coffre (rotation : l'ancien jeton devient inutilisable). */
export async function reprendre(): Promise<Utilisateur | null> {
  enCours ??= (async () => {
    try {
      const jeton = await SecureStore.getItemAsync(CLE_RAFRAICHISSEMENT, OPTIONS_COFFRE);
      if (!jeton) return null;
      const r = await brut("POST", "/auth/rafraichir", { jeton_rafraichissement: jeton });
      if (!r.ok) {
        if (r.status === 401) await fermer();
        return null;
      }
      return await ouvrir(await r.json());
    } finally {
      enCours = null;
    }
  })();
  return enCours;
}

async function authentifie(methode: string, chemin: string, corps?: unknown): Promise<Response> {
  if (!jetonAcces || Date.now() > expireA - 60_000) {
    if (!(await reprendre())) {
      surExpiration?.();
      throw new ErreurApi(401, "SESSION", "Votre session a expiré. Reconnectez-vous.");
    }
  }
  let r = await brut(methode, chemin, corps, jetonAcces);
  if (r.status === 401 && (await reprendre())) r = await brut(methode, chemin, corps, jetonAcces);
  if (r.status === 401) {
    await fermer();
    surExpiration?.();
    throw new ErreurApi(401, "SESSION", "Votre session a expiré. Reconnectez-vous.");
  }
  if (!r.ok) throw await erreur(r);
  return r;
}

export async function appel<T>(chemin: string, methode = "GET", corps?: unknown): Promise<T> {
  const r = await authentifie(methode, chemin, methode === "GET" ? undefined : (corps ?? {}));
  return (r.status === 204 ? undefined : await r.json()) as T;
}

/** Fichier binaire (relevé PDF) : octets et en-têtes utiles, jamais écrits par cette fonction. */
export async function fichier(chemin: string): Promise<{ octets: Uint8Array; code: string | null }> {
  const r = await authentifie("GET", chemin);
  return { octets: new Uint8Array(await r.arrayBuffer()), code: r.headers.get("x-code-verification") };
}

export async function deconnecter(): Promise<void> {
  const jeton = await SecureStore.getItemAsync(CLE_RAFRAICHISSEMENT, OPTIONS_COFFRE).catch(() => null);
  if (jeton && jetonAcces) await brut("POST", "/auth/deconnexion", { jeton_rafraichissement: jeton }, jetonAcces).catch(() => undefined);
  await fermer();
}

export async function verifierActivation(jeton: string) {
  const r = await brut("POST", "/auth/activation/verifier", { jeton });
  if (!r.ok) throw await erreur(r);
  return (await r.json()) as { identifiant: string; role: string; expire_le: string; mfa_requis: boolean };
}

export async function activer(jeton: string, motDePasse: string, confirmation: string) {
  const r = await brut("POST", "/auth/activation", { jeton, mot_de_passe: motDePasse, confirmation });
  if (!r.ok) throw await erreur(r);
}
