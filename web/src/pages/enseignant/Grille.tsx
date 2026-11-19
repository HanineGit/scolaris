import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api";
import { TYPES_EVALUATION, lireNote, note } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Statut, messageErreur, useChargement } from "../../ui";
import type { MaMatiere } from "./MesMatieres";

interface Ligne { etudiant: { id: string; matricule: string; nom: string; prenom: string; statut: string }; note: { valeur: string } | null }
interface GrilleVue {
  matiere: { code: string; libelle: string; publiee_le: string | null };
  classe: { code: string; libelle: string | null };
  saisie_possible: boolean; verrou: { code: string; message: string } | null; lignes: Ligne[];
}
const aujourdhui = () => new Date().toISOString().slice(0, 10);

/** W5 : saisie des notes d'une évaluation pour toute la classe (F21). */
export default function Grille() {
  const [params] = useSearchParams();
  const matieres = useChargement(() => api.get<{ elements: MaMatiere[] }>("/enseignants/moi/matieres"), []);
  const avecClasse = (matieres.donnees?.elements ?? []).filter((m) => m.active && m.classe_id);
  const [matiere, setMatiere] = useState(params.get("matiere") ?? "");
  const [type, setType] = useState("EXAMEN");
  const [jour, setJour] = useState(aujourdhui());
  const [saisies, setSaisies] = useState<Record<string, string>>({});
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const champs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => { if (!matiere && avecClasse.length) setMatiere(avecClasse[0].id); }, [avecClasse, matiere]);
  const grille = useChargement(() => matiere
    ? api.get<GrilleVue>(`/matieres/${matiere}/grille?type_evaluation=${type}&date_evaluation=${jour}`)
    : Promise.resolve(null), [matiere, type, jour]);
  useEffect(() => { setSaisies({}); setSucces(null); setErreur(null); }, [matiere, type, jour]);

  const g = grille.donnees;
  const aSaisir = (g?.lignes ?? []).filter((l) => !l.note && l.etudiant.statut === "ACTIF");
  const remplies = useMemo(() => Object.entries(saisies).filter(([, v]) => v.trim() !== ""), [saisies]);
  const invalides = remplies.filter(([, v]) => lireNote(v) === null).length;
  const valeurs = remplies.map(([, v]) => Number(lireNote(v))).filter((v) => !Number.isNaN(v));
  const moyenne = valeurs.length ? valeurs.reduce((a, b) => a + b, 0) / valeurs.length : null;

  async function enregistrer() {
    setErreur(null); setSucces(null); setEnCours(true);
    try {
      const r = await api.post<{ enregistrees: number }>(`/matieres/${matiere}/evaluations`, {
        type_evaluation: type, date_evaluation: jour,
        notes: remplies.map(([id, v]) => ({ etudiant_id: id, valeur: lireNote(v) })),
      });
      setSucces(`${r.enregistrees} note(s) enregistrée(s).`);
      setSaisies({});
      grille.recharger();
    } catch (e) { setErreur(messageErreur(e)); } finally { setEnCours(false); }
  }

  return (
    <Gabarit fil={["Enseignement", "Saisie par classe"]}>
      <div className="phd"><div><h1>Saisie par classe</h1>
        <p className="sub">Une évaluation, toute la classe : l'enregistrement est global, aucune note n'est gardée si l'une d'elles est refusée</p></div></div>
      <div className="box"><div className="bx-b">
        <div className="g3">
          <Champ libelle="Matière">
            <select className="in" value={matiere} onChange={(e) => setMatiere(e.target.value)}>
              {avecClasse.length === 0 && <option value="">Aucune matière rattachée à une classe</option>}
              {avecClasse.map((m) => <option key={m.id} value={m.id}>{m.code} · {m.libelle}</option>)}
            </select>
          </Champ>
          <Champ libelle="Évaluation">
            <select className="in" value={type} onChange={(e) => setType(e.target.value)}>
              {Object.entries(TYPES_EVALUATION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Champ>
          <Champ libelle="Date de l'évaluation"><input className="in" type="date" max={aujourdhui()} value={jour} onChange={(e) => setJour(e.target.value)} /></Champ>
        </div>
      </div></div>

      {(grille.erreur || erreur) && <div style={{ marginTop: 12 }}><Message type="er">{grille.erreur ?? erreur}</Message></div>}
      {succes && <div style={{ marginTop: 12 }}><Message type="ok">{succes}</Message></div>}
      {g?.verrou && <div style={{ marginTop: 12 }}><Message type="wa">{g.verrou.message}</Message></div>}

      {g && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 16, alignItems: "start", marginTop: 16 }}>
          <div className="box">
            <div className="bx-h"><h3>{g.classe.code} · {g.lignes.length} étudiant(s)</h3>
              <span className="muet" style={{ fontSize: 12.5 }}>Entrée : étudiant suivant</span></div>
            <table className="grille">
              <thead><tr><th>Matricule</th><th>Nom et prénom</th><th className="r">Note / 20</th><th>État</th></tr></thead>
              <tbody>
                {g.lignes.map((l) => {
                  const v = saisies[l.etudiant.id] ?? "";
                  const faux = v.trim() !== "" && lireNote(v) === null;
                  const index = aSaisir.findIndex((x) => x.etudiant.id === l.etudiant.id);
                  return (
                    <tr key={l.etudiant.id} className={v.trim() && !faux ? "modifie" : ""}>
                      <td className="mono">{l.etudiant.matricule}</td>
                      <td>{l.etudiant.nom} {l.etudiant.prenom}</td>
                      <td className="r">
                        {l.note ? <b>{note(l.note.valeur)}</b> : l.etudiant.statut !== "ACTIF" ? <span className="muet">archivé</span> : (
                          <input ref={(el) => { champs.current[index] = el; }} className={`in${faux ? " e" : ""}`} inputMode="decimal" maxLength={5}
                            aria-label={`Note de ${l.etudiant.nom} ${l.etudiant.prenom}`} disabled={!g.saisie_possible} value={v}
                            onChange={(e) => setSaisies((s) => ({ ...s, [l.etudiant.id]: e.target.value }))}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); champs.current[index + 1]?.focus(); } }} />
                        )}
                      </td>
                      <td>{l.note ? <Statut ton="ok">Saisie</Statut> : faux ? <Statut ton="er">Invalide</Statut> : v.trim() ? <Statut ton="wa">À enregistrer</Statut> : <span className="muet">–</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {g.lignes.length === 0 && <p className="vide">Aucun étudiant inscrit dans cette classe.</p>}
          </div>

          <div className="box" style={{ position: "sticky", top: 78, marginTop: 0 }}>
            <div className="bx-h"><h3>Récapitulatif</h3></div>
            <div className="bx-b">
              <div className="kv" style={{ marginBottom: 10 }}><span>Notes à enregistrer</span><b>{remplies.length} / {aSaisir.length}</b></div>
              <div className="kv" style={{ marginBottom: 10 }}><span>Moyenne provisoire</span><b>{moyenne === null ? "–" : moyenne.toFixed(2).replace(".", ",")}</b></div>
              {invalides > 0 && <div style={{ marginBottom: 10 }}><Message type="er">{invalides} valeur(s) invalide(s) : entre 0 et 20, deux décimales au plus.</Message></div>}
              <button className="btn p plein" disabled={!g.saisie_possible || remplies.length === 0 || invalides > 0 || enCours} onClick={() => void enregistrer()}>
                <Icone nom="check" />Enregistrer {remplies.length || ""} note(s)</button>
              <p className="help" style={{ marginTop: 10 }}>Les notes restent invisibles des étudiants jusqu'à leur publication par l'administration.</p>
            </div>
          </div>
        </div>
      )}
    </Gabarit>
  );
}
