import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { api, requete } from "../../api";
import { TYPES_EVALUATION, dateHeure, lireNote, note } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Statut, messageErreur, useChargement } from "../../ui";
import type { MaMatiere } from "./MesMatieres";
import type { NoteVue } from "./Notes";

interface EtudiantTrouve { id: string; matricule: string; nom: string; prenom: string; statut: string }
const aujourdhui = () => new Date().toISOString().slice(0, 10);

/** W4 : enregistrement d'une note (F08). */
export default function Saisie() {
  const [params] = useSearchParams();
  const matieres = useChargement(() => api.get<{ elements: MaMatiere[] }>("/enseignants/moi/matieres"), []);
  const actives = (matieres.donnees?.elements ?? []).filter((m) => m.active);

  const [matiere, setMatiere] = useState(params.get("matiere") ?? "");
  const [type, setType] = useState("EXAMEN");
  const [jour, setJour] = useState(aujourdhui());
  const [matricule, setMatricule] = useState("");
  const [etudiant, setEtudiant] = useState<EtudiantTrouve | null>(null);
  const [erreurEtudiant, setErreurEtudiant] = useState<string | null>(null);
  const [valeur, setValeur] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  useEffect(() => { if (!matiere && actives.length) setMatiere(actives[0].id); }, [actives, matiere]);

  const saisies = useChargement(
    () => matiere ? api.get<{ total: number; elements: NoteVue[] }>(`/matieres/${matiere}/notes${requete({ type_evaluation: type, date_evaluation: jour, taille: 8 })}`)
      : Promise.resolve({ total: 0, elements: [] }),
    [matiere, type, jour]);

  const valeurNormalisee = lireNote(valeur);
  const matriculeValide = /^ETU-\d{4}-\d{4}$/.test(matricule);

  async function chercher() {
    setEtudiant(null);
    setErreurEtudiant(null);
    try {
      setEtudiant(await api.get<EtudiantTrouve>(`/notes/etudiant${requete({ matricule })}`));
    } catch (e) {
      setErreurEtudiant(messageErreur(e));
    }
  }

  async function enregistrer(e: FormEvent) {
    e.preventDefault();
    if (!etudiant || !valeurNormalisee) return;
    setEnCours(true);
    setErreur(null);
    setSucces(null);
    try {
      await api.post("/notes", { matiere_id: matiere, etudiant_id: etudiant.id, type_evaluation: type, date_evaluation: jour, valeur: valeurNormalisee });
      setSucces(`Note de ${note(valeurNormalisee)} enregistrée pour ${etudiant.nom} ${etudiant.prenom}.`);
      setValeur("");
      setMatricule("");
      setEtudiant(null);
      saisies.recharger();
    } catch (ex) {
      setErreur(messageErreur(ex));
    } finally {
      setEnCours(false);
    }
  }

  const libelle = actives.find((m) => m.id === matiere);
  return (
    <Gabarit fil={["Enseignement", "Saisie des notes"]}>
      <div className="phd"><div><h1>Enregistrer une note</h1><p className="sub">{libelle ? `${libelle.libelle} (${libelle.code})` : "—"}</p></div></div>
      <div style={{ display: "grid", gridTemplateColumns: "430px 1fr", gap: 16, alignItems: "start" }}>
        <form className="box" onSubmit={enregistrer}>
          <div className="bx-h"><h3>Nouvelle note</h3></div>
          <div className="bx-b">
            {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
            {succes && <div style={{ marginBottom: 12 }}><Message type="ok">{succes}</Message></div>}
            <Champ libelle="Matière" requis>
              <select className="in" value={matiere} onChange={(e) => setMatiere(e.target.value)}>
                {actives.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.libelle}</option>)}
              </select>
            </Champ>
            <div className="g2">
              <Champ libelle="Type d'évaluation" requis>
                <select className="in" value={type} onChange={(e) => setType(e.target.value)}>
                  {Object.entries(TYPES_EVALUATION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Champ>
              <Champ libelle="Date de l'évaluation" requis>
                <input className="in" type="date" max={aujourdhui()} value={jour} onChange={(e) => setJour(e.target.value)} />
              </Champ>
            </div>
            <Champ libelle="Étudiant (matricule)" requis erreur={erreurEtudiant}>
              <div style={{ display: "flex", gap: 8 }}>
                <input className="in mono" placeholder="ETU-2026-0142" maxLength={13} value={matricule}
                  onChange={(e) => { setMatricule(e.target.value.toUpperCase()); setEtudiant(null); }}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (matriculeValide) void chercher(); } }} />
                <button type="button" className="btn s" disabled={!matriculeValide} onClick={() => void chercher()}><Icone nom="search" />Rechercher</button>
              </div>
              {etudiant && (
                <div style={{ border: "1px solid var(--line)", borderTop: 0, borderRadius: "0 0 4px 4px", padding: "8px 10px", background: "var(--sand2)" }}>
                  <b>{etudiant.nom} {etudiant.prenom}</b> · {etudiant.matricule} ·{" "}
                  <Statut ton={etudiant.statut === "ACTIF" ? "ok" : "mu"}>{etudiant.statut === "ACTIF" ? "Actif" : "Archivé"}</Statut>
                </div>
              )}
            </Champ>
            <Champ libelle="Note sur 20" requis erreur={valeur && !valeurNormalisee ? "La note doit être comprise entre 0 et 20 (deux décimales au plus)." : null}>
              <input className={`in${valeur && !valeurNormalisee ? " e" : ""}`} style={{ width: 140 }} inputMode="decimal" maxLength={5}
                value={valeur} onChange={(e) => setValeur(e.target.value)} placeholder="14,50" />
            </Champ>
            <div className="actions" style={{ borderTop: "1px solid var(--line2)", paddingTop: 12 }}>
              <button type="button" className="btn s" onClick={() => { setValeur(""); setMatricule(""); setEtudiant(null); }}>Effacer</button>
              <button className="btn p" disabled={enCours || !etudiant || etudiant.statut !== "ACTIF" || !valeurNormalisee}>Enregistrer</button>
            </div>
          </div>
        </form>
        <div className="box">
          <div className="bx-h"><h3>Notes déjà saisies pour cette évaluation</h3>
            <span className="sub" style={{ margin: 0 }}>{TYPES_EVALUATION[type]} du {jour.split("-").reverse().join("/")} · {saisies.donnees?.total ?? 0} notes</span></div>
          <table>
            <thead><tr><th>Matricule</th><th>Étudiant</th><th className="r">Note</th><th>Saisie le</th></tr></thead>
            <tbody>
              {(saisies.donnees?.elements ?? []).map((n) => (
                <tr key={n.id}><td className="mono">{n.etudiant?.matricule ?? "—"}</td><td>{n.etudiant ? `${n.etudiant.nom} ${n.etudiant.prenom}` : "—"}</td>
                  <td className="r"><b>{note(n.valeur)}</b></td><td>{dateHeure(n.saisie_le)}</td></tr>
              ))}
            </tbody>
          </table>
          {saisies.donnees?.total === 0 && <p className="vide">Aucune note saisie pour cette évaluation.</p>}
        </div>
      </div>
    </Gabarit>
  );
}
