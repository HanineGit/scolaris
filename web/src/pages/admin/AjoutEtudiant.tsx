import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api";
import { emailValide, nomValide } from "../../format";
import { Champ, Gabarit, Message, messageErreur } from "../../ui";
import type { EtudiantVue } from "./Etudiants";

const REGLE_NOM = "Lettres, espaces, apostrophes et traits d'union uniquement (2 à 60 caractères).";

/** W8 : ajout d'un étudiant (F04). */
export default function AjoutEtudiant() {
  const naviguer = useNavigate();
  const [nom, setNom] = useState("");
  const [prenom, setPrenom] = useState("");
  const [email, setEmail] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const valide = nomValide(nom) && nomValide(prenom) && emailValide(email);

  async function enregistrer(e: FormEvent) {
    e.preventDefault();
    setEnCours(true);
    setErreur(null);
    try {
      const cree = await api.post<EtudiantVue>("/etudiants", { nom: nom.trim(), prenom: prenom.trim(), email: email.trim() });
      naviguer(`/admin/etudiants/${cree.id}`, { state: { message: `Étudiant ${cree.matricule} enregistré. Le lien d'activation a été envoyé.` } });
    } catch (ex) {
      setErreur(messageErreur(ex));
      setEnCours(false);
    }
  }

  return (
    <Gabarit fil={["Scolarité", "Étudiants", "Ajouter un étudiant"]}>
      <div className="phd"><div><h1>Ajouter un étudiant</h1><p className="sub">Les champs marqués d'un astérisque sont obligatoires.</p></div></div>
      <div style={{ display: "grid", gridTemplateColumns: "620px 1fr", gap: 16, alignItems: "start" }}>
        <form className="box" onSubmit={enregistrer}>
          <div className="bx-h"><h3>Informations de base</h3></div>
          <div className="bx-b">
            {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
            <Champ libelle="Matricule"><input className="in" readOnly value="Attribué automatiquement à l'enregistrement" /></Champ>
            <div className="g2">
              <Champ libelle="Nom" requis erreur={nom && !nomValide(nom) ? REGLE_NOM : null}>
                <input className={`in${nom && !nomValide(nom) ? " e" : ""}`} maxLength={60} value={nom} onChange={(e) => setNom(e.target.value)} autoFocus />
              </Champ>
              <Champ libelle="Prénom" requis erreur={prenom && !nomValide(prenom) ? REGLE_NOM : null}>
                <input className={`in${prenom && !nomValide(prenom) ? " e" : ""}`} maxLength={60} value={prenom} onChange={(e) => setPrenom(e.target.value)} />
              </Champ>
            </div>
            <Champ libelle="Adresse e-mail" requis erreur={email && !emailValide(email) ? "Format d'adresse e-mail invalide." : null}
              aide="Le lien d'activation du compte sera envoyé à cette adresse.">
              <input className={`in${email && !emailValide(email) ? " e" : ""}`} type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
            </Champ>
            <div className="actions" style={{ borderTop: "1px solid var(--line2)", paddingTop: 14, marginTop: 6 }}>
              <button type="button" className="btn s" onClick={() => naviguer("/admin/etudiants")}>Annuler</button>
              <button className="btn p" disabled={!valide || enCours}>Enregistrer l'étudiant</button>
            </div>
          </div>
        </form>
        <div className="box bx-b">
          <h3 style={{ fontSize: 14.5, fontWeight: 600, marginBottom: 8 }}>Après l'enregistrement</h3>
          <ol style={{ paddingLeft: 18, fontSize: 13.5, lineHeight: 1.65, color: "var(--tx2)" }}>
            <li>La fiche est créée avec le statut « Actif ».</li>
            <li>Un compte étudiant est créé en attente d'activation.</li>
            <li>Un lien d'activation à usage unique, valable 24 heures, est envoyé à l'adresse indiquée.</li>
            <li>L'opération est enregistrée dans le journal d'audit.</li>
          </ol>
          <div style={{ marginTop: 12 }}><Message type="in">Le matricule ne pourra plus être modifié. Une adresse e-mail ne peut être associée qu'à un seul étudiant.</Message></div>
        </div>
      </div>
    </Gabarit>
  );
}
