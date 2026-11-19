/** Mise en forme et validation côté client (aide à la saisie ; le serveur revalide tout). */

export const TYPES_EVALUATION: Record<string, string> = {
  CONTROLE_CONTINU: "Contrôle continu",
  EXAMEN: "Examen",
  TP: "Travaux pratiques",
  RATTRAPAGE: "Rattrapage",
};

export const STATUTS_COMPTE: Record<string, [string, string]> = {
  ACTIF: ["Activé", "ok"],
  EN_ATTENTE_ACTIVATION: ["En attente d'activation", "wa"],
  VERROUILLE: ["Verrouillé", "er"],
  DESACTIVE: ["Désactivé", "mu"],
};

export function date(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, j] = iso.slice(0, 10).split("-");
  return `${j}/${m}/${a}`;
}

export function dateHeure(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Horodatage UTC du journal d'audit : AAAA-MM-JJ HH:MM:SS. */
export function horodatageUtc(iso: string): string {
  return new Date(iso).toISOString().replace("T", " ").slice(0, 19);
}

export function note(valeur: string | null | undefined): string {
  return valeur == null ? "—" : valeur.replace(".", ",");
}

/** Convertit une saisie « 14,5 » en « 14.50 » ; renvoie null si la valeur n'est pas une note valide. */
export function lireNote(saisie: string): string | null {
  const t = saisie.trim().replace(",", ".");
  if (!/^\d{1,2}(\.\d{1,2})?$/.test(t)) return null;
  const v = Number(t);
  return v >= 0 && v <= 20 ? v.toFixed(2) : null;
}

const NOM_RE = /^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{1,59}$/;
export const nomValide = (v: string) => NOM_RE.test(v.trim());
export const emailValide = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()) && v.length <= 254;

export interface Regle { libelle: string; ok: boolean }

/** Mêmes règles que le serveur (le serveur vérifie en plus les mots de passe divulgués). */
export function reglesMotDePasse(mdp: string): Regle[] {
  return [
    { libelle: "12 caractères au minimum", ok: mdp.length >= 12 && mdp.length <= 128 },
    { libelle: "Une majuscule et une minuscule", ok: /[a-z]/.test(mdp) && /[A-Z]/.test(mdp) },
    { libelle: "Au moins un chiffre", ok: /\d/.test(mdp) },
    { libelle: "Au moins un caractère spécial", ok: /[^A-Za-z0-9]/.test(mdp) },
  ];
}

export function initiales(nom?: string | null, prenom?: string | null): string {
  return `${(prenom ?? "")[0] ?? ""}${(nom ?? "")[0] ?? ""}`.toUpperCase() || "?";
}

export function anneeCourante(): string {
  const d = new Date();
  const debut = d.getMonth() >= 8 ? d.getFullYear() : d.getFullYear() - 1;
  return `${debut}-${debut + 1}`;
}
