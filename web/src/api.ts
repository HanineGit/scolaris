/**
 * Client de l'API Scolaris.
 *
 * Sécurité :
 * - les jetons sont conservés en mémoire uniquement (jamais dans localStorage
 *   ni dans un cookie lisible par script) : recharger la page ferme la session ;
 * - le jeton d'accès (15 min) est renouvelé par rotation du jeton de
 *   rafraîchissement ; un jeton réutilisé révoque toute la session côté serveur ;
 * - les messages d'erreur affichés sont ceux, génériques, renvoyés par l'API.
 */
export type Role = "ETUDIANT" | "ENSEIGNANT" | "ADMINISTRATEUR";

export interface Utilisateur {
  id: string;
  identifiant: string;
  role: Role;
  nom: string | null;
  prenom: string | null;
}

export interface Jetons {
  jeton_acces: string;
  jeton_rafraichissement: string;
  expire_dans: number;
  utilisateur: Utilisateur;
}

export class ErreurApi extends Error {
  constructor(public statut: number, public code: string, message: string,
              public details: { champ: string; regle: string }[] = []) {
    super(message);
  }
}

const BASE = "/api/v1";

let jetonAcces: string | null = null;
let jetonRafraichissement: string | null = null;
let expireA = 0;
let rafraichissementEnCours: Promise<boolean> | null = null;
let surExpiration: (() => void) | null = null;

export function ouvrirSession(j: Jetons) {
  jetonAcces = j.jeton_acces;
  jetonRafraichissement = j.jeton_rafraichissement;
  expireA = Date.now() + j.expire_dans * 1000;
}

export function fermerSession() {
  jetonAcces = null;
  jetonRafraichissement = null;
  expireA = 0;
}

export function quandSessionExpire(fn: () => void) {
  surExpiration = fn;
}

export function sessionOuverte() {
  return jetonAcces !== null;
}

/** Secondes restantes avant l'expiration du jeton d'accès. */
export function secondesAvantExpiration() {
  return Math.max(0, Math.round((expireA - Date.now()) / 1000));
}

export async function rafraichir(): Promise<boolean> {
  if (!jetonRafraichissement) return false;
  // Un seul renouvellement à la fois : deux requêtes simultanées ne doivent
  // pas présenter deux fois le même jeton (ce qui révoquerait la session).
  rafraichissementEnCours ??= (async () => {
    try {
      const r = await fetch(`${BASE}/auth/rafraichir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jeton_rafraichissement: jetonRafraichissement }),
        credentials: "omit",
      });
      if (!r.ok) return false;
      ouvrirSession(await r.json());
      return true;
    } catch {
      return false;
    } finally {
      rafraichissementEnCours = null;
    }
  })();
  return rafraichissementEnCours;
}

async function lireErreur(r: Response): Promise<ErreurApi> {
  try {
    const corps = await r.json();
    const e = corps?.erreur ?? {};
    return new ErreurApi(r.status, e.code ?? `E${r.status}`, e.message ?? "Une erreur est survenue.", e.details ?? []);
  } catch {
    return new ErreurApi(r.status, `E${r.status}`, r.status === 429
      ? "Trop de requêtes. Réessayez dans une minute."
      : "Une erreur est survenue.");
  }
}

export async function appel<T = unknown>(methode: string, chemin: string, corps?: unknown, nouvelEssai = true): Promise<T> {
  // Renouvellement préventif si le jeton expire dans moins de deux minutes.
  if (jetonAcces && secondesAvantExpiration() < 120) await rafraichir();
  const entetes: Record<string, string> = { Accept: "application/json" };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  if (jetonAcces) entetes.Authorization = `Bearer ${jetonAcces}`;
  let r: Response;
  try {
    r = await fetch(BASE + chemin, {
      method: methode,
      headers: entetes,
      body: corps === undefined ? undefined : JSON.stringify(corps),
      credentials: "omit",
      cache: "no-store",
    });
  } catch {
    throw new ErreurApi(0, "RESEAU", "Le serveur est injoignable. Vérifiez votre connexion.");
  }
  if (r.status === 401 && jetonAcces && nouvelEssai) {
    if (await rafraichir()) return appel<T>(methode, chemin, corps, false);
    fermerSession();
    surExpiration?.();
  }
  if (!r.ok) throw await lireErreur(r);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const api = {
  get: <T,>(chemin: string) => appel<T>("GET", chemin),
  post: <T,>(chemin: string, corps?: unknown) => appel<T>("POST", chemin, corps ?? {}),
  put: <T,>(chemin: string, corps: unknown) => appel<T>("PUT", chemin, corps),
  patch: <T,>(chemin: string, corps: unknown) => appel<T>("PATCH", chemin, corps),
  delete: <T,>(chemin: string) => appel<T>("DELETE", chemin),
};

export async function deconnecter() {
  const jeton = jetonRafraichissement;
  try {
    if (jeton && jetonAcces) await appel("POST", "/auth/deconnexion", { jeton_rafraichissement: jeton }, false);
  } catch {
    // La session locale est fermée quoi qu'il arrive.
  } finally {
    fermerSession();
  }
}

/**
 * Téléchargement d'un export (PDF, Excel). Le jeton passe dans l'en-tête, jamais dans
 * l'URL (qui finirait dans l'historique et les journaux) ; le fichier est remis au
 * navigateur par une URL locale révoquée aussitôt.
 */
export async function telecharger(chemin: string, nomFichier: string, nouvelEssai = true): Promise<void> {
  if (jetonAcces && secondesAvantExpiration() < 120) await rafraichir();
  const r = await fetch(BASE + chemin, {
    headers: jetonAcces ? { Authorization: `Bearer ${jetonAcces}` } : {}, credentials: "omit", cache: "no-store",
  });
  if (r.status === 401 && nouvelEssai && (await rafraichir())) return telecharger(chemin, nomFichier, false);
  if (!r.ok) throw await lireErreur(r);
  const url = URL.createObjectURL(await r.blob());
  const lien = document.createElement("a");
  lien.href = url;
  lien.download = nomFichier;
  lien.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Construit une chaîne de requête à partir des seuls paramètres renseignés. */
export function requete(params: Record<string, string | number | undefined | null>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
