import { appel, fichier } from "./api";

export interface MatiereResume { code: string; libelle: string; coefficient: string; moyenne: string; nombre_notes: number; derniere_date: string }
export interface NoteEtudiant {
  id: string; matiere_code: string; matiere_libelle: string; type_evaluation: string; date_evaluation: string;
  valeur: string; modifiee_le: string | null;
}
export interface MesNotes { moyenne_generale: string | null; matieres: MatiereResume[]; notes: NoteEtudiant[] }
export interface Filtres { matiere?: string; du?: string; au?: string }

/** F11 : aucune donnée d'identité n'est envoyée ; le serveur utilise le jeton. */
export function mesNotes(f: Filtres = {}): Promise<MesNotes> {
  const p = new URLSearchParams();
  if (f.matiere) p.set("matiere", f.matiere);
  if (f.du) p.set("du", f.du);
  if (f.au) p.set("au", f.au);
  const q = p.toString();
  return appel<MesNotes>(`/etudiants/moi/notes${q ? `?${q}` : ""}`);
}

/* --- F24 Synthèse --- */
export interface Synthese {
  moyenne_generale: string | null; mention: string; matieres_validees: number; matieres: number;
  evolution: { libelle: string; moyenne: string | null }[]; a_surveiller: { code: string; libelle: string; moyenne: string }[];
  reclamations_ouvertes: number; derniere_publication: string | null;
}
export const synthese = () => appel<Synthese>("/etudiants/moi/synthese");

/* --- F19 Réclamations --- */
export interface Reclamation {
  id: string; statut: "SOUMISE" | "EN_COURS" | "ACCEPTEE" | "REJETEE"; motif: string; reponse: string | null;
  soumise_le: string; traitee_le: string | null;
  note: { id: string; valeur: string; type_evaluation: string; date_evaluation: string; matiere_code: string; matiere_libelle: string };
}
export const mesReclamations = () => appel<{ delai_jours: number; elements: Reclamation[] }>("/etudiants/moi/reclamations");
export const deposerReclamation = (noteId: string, motif: string) =>
  appel<Reclamation>("/etudiants/moi/reclamations", "POST", { note_id: noteId, motif });

/* --- F28 Notifications --- */
export interface Notification { id: string; categorie: string; titre: string; message: string; lien: string | null; creee_le: string; lue: boolean }
export const notifications = () => appel<{ non_lues: number; elements: Notification[] }>("/notifications?limite=50");
export const marquerLue = (id: string) => appel<void>(`/notifications/${id}/lecture`, "POST");
export const toutMarquerLu = () => appel<void>("/notifications/lecture", "POST");

/* --- F27 Espace sécurité --- */
export interface Securite {
  identifiant: string; email: string; derniere_connexion: string | null;
  sessions: { id: string; appareil: string; ouverte_le: string; derniere_activite: string; courante: boolean }[];
  connexions: { horodatage: string; resultat: string; appareil: string }[];
}
export const securite = () => appel<Securite>("/moi/securite");
export const fermerSession = (id: string) => appel<void>(`/moi/sessions/${id}`, "DELETE");
export const changerMotDePasse = (actuel: string, nouveau: string, confirmation: string) =>
  appel<void>("/moi/mot-de-passe", "PUT", { actuel, nouveau, confirmation });

/* --- F20 Relevé de notes --- */
export const releve = () => fichier("/etudiants/moi/releve");

export { STATUTS_RECLAMATION, TYPES, date, dateHeure, lireDate, mois, motifValide, note, reglesMotDePasse } from "./format";
