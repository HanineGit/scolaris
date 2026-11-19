import { useEffect, useState } from "react";

import { api, telecharger } from "../../api";
import { date, dateHeure } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Modale, Statut, messageErreur, useChargement } from "../../ui";
import type { Semestre } from "./Calendrier";
import type { Classe } from "./Classes";

interface Matiere {
  id: string; code: string; libelle: string; coefficient: string; active: boolean;
  classe_id: string | null; semestre: Semestre | null; publiee_le: string | null;
  enseignants: { affectation_id: string; enseignant_id: string; nom: string | null; prenom: string | null; depuis: string }[];
}
interface Enseignant { id: string; nom: string; prenom: string }

const coefValide = (c: string) => /^\d{1,2}([.,]\d)?$/.test(c) && Number(c.replace(",", ".")) >= 0.5 && Number(c.replace(",", ".")) <= 10;
const libelleValide = (l: string) => /^[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9' ,\-()]{1,79}$/.test(l.trim());

/** W10 : matières et affectations des enseignants (F07). */
export default function Matieres() {
  const liste = useChargement(() => api.get<{ annee_academique: string; elements: Matiere[] }>("/matieres"), []);
  const enseignants = useChargement(() => api.get<Enseignant[]>("/matieres/enseignants-disponibles"), []);
  const [selection, setSelection] = useState<string | null>(null);
  const [creation, setCreation] = useState(false);
  const classes = useChargement(() => api.get<{ elements: Classe[] }>("/classes"), []);
  const semestres = useChargement(() => api.get<{ elements: Semestre[] }>("/semestres"), []);
  const m = liste.donnees?.elements.find((x) => x.id === selection) ?? null;
  const ref = { classes: classes.donnees?.elements ?? [], semestres: semestres.donnees?.elements ?? [] };
  const codeClasse = (id: string | null) => ref.classes.find((c) => c.id === id)?.code;

  return (
    <Gabarit fil={["Scolarité", "Matières et publication"]}>
      <div className="phd">
        <div><h1>Matières et publication</h1><p className="sub">Année académique {liste.donnees?.annee_academique ?? "…"}</p></div>
        <button className="btn p" onClick={() => setCreation(true)}><Icone nom="plus" />Nouvelle matière</button>
      </div>
      {liste.erreur && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur}</Message></div>}
      <div style={{ display: "grid", gridTemplateColumns: m ? "1fr 400px" : "1fr", gap: 16, alignItems: "start" }}>
        <div className="box">
          <table>
            <thead><tr><th>Code</th><th>Libellé</th><th>Classe</th><th>Semestre</th><th className="r">Coef.</th><th>Enseignant(s)</th><th>Notes</th></tr></thead>
            <tbody>
              {(liste.donnees?.elements ?? []).map((x) => (
                <tr key={x.id} className={`cliquable${x.id === selection ? " sel" : ""}`} onClick={() => setSelection(x.id)}>
                  <td className="mono"><b>{x.code}</b></td><td>{x.libelle}{!x.active && <span className="muet"> · désactivée</span>}</td>
                  <td>{codeClasse(x.classe_id) ? <span className="pastille">{codeClasse(x.classe_id)}</span> : <span className="muet">–</span>}</td>
                  <td>{x.semestre ? `S${x.semestre.numero}` : <span className="muet">–</span>}</td>
                  <td className="r">{x.coefficient.replace(".0", "")}</td>
                  <td>{x.enseignants.length ? x.enseignants.map((e) => `${e.prenom?.[0] ?? ""}. ${e.nom ?? "?"}`).join(", ")
                    : <span style={{ color: x.active ? "var(--wa)" : "var(--fa)" }}>Aucun</span>}</td>
                  <td><Statut ton={x.publiee_le ? "ok" : "wa"}>{x.publiee_le ? "Publiées" : "En saisie"}</Statut></td>
                </tr>
              ))}
            </tbody>
          </table>
          {liste.donnees?.elements.length === 0 && <p className="vide">Aucune matière. Créez la première avec « Nouvelle matière ».</p>}
        </div>
        {m && <Edition m={m} enseignants={enseignants.donnees ?? []} {...ref} onFermer={() => setSelection(null)} onChange={liste.recharger} />}
      </div>
      {creation && <Creation {...ref} onFermer={() => setCreation(false)} onCree={(id) => { setCreation(false); liste.recharger(); setSelection(id); }} />}
    </Gabarit>
  );
}

