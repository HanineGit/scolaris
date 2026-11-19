import { useState } from "react";

import { api } from "../../api";
import { anneeCourante, date } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Modale, Statut, messageErreur, useChargement } from "../../ui";

export interface Semestre {
  id: string; annee_academique: string; numero: number; libelle: string;
  saisie_debut: string | null; saisie_fin: string | null; saisie_ouverte: boolean;
}

/** W14 : semestres et fenêtres de saisie des notes (F17). */
export default function Calendrier() {
  const annee = anneeCourante();
  const liste = useChargement(() => api.get<{ elements: Semestre[] }>(`/semestres?annee=${annee}`), []);
  const [fenetre, setFenetre] = useState<Semestre | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const elements = liste.donnees?.elements ?? [];
  const manquants = [1, 2].filter((n) => !elements.some((s) => s.numero === n));

  const action = async (f: () => Promise<unknown>) => {
    setErreur(null);
    try { await f(); liste.recharger(); } catch (e) { setErreur(messageErreur(e)); }
  };

  return (
    <Gabarit fil={["Scolarité", "Calendrier et saisie"]}>
      <div className="phd"><div><h1>Calendrier et saisie</h1>
        <p className="sub">Année académique {annee} · les enseignants ne saisissent que pendant la fenêtre ouverte du semestre</p></div>
        <div className="actions">
          {manquants.map((n) => (
            <button key={n} className="btn p" onClick={() => void action(() => api.post("/semestres", { annee_academique: annee, numero: n }))}>
              <Icone nom="plus" />Créer le semestre {n}</button>
          ))}
        </div>
      </div>
      {(liste.erreur || erreur) && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur ?? erreur}</Message></div>}
      <div className="g2">
        {elements.map((s) => (
          <div className="box" key={s.id} style={{ marginTop: 0 }}>
            <div className="bx-h"><h3>{s.libelle}</h3>
              <Statut ton={s.saisie_ouverte ? "ok" : s.saisie_debut ? "wa" : "mu"}>
                {s.saisie_ouverte ? "Saisie ouverte" : s.saisie_debut ? "Hors fenêtre" : "Saisie fermée"}</Statut></div>
            <div className="bx-b">
              <div className="g2" style={{ marginBottom: 14 }}>
                <div className="kv"><span>Ouverture de la saisie</span><b>{s.saisie_debut ? date(s.saisie_debut) : "–"}</b></div>
                <div className="kv"><span>Clôture de la saisie</span><b>{s.saisie_fin ? date(s.saisie_fin) : "–"}</b></div>
              </div>
              <div className="actions" style={{ justifyContent: "flex-start" }}>
                <button className="btn p" onClick={() => setFenetre(s)}><Icone nom="unlock" />{s.saisie_debut ? "Modifier la fenêtre" : "Ouvrir la saisie"}</button>
                {s.saisie_debut && <button className="btn s" onClick={() => void action(() => api.post(`/semestres/${s.id}/fermeture`))}>
                  <Icone nom="lock" />Fermer la saisie</button>}
              </div>
            </div>
          </div>
        ))}
      </div>
      {!liste.enCours && elements.length === 0 && <div className="box"><p className="vide">Aucun semestre pour {annee}.</p></div>}
      <div style={{ marginTop: 16, maxWidth: 820 }}>
        <Message type="in">Les matières rattachées à un semestre ne sont modifiables que pendant sa fenêtre de saisie et avant leur publication.
          Chaque ouverture et fermeture est tracée dans le journal d'audit.</Message>
      </div>
      {fenetre && <Fenetre s={fenetre} onFermer={() => setFenetre(null)} onFait={() => { setFenetre(null); liste.recharger(); }} />}
    </Gabarit>
  );
}

function Fenetre({ s, onFermer, onFait }: { s: Semestre; onFermer: () => void; onFait: () => void }) {
  const aujourd = new Date().toISOString().slice(0, 10);
  const [debut, setDebut] = useState(s.saisie_debut ?? aujourd);
  const [fin, setFin] = useState(s.saisie_fin ?? aujourd);
  const [erreur, setErreur] = useState<string | null>(null);
  const valide = debut && fin && fin >= debut;
  async function valider() {
    setErreur(null);
    try { await api.put(`/semestres/${s.id}/fenetre`, { saisie_debut: debut, saisie_fin: fin }); onFait(); }
    catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <Modale titre={`Fenêtre de saisie · ${s.libelle}`} onFermer={onFermer} largeur={480} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!valide} onClick={() => void valider()}>Enregistrer</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <div className="g2">
        <Champ libelle="Du" requis><input className="in" type="date" value={debut} onChange={(e) => setDebut(e.target.value)} /></Champ>
        <Champ libelle="Au" requis erreur={fin < debut ? "La clôture précède l'ouverture." : null}>
          <input className="in" type="date" value={fin} min={debut} onChange={(e) => setFin(e.target.value)} /></Champ>
      </div>
    </Modale>
  );
}
