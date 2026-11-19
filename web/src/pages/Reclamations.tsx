import { useState } from "react";

import { api } from "../api";
import { TYPES_EVALUATION, date, dateHeure, lireNote, note } from "../format";
import { Champ, Gabarit, Message, Modale, Statut, messageErreur, useChargement } from "../ui";

export interface Reclamation {
  id: string; statut: "SOUMISE" | "EN_COURS" | "ACCEPTEE" | "REJETEE"; motif: string; reponse: string | null;
  soumise_le: string; traitee_le: string | null; traitee_par: string | null; version: number;
  etudiant: { matricule: string; nom: string; prenom: string } | null;
  note: { id: string; valeur: string; type_evaluation: string; date_evaluation: string; matiere_code: string; matiere_libelle: string };
}

export const STATUTS_RECLAMATION: Record<string, [string, string]> = {
  SOUMISE: ["Soumise", "wa"], EN_COURS: ["En cours d'examen", "in"], ACCEPTEE: ["Acceptée", "ok"], REJETEE: ["Rejetée", "er"],
};

/** W16 et W17 : réclamations à traiter (enseignant) ou vue d'ensemble en lecture (administrateur) (F19). */
export default function Reclamations({ role }: { role: "ENSEIGNANT" | "ADMINISTRATEUR" }) {
  const [statut, setStatut] = useState("");
  const enseignant = role === "ENSEIGNANT";
  const liste = useChargement(() => api.get<{ elements: Reclamation[] }>(
    `${enseignant ? "/enseignants/moi/reclamations" : "/reclamations"}${statut ? `?statut=${statut}` : ""}`), [statut]);
  const [choisie, setChoisie] = useState<Reclamation | null>(null);
  const elements = liste.donnees?.elements ?? [];

  return (
    <Gabarit fil={[enseignant ? "Suivi" : "Résultats", "Réclamations"]}>
      <div className="phd"><div><h1>Réclamations</h1>
        <p className="sub">{enseignant ? "Contestations déposées par les étudiants sur les notes publiées de vos matières"
          : "Vue d'ensemble des réclamations ; leur traitement revient à l'enseignant de la matière"}</p></div></div>
      {liste.erreur && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur}</Message></div>}
      <div className="box">
        <div className="tb">
          <select className="in" style={{ width: 220 }} value={statut} onChange={(e) => setStatut(e.target.value)} aria-label="Statut">
            <option value="">Tous les statuts</option>
            {Object.entries(STATUTS_RECLAMATION).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <table>
          <thead><tr><th>Déposée le</th><th>Étudiant</th><th>Matière</th><th>Évaluation</th><th className="r">Note</th><th>Statut</th><th /></tr></thead>
          <tbody>
            {elements.map((r) => {
              const [libelle, ton] = STATUTS_RECLAMATION[r.statut];
              return (
                <tr key={r.id} className="cliquable" onClick={() => setChoisie(r)}>
                  <td>{dateHeure(r.soumise_le)}</td>
                  <td>{r.etudiant ? <>{r.etudiant.nom} {r.etudiant.prenom} <span className="mono muet">{r.etudiant.matricule}</span></> : "–"}</td>
                  <td><span className="mono">{r.note.matiere_code}</span> {r.note.matiere_libelle}</td>
                  <td>{TYPES_EVALUATION[r.note.type_evaluation]} · {date(r.note.date_evaluation)}</td>
                  <td className="r"><b>{note(r.note.valeur)}</b></td>
                  <td><Statut ton={ton}>{libelle}</Statut></td>
                  <td className="r"><span className="ln">{enseignant && (r.statut === "SOUMISE" || r.statut === "EN_COURS") ? "Traiter" : "Voir"}</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!liste.enCours && elements.length === 0 && <p className="vide">Aucune réclamation.</p>}
      </div>
      {choisie && <Detail r={choisie} peutTraiter={enseignant} onFermer={() => setChoisie(null)} onFait={() => { setChoisie(null); liste.recharger(); }} />}
    </Gabarit>
  );
}

function Detail({ r, peutTraiter, onFermer, onFait }: { r: Reclamation; peutTraiter: boolean; onFermer: () => void; onFait: () => void }) {
  const ouverte = r.statut === "SOUMISE" || r.statut === "EN_COURS";
  const [decision, setDecision] = useState<"EN_COURS" | "ACCEPTEE" | "REJETEE">("ACCEPTEE");
  const [reponse, setReponse] = useState("");
  const [valeur, setValeur] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const nouvelle = lireNote(valeur);
  const valide = reponse.trim().length >= 10 && (decision !== "ACCEPTEE" || (nouvelle !== null && nouvelle !== r.note.valeur));
  async function valider() {
    setErreur(null);
    try {
      await api.put(`/reclamations/${r.id}`, { decision, reponse: reponse.trim(), version: r.version,
                                              nouvelle_valeur: decision === "ACCEPTEE" ? nouvelle : null });
      onFait();
    } catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <Modale titre={`Réclamation · ${r.note.matiere_code}`} onFermer={onFermer} largeur={560} pied={peutTraiter && ouverte ? <>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!valide} onClick={() => void valider()}>Enregistrer la décision</button></> : undefined}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <div className="g3" style={{ marginBottom: 14 }}>
        <div className="kv"><span>Étudiant</span><b>{r.etudiant ? `${r.etudiant.nom} ${r.etudiant.prenom}` : "–"}</b></div>
        <div className="kv"><span>Évaluation</span><b>{TYPES_EVALUATION[r.note.type_evaluation]}</b></div>
        <div className="kv"><span>Note actuelle</span><b>{note(r.note.valeur)} / 20</b></div>
      </div>
      <label className="lbl">Motif de l'étudiant</label>
      <p className="regles" style={{ lineHeight: 1.5, color: "var(--tx)" }}>{r.motif}</p>
      {r.reponse && <><label className="lbl">Réponse{r.traitee_par ? ` de ${r.traitee_par}` : ""}</label>
        <p className="regles" style={{ lineHeight: 1.5, color: "var(--tx)" }}>{r.reponse}</p></>}
      {peutTraiter && ouverte && (
        <>
          <Champ libelle="Décision" requis>
            <select className="in" value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)}>
              <option value="ACCEPTEE">Accepter et corriger la note</option>
              <option value="REJETEE">Rejeter (note maintenue)</option>
              <option value="EN_COURS">Indiquer que l'examen est en cours</option>
            </select>
          </Champ>
          {decision === "ACCEPTEE" && (
            <Champ libelle="Nouvelle note sur 20" requis erreur={valeur && nouvelle === null ? "Entre 0 et 20, deux décimales au plus." : null}>
              <input className="in" inputMode="decimal" maxLength={5} style={{ width: 120 }} value={valeur} onChange={(e) => setValeur(e.target.value)} />
            </Champ>
          )}
          <Champ libelle="Réponse à l'étudiant" requis aide="10 à 500 caractères ; elle est conservée dans l'historique de la note.">
            <textarea className="in" maxLength={500} value={reponse} onChange={(e) => setReponse(e.target.value)} />
          </Champ>
        </>
      )}
    </Modale>
  );
}
