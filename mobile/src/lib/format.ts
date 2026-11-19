/** Fonctions pures de présentation (testées sans téléphone : npm test). */
export const TYPES: Record<string, string> = {
  CONTROLE_CONTINU: "Contrôle continu", EXAMEN: "Examen", TP: "Travaux pratiques", RATTRAPAGE: "Rattrapage",
};

export const note = (v: string | null | undefined) => (v == null ? "—" : v.replace(".", ","));
export const date = (iso: string) => iso.slice(0, 10).split("-").reverse().join("/");
const MOIS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];
export const mois = (iso: string) => `${MOIS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;

/** Lecture d'une date saisie « JJ/MM/AAAA » ; renvoie AAAA-MM-JJ ou null. */
export function lireDate(saisie: string): string | null {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(saisie.trim());
  if (!m) return null;
  const iso = `${m[3]}-${m[2]}-${m[1]}`;
  const d = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().startsWith(iso) ? iso : null;
}

export function reglesMotDePasse(mdp: string) {
  return [
    { libelle: "12 caractères au minimum", ok: mdp.length >= 12 && mdp.length <= 128 },
    { libelle: "Une majuscule et une minuscule", ok: /[a-z]/.test(mdp) && /[A-Z]/.test(mdp) },
    { libelle: "Au moins un chiffre", ok: /\d/.test(mdp) },
    { libelle: "Au moins un caractère spécial", ok: /[^A-Za-z0-9]/.test(mdp) },
  ];
}

/** « 2026-11-19T18:14:05+00:00 » → « 19/11/2026 à 19:14 » (heure locale du téléphone). */
export function dateHeure(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const deux = (n: number) => String(n).padStart(2, "0");
  return `${deux(d.getDate())}/${deux(d.getMonth() + 1)}/${d.getFullYear()} à ${deux(d.getHours())}:${deux(d.getMinutes())}`;
}

export const STATUTS_RECLAMATION: Record<string, [string, "wa" | "in" | "ok" | "er"]> = {
  SOUMISE: ["Soumise", "wa"], EN_COURS: ["En cours d'examen", "in"], ACCEPTEE: ["Acceptée", "ok"], REJETEE: ["Rejetée", "er"],
};

/** Même règle que le serveur : 20 à 500 caractères, sans chevrons ni caractères de contrôle. */
export function motifValide(motif: string): boolean {
  const t = motif.trim();
  // eslint-disable-next-line no-control-regex
  return t.length >= 20 && t.length <= 500 && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f<>]/.test(t);
}
