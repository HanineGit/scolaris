import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, requete } from "../../api";
import { TYPES_EVALUATION, date, dateHeure, lireNote, note } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Modale, Pagination, messageErreur, useChargement } from "../../ui";
import type { MaMatiere } from "./MesMatieres";

export interface NoteVue {
  id: string; matiere_id: string; matiere_code: string; matiere_libelle: string; etudiant_id: string;
  etudiant: { matricule: string; nom: string; prenom: string } | null; type_evaluation: string;
  date_evaluation: string; valeur: string; saisie_par: string; saisie_le: string; modifie_le: string | null; version: number;
}
interface Historique { date: string; auteur: string; avant: string | null; apres: string; motif: string }

const TAILLE = 20;

/** W5 et W6 : notes d'une matière, modification motivée et historique (F09, F10). */
export default function Notes() {
  const [params, setParams] = useSearchParams();
  const matieres = useChargement(() => api.get<{ elements: MaMatiere[] }>("/enseignants/moi/matieres"), []);
  const liste = matieres.donnees?.elements ?? [];
  const matiere = params.get("matiere") ?? liste[0]?.id ?? "";
  const [type, setType] = useState("");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [matricule, setMatricule] = useState("");
  const [page, setPage] = useState(1);
  const [aModifier, setAModifier] = useState<NoteVue | null>(null);
  const [historique, setHistorique] = useState<NoteVue | null>(null);

  useEffect(() => setPage(1), [matiere, type, du, au, matricule]);
  const filtreMatricule = /^ETU-\d{4}-\d{4}$/.test(matricule) ? matricule : undefined;
  const notes = useChargement(
    () => matiere ? api.get<{ total: number; elements: NoteVue[] }>(`/matieres/${matiere}/notes${requete({
      type_evaluation: type, du, au, matricule: filtreMatricule, page, taille: TAILLE })}`) : Promise.resolve({ total: 0, elements: [] }),
    [matiere, type, du, au, filtreMatricule, page]);
  const m = liste.find((x) => x.id === matiere);

  return (
    <Gabarit fil={["Enseignement", "Consultation des notes"]}>
      <div className="phd">
        <div><h1>Notes de la matière</h1><p className="sub">{m ? `${m.libelle} (${m.code}) · ${notes.donnees?.total ?? 0} notes` : "—"}</p></div>
        {m?.active && <Link className="btn p" to={`/enseignant/saisie?matiere=${matiere}`}><Icone nom="plus" />Enregistrer une note</Link>}
      </div>
      {notes.erreur && <div style={{ marginBottom: 12 }}><Message type="er">{notes.erreur}</Message></div>}
      <div className="box">
        <div className="tb">
          <select className="in" style={{ width: 250 }} value={matiere} onChange={(e) => setParams({ matiere: e.target.value })} aria-label="Matière">
            {liste.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.libelle}</option>)}
          </select>
          <select className="in" style={{ width: 190 }} value={type} onChange={(e) => setType(e.target.value)} aria-label="Évaluation">
            <option value="">Toutes les évaluations</option>
            {Object.entries(TYPES_EVALUATION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input className="in" type="date" value={du} onChange={(e) => setDu(e.target.value)} aria-label="Du" />
          <input className="in" type="date" value={au} onChange={(e) => setAu(e.target.value)} aria-label="Au" />
          <input className="in mono" style={{ width: 170 }} placeholder="Matricule" maxLength={13} value={matricule}
            onChange={(e) => setMatricule(e.target.value.toUpperCase())} aria-label="Matricule" />
        </div>
        <table>
          <thead><tr><th>Matricule</th><th>Étudiant</th><th>Évaluation</th><th>Date</th><th className="r">Note /20</th><th>Dernière modification</th><th /></tr></thead>
          <tbody>
            {(notes.donnees?.elements ?? []).map((n) => (
              <tr key={n.id}>
                <td className="mono">{n.etudiant?.matricule ?? "—"}</td>
                <td>{n.etudiant ? `${n.etudiant.nom} ${n.etudiant.prenom}` : "—"}</td>
                <td>{TYPES_EVALUATION[n.type_evaluation]}</td>
                <td>{date(n.date_evaluation)}</td>
                <td className="r"><b>{note(n.valeur)}</b></td>
                <td>{n.modifie_le ? dateHeure(n.modifie_le) : <span className="muet">—</span>}</td>
                <td className="r">
                  {m?.active && <button className="lien" onClick={() => setAModifier(n)}>Modifier</button>}
                  {n.modifie_le && <> · <button className="lien" onClick={() => setHistorique(n)}>Historique</button></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {notes.donnees?.total === 0 && <p className="vide">Aucune note ne correspond à ces critères.</p>}
        <Pagination page={page} total={notes.donnees?.total ?? 0} taille={TAILLE} onPage={setPage} />
      </div>
      {aModifier && <ModifierNote n={aModifier} onFermer={() => setAModifier(null)} onModifiee={() => { setAModifier(null); notes.recharger(); }} />}
      {historique && (
        <Modale titre="Historique de la note" onFermer={() => setHistorique(null)} largeur={640}>
          <TableHistorique noteId={historique.id} />
        </Modale>
      )}
    </Gabarit>
  );
}

export function TableHistorique({ noteId }: { noteId: string }) {
  const h = useChargement(() => api.get<{ elements: Historique[] }>(`/notes/${noteId}/historique`), [noteId]);
  if (h.erreur) return <Message type="er">{h.erreur}</Message>;
  return (
    <table style={{ border: "1px solid var(--line)" }}>
      <thead><tr><th>Date</th><th>Auteur</th><th className="r">Avant</th><th className="r">Après</th><th>Motif</th></tr></thead>
      <tbody>
        {(h.donnees?.elements ?? []).map((l, i) => (
          <tr key={i}><td>{dateHeure(l.date)}</td><td>{l.auteur}</td><td className="r">{note(l.avant)}</td><td className="r">{note(l.apres)}</td><td>{l.motif}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function ModifierNote({ n, onFermer, onModifiee }: { n: NoteVue; onFermer: () => void; onModifiee: () => void }) {
  const [valeur, setValeur] = useState("");
  const [motif, setMotif] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const v = lireNote(valeur);
  const motifValide = motif.trim().length >= 10 && motif.length <= 255 && !/[<>]/.test(motif);

  async function confirmer() {
    setEnCours(true);
    setErreur(null);
    try {
      await api.put(`/notes/${n.id}`, { valeur: v, motif: motif.trim(), version: n.version });
      onModifiee();
    } catch (e) {
      setErreur(messageErreur(e));
      setEnCours(false);
    }
  }

  return (
    <Modale titre="Modifier une note" onFermer={onFermer} largeur={650} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!v || !motifValide || enCours || v === n.valeur} onClick={() => void confirmer()}>Confirmer la modification</button>
    </>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <div className="g3" style={{ marginBottom: 14, padding: "10px 12px", background: "var(--sand2)", border: "1px solid var(--line2)", borderRadius: 4 }}>
        <div className="kv"><span>Étudiant</span><b>{n.etudiant ? `${n.etudiant.nom} ${n.etudiant.prenom}` : "—"}</b></div>
        <div className="kv"><span>Évaluation</span><b>{TYPES_EVALUATION[n.type_evaluation]}</b></div>
        <div className="kv"><span>Date</span><b>{date(n.date_evaluation)}</b></div>
      </div>
      <div className="g2">
        <Champ libelle="Valeur actuelle"><input className="in" readOnly value={note(n.valeur)} /></Champ>
        <Champ libelle="Nouvelle valeur" requis erreur={valeur && !v ? "Entre 0 et 20, deux décimales au plus." : null}>
          <input className="in" inputMode="decimal" maxLength={5} value={valeur} onChange={(e) => setValeur(e.target.value)} autoFocus />
        </Champ>
      </div>
      <Champ libelle="Motif de la modification" requis aide={`${motif.length} / 255 caractères (10 au minimum)`}
        erreur={/[<>]/.test(motif) ? "Les chevrons < et > ne sont pas autorisés." : null}>
        <textarea className="in" maxLength={255} value={motif} onChange={(e) => setMotif(e.target.value)} />
      </Champ>
      <label className="lbl">Historique de la note</label>
      <TableHistorique noteId={n.id} />
      <div style={{ marginTop: 14 }}>
        <Message type="wa">La modification sera ajoutée à l'historique et au journal d'audit avec votre identifiant. L'étudiant verra la mention « modifiée ».</Message>
      </div>
    </Modale>
  );
}