function Edition({ m, enseignants, classes, semestres, onFermer, onChange }: {
  m: Matiere; enseignants: Enseignant[]; classes: Classe[]; semestres: Semestre[]; onFermer: () => void; onChange: () => void;
}) {
  const [publication, setPublication] = useState<"publier" | "retirer" | null>(null);
  const [libelle, setLibelle] = useState(m.libelle);
  const [coef, setCoef] = useState(m.coefficient.replace(".0", ""));
  const [choix, setChoix] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => { setLibelle(m.libelle); setCoef(m.coefficient.replace(".0", "")); setErreur(null); }, [m]);

  const action = async (f: () => Promise<unknown>) => {
    setErreur(null);
    try { await f(); onChange(); } catch (e) { setErreur(messageErreur(e)); }
  };
  const disponibles = enseignants.filter((e) => !m.enseignants.some((a) => a.enseignant_id === e.id));

  return (
    <div className="box">
      <div className="bx-h"><h3>{m.code} · {m.libelle}</h3><button className="fermer" onClick={onFermer} aria-label="Fermer"><Icone nom="x" /></button></div>
      <div className="bx-b">
        {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
        <div className="g2">
          <Champ libelle="Code"><input className="in" readOnly value={m.code} /></Champ>
          <Champ libelle="Coefficient" requis erreur={!coefValide(coef) ? "Entre 0,5 et 10." : null}>
            <input className="in" inputMode="decimal" maxLength={4} value={coef} onChange={(e) => setCoef(e.target.value)} />
          </Champ>
        </div>
        <Champ libelle="Libellé" requis erreur={!libelleValide(libelle) ? "2 à 80 caractères, sans caractère spécial." : null}>
          <input className="in" maxLength={80} value={libelle} onChange={(e) => setLibelle(e.target.value)} />
        </Champ>
        <div className="g2">
          <Champ libelle="Classe">
            <select className="in" value={m.classe_id ?? ""} onChange={(e) => e.target.value && void action(() => api.patch(`/matieres/${m.id}`, { classe_id: e.target.value }))}>
              <option value="">Non rattachée</option>
              {classes.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
            </select>
          </Champ>
          <Champ libelle="Semestre">
            <select className="in" value={m.semestre?.id ?? ""} onChange={(e) => e.target.value && void action(() => api.patch(`/matieres/${m.id}`, { semestre_id: e.target.value }))}>
              <option value="">Non rattachée</option>
              {semestres.map((s) => <option key={s.id} value={s.id}>{s.libelle}</option>)}
            </select>
          </Champ>
        </div>
        <div className="box" style={{ marginBottom: 14, boxShadow: "none" }}>
          <div className="bx-b" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div className="kv"><span>Publication des notes</span>
              <b>{m.publiee_le ? `Publiées le ${dateHeure(m.publiee_le)}` : "Non publiées (invisibles des étudiants)"}</b></div>
            {m.publiee_le
              ? <button className="btn d sm" onClick={() => setPublication("retirer")}><Icone nom="unlock" />Retirer</button>
              : <button className="btn p sm" onClick={() => setPublication("publier")}><Icone nom="send" />Publier</button>}
          </div>
          <div className="bx-b" style={{ borderTop: "1px solid var(--line2)", display: "flex", gap: 8 }}>
            <button className="btn s sm" onClick={() => void action(() => telecharger(`/matieres/${m.id}/export?format=pdf`, `notes-${m.code}.pdf`))}><Icone nom="download" />PDF</button>
            <button className="btn s sm" onClick={() => void action(() => telecharger(`/matieres/${m.id}/export?format=xlsx`, `notes-${m.code}.xlsx`))}><Icone nom="download" />Excel</button>
          </div>
        </div>
        <label className="lbl">Enseignants affectés</label>
        <div style={{ border: "1px solid var(--line)", borderRadius: 4, marginBottom: 8 }}>
          {m.enseignants.length === 0 && <div style={{ padding: "8px 10px", fontSize: 13.5, color: "var(--mu)" }}>Aucun enseignant affecté.</div>}
          {m.enseignants.map((a) => (
            <div key={a.affectation_id} style={{ display: "flex", justifyContent: "space-between", padding: "8px 10px", fontSize: 13.5, borderBottom: "1px solid var(--line2)" }}>
              <span><b>{a.prenom} {a.nom}</b> · depuis le {date(a.depuis)}</span>
              <button className="lien" onClick={() => void action(() => api.delete(`/matieres/${m.id}/affectations/${a.affectation_id}`))}>Retirer</button>
            </div>
          ))}
        </div>
        {m.active && (
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            <select className="in" style={{ flex: 1 }} value={choix} onChange={(e) => setChoix(e.target.value)} aria-label="Enseignant">
              <option value="">Choisir un enseignant</option>
              {disponibles.map((e) => <option key={e.id} value={e.id}>{e.nom} {e.prenom}</option>)}
            </select>
            <button className="btn s" disabled={!choix}
              onClick={() => void action(async () => { await api.post(`/matieres/${m.id}/affectations`, { enseignant_id: choix }); setChoix(""); })}>Affecter</button>
          </div>
        )}
        <div style={{ marginBottom: 12 }}><Message type="in">Une matière qui porte des notes ne peut pas être supprimée ; elle peut seulement être désactivée.</Message></div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <button className="btn s" onClick={() => void action(() => api.patch(`/matieres/${m.id}`, { active: !m.active }))}>{m.active ? "Désactiver" : "Réactiver"}</button>
          <button className="btn p" disabled={!coefValide(coef) || !libelleValide(libelle)}
            onClick={() => void action(() => api.patch(`/matieres/${m.id}`, { libelle: libelle.trim(), coefficient: coef.replace(",", ".") }))}>Enregistrer</button>
        </div>
      </div>
      {publication && <Publication m={m} mode={publication} onFermer={() => setPublication(null)} onFait={() => { setPublication(null); onChange(); }} />}
    </div>
  );
}

function Publication({ m, mode, onFermer, onFait }: { m: Matiere; mode: "publier" | "retirer"; onFermer: () => void; onFait: () => void }) {
  const [motif, setMotif] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const retirer = mode === "retirer";
  async function valider() {
    setErreur(null);
    try {
      if (retirer) await api.post(`/matieres/${m.id}/depublication`, { motif: motif.trim() });
      else await api.post(`/matieres/${m.id}/publication`);
      onFait();
    } catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <Modale titre={retirer ? "Retirer la publication" : "Publier les notes"} onFermer={onFermer} largeur={500} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className={`btn ${retirer ? "d" : "p"}`} disabled={retirer && motif.trim().length < 10} onClick={() => void valider()}>
        {retirer ? "Retirer la publication" : "Publier"}</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      {retirer ? (
        <>
          <div style={{ marginBottom: 12 }}><Message type="wa">Les étudiants ne verront plus ces notes et la saisie rouvrira. Cette opération est tracée comme une alerte.</Message></div>
          <Champ libelle="Motif" requis aide="10 à 255 caractères, ex. « Ouverture de la session de rattrapage ».">
            <textarea className="in" maxLength={255} value={motif} onChange={(e) => setMotif(e.target.value)} />
          </Champ>
        </>
      ) : (
        <Message type="in">Les notes de {m.libelle} deviendront visibles des étudiants, qui seront prévenus.
          La matière sera ensuite verrouillée : une note ne pourra plus changer qu'à la suite d'une réclamation acceptée.</Message>
      )}
    </Modale>
  );
}

function Creation({ classes, semestres, onFermer, onCree }: { classes: Classe[]; semestres: Semestre[]; onFermer: () => void; onCree: (id: string) => void }) {
  const [classeId, setClasseId] = useState("");
  const [semestreId, setSemestreId] = useState("");
  const [code, setCode] = useState("");
  const [libelle, setLibelle] = useState("");
  const [coef, setCoef] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const valide = /^[A-Z0-9]{2,10}$/.test(code) && libelleValide(libelle) && coefValide(coef);
  async function creer() {
    setErreur(null);
    try {
      const m = await api.post<Matiere>("/matieres", { code, libelle: libelle.trim(), coefficient: coef.replace(",", "."),
        classe_id: classeId || null, semestre_id: semestreId || null });
      onCree(m.id);
    } catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <Modale titre="Nouvelle matière" onFermer={onFermer} largeur={480} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!valide} onClick={() => void creer()}>Créer la matière</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <div className="g2">
        <Champ libelle="Code" requis aide="2 à 10 lettres majuscules ou chiffres.">
          <input className="in mono" maxLength={10} value={code} onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} autoFocus />
        </Champ>
        <Champ libelle="Coefficient" requis><input className="in" inputMode="decimal" maxLength={4} value={coef} onChange={(e) => setCoef(e.target.value)} /></Champ>
      </div>
      <Champ libelle="Libellé" requis><input className="in" maxLength={80} value={libelle} onChange={(e) => setLibelle(e.target.value)} /></Champ>
      <div className="g2">
        <Champ libelle="Classe">
          <select className="in" value={classeId} onChange={(e) => setClasseId(e.target.value)}>
            <option value="">Non rattachée</option>{classes.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}
          </select>
        </Champ>
        <Champ libelle="Semestre">
          <select className="in" value={semestreId} onChange={(e) => setSemestreId(e.target.value)}>
            <option value="">Non rattachée</option>{semestres.map((s) => <option key={s.id} value={s.id}>{s.libelle}</option>)}
          </select>
        </Champ>
      </div>
    </Modale>
  );
}
