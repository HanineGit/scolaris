import { useState } from "react";
import { useLocation, useParams } from "react-router-dom";

import { api } from "../../api";
import { STATUTS_COMPTE, TYPES_EVALUATION, date, emailValide, nomValide, note } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Modale, Statut, messageErreur, useChargement } from "../../ui";
import type { NoteVue } from "../enseignant/Notes";
import type { Classe } from "./Classes";
import type { EtudiantVue } from "./Etudiants";

/** W9 : fiche étudiant, notes en lecture seule, modification et archivage (F05, F06, F09). */
export default function FicheEtudiant() {
  const { id } = useParams();
  const etat = useLocation().state as { message?: string } | null;
  const fiche = useChargement(() => api.get<EtudiantVue>(`/etudiants/${id}`), [id]);
  const notes = useChargement(() => api.get<{ elements: NoteVue[] }>(`/notes?etudiant=${id}`), [id]);
  const [modale, setModale] = useState<"modifier" | "archiver" | "classe" | null>(null);
  const [message, setMessage] = useState<string | null>(etat?.message ?? null);
  const e = fiche.donnees;

  if (fiche.erreur) return <Gabarit fil={["Scolarité", "Étudiants"]}><Message type="er">{fiche.erreur}</Message></Gabarit>;
  if (!e) return <Gabarit fil={["Scolarité", "Étudiants"]}><p className="chargement">Chargement…</p></Gabarit>;
  const [compte] = STATUTS_COMPTE[e.compte ?? ""] ?? ["—"];

  return (
    <Gabarit fil={["Scolarité", "Étudiants", `${e.nom} ${e.prenom}`]}>
      <div className="phd">
        <div><h1>{e.nom} {e.prenom}</h1>
          <p className="sub"><span className="mono">{e.matricule}</span> · <Statut ton={e.statut === "ACTIF" ? "ok" : "mu"}>{e.statut === "ACTIF" ? "Actif" : "Archivé"}</Statut></p></div>
        {e.statut === "ACTIF" && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn s" onClick={() => setModale("modifier")}><Icone nom="edit" />Modifier la fiche</button>
            <button className="btn d" onClick={() => setModale("archiver")}><Icone nom="archive" />Archiver</button>
          </div>
        )}
      </div>
      {message && <div style={{ marginBottom: 14 }}><Message type="ok">{message}</Message></div>}
      <div className="box bx-b" style={{ marginBottom: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 14 }}>
          <div className="kv"><span>Nom</span><b>{e.nom}</b></div>
          <div className="kv"><span>Prénom</span><b>{e.prenom}</b></div>
          <div className="kv"><span>Adresse e-mail</span><b>{e.email}</b></div>
          <div className="kv"><span>Classe</span><b>{e.classe ?? "Non inscrit"}</b>
            {e.statut === "ACTIF" && <button className="lien" style={{ display: "block", marginTop: 2 }} onClick={() => setModale("classe")}>{e.classe ? "Changer de classe" : "Inscrire"}</button>}</div>
          <div className="kv"><span>Compte</span><b>{compte}</b></div>
          <div className="kv"><span>Fiche créée le</span><b>{date(e.cree_le)}</b></div>
        </div>
      </div>
      <div className="box">
        <div className="bx-h"><h3>Notes (lecture seule)</h3><span className="sub" style={{ margin: 0 }}>Les notes sont saisies par les enseignants des matières</span></div>
        <table>
          <thead><tr><th>Matière</th><th>Évaluation</th><th>Date</th><th className="r">Note /20</th><th>Saisie par</th></tr></thead>
          <tbody>
            {(notes.donnees?.elements ?? []).map((n) => (
              <tr key={n.id}><td>{n.matiere_libelle}</td><td>{TYPES_EVALUATION[n.type_evaluation]}</td><td>{date(n.date_evaluation)}</td>
                <td className="r"><b>{note(n.valeur)}</b>{n.modifie_le && <span className="muet"> (modifiée)</span>}</td><td>{n.saisie_par}</td></tr>
            ))}
          </tbody>
        </table>
        {notes.donnees?.elements.length === 0 && <p className="vide">Aucune note enregistrée.</p>}
      </div>
      {modale === "classe" && <ChangerClasse e={e} onFermer={() => setModale(null)}
        onFait={(m) => { setModale(null); setMessage(m); fiche.recharger(); }} />}
      {modale === "modifier" && <ModifierFiche e={e} onFermer={() => setModale(null)}
        onFait={() => { setModale(null); setMessage("Fiche mise à jour."); fiche.recharger(); }} />}
      {modale === "archiver" && <Archiver e={e} onFermer={() => setModale(null)}
        onFait={() => { setModale(null); setMessage("Étudiant archivé ; son compte est désactivé."); fiche.recharger(); }} />}
    </Gabarit>
  );
}

function ModifierFiche({ e, onFermer, onFait }: { e: EtudiantVue; onFermer: () => void; onFait: () => void }) {
  const [nom, setNom] = useState(e.nom);
  const [prenom, setPrenom] = useState(e.prenom);
  const [email, setEmail] = useState(e.email);
  const [erreur, setErreur] = useState<string | null>(null);
  const valide = nomValide(nom) && nomValide(prenom) && emailValide(email);
  async function enregistrer() {
    setErreur(null);
    try {
      await api.patch(`/etudiants/${e.id}`, { nom: nom.trim(), prenom: prenom.trim(), email: email.trim(), version: e.version });
      onFait();
    } catch (ex) { setErreur(messageErreur(ex)); }
  }
  return (
    <Modale titre="Modifier la fiche" onFermer={onFermer} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!valide} onClick={() => void enregistrer()}>Enregistrer</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <Champ libelle="Matricule" aide="Le matricule n'est pas modifiable."><input className="in" readOnly value={e.matricule} /></Champ>
      <div className="g2">
        <Champ libelle="Nom" requis><input className="in" maxLength={60} value={nom} onChange={(x) => setNom(x.target.value)} /></Champ>
        <Champ libelle="Prénom" requis><input className="in" maxLength={60} value={prenom} onChange={(x) => setPrenom(x.target.value)} /></Champ>
      </div>
      <Champ libelle="Adresse e-mail" requis aide="L'adresse de connexion de l'étudiant sera mise à jour.">
        <input className="in" type="email" maxLength={254} value={email} onChange={(x) => setEmail(x.target.value)} />
      </Champ>
    </Modale>
  );
}

function Archiver({ e, onFermer, onFait }: { e: EtudiantVue; onFermer: () => void; onFait: () => void }) {
  const [saisie, setSaisie] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  async function archiver() {
    setErreur(null);
    try {
      await api.post(`/etudiants/${e.id}/archivage`, { confirmation_matricule: saisie, version: e.version });
      onFait();
    } catch (ex) { setErreur(messageErreur(ex)); }
  }
  return (
    <Modale titre="Archiver cet étudiant ?" onFermer={onFermer} largeur={500} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn d" disabled={saisie !== e.matricule} onClick={() => void archiver()}>Archiver</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <p style={{ marginBottom: 10, lineHeight: 1.55 }}><b>{e.nom} {e.prenom}</b> ({e.matricule}) n'apparaîtra plus dans la liste des étudiants actifs et son compte sera désactivé.</p>
      <p style={{ marginBottom: 12, color: "var(--mu)", lineHeight: 1.55 }}>La fiche et les notes sont conservées. Aucune nouvelle note ne pourra être saisie.</p>
      <Champ libelle="Saisissez le matricule pour confirmer">
        <input className="in mono" value={saisie} maxLength={13} onChange={(x) => setSaisie(x.target.value.toUpperCase())} autoFocus />
      </Champ>
    </Modale>
  );
}

function ChangerClasse({ e, onFermer, onFait }: { e: EtudiantVue; onFermer: () => void; onFait: (message: string) => void }) {
  const classes = useChargement(() => api.get<{ elements: Classe[] }>("/classes"), []);
  const [choix, setChoix] = useState(e.classe_id ?? "");
  const [erreur, setErreur] = useState<string | null>(null);
  async function valider() {
    setErreur(null);
    try {
      await api.put(`/etudiants/${e.id}/classe`, { classe_id: choix || null, version: e.version });
      onFait(choix ? "Inscription enregistrée." : "L'étudiant n'est plus inscrit dans une classe.");
    } catch (err) { setErreur(messageErreur(err)); }
  }
  return (
    <Modale titre="Classe de l'étudiant" onFermer={onFermer} largeur={460} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={choix === (e.classe_id ?? "")} onClick={() => void valider()}>Enregistrer</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <Champ libelle="Classe" aide="Seules les classes ouvertes de l'année en cours sont proposées.">
        <select className="in" value={choix} onChange={(ev) => setChoix(ev.target.value)}>
          <option value="">Aucune classe</option>
          {(classes.donnees?.elements ?? []).filter((c) => c.active).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.libelle}</option>)}
        </select>
      </Champ>
      <Message type="in">Le changement est tracé dans le journal d'audit avec la classe d'origine.</Message>
    </Modale>
  );
}
