import { useState } from "react";

import { api, telecharger } from "../../api";
import { note } from "../../format";
import { Icone } from "../../icons";
import { Gabarit, Indicateur, Message, Statut, messageErreur, useChargement } from "../../ui";
import type { Semestre } from "./Calendrier";
import type { Classe } from "./Classes";

interface Resultat {
  etudiant: { id: string; matricule: string; nom: string; prenom: string };
  moyennes: Record<string, string>; moyenne_generale: string | null; mention: string;
  decision: "ADMIS" | "AJOURNE" | "INCOMPLET"; rang?: number;
}
interface Deliberation {
  classe: { id: string; code: string; libelle: string };
  matieres: { code: string; libelle: string; coefficient: string; publiee: boolean }[];
  resultats: Resultat[]; synthese: { effectif: number; admis: number; ajournes: number; non_publiees: string[] };
}

const DECISIONS = { ADMIS: ["Admis", "ok"], AJOURNE: ["Ajourné", "er"], INCOMPLET: ["Incomplet", "mu"] } as const;

/** W15 : délibération d'une classe et procès-verbal (F26). */
export default function DeliberationPage() {
  const classes = useChargement(() => api.get<{ elements: Classe[] }>("/classes"), []);
  const semestres = useChargement(() => api.get<{ elements: Semestre[] }>("/semestres"), []);
  const [classe, setClasse] = useState("");
  const [semestre, setSemestre] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const d = useChargement(() => classe
    ? api.get<Deliberation>(`/classes/${classe}/deliberation${semestre ? `?semestre_id=${semestre}` : ""}`)
    : Promise.resolve(null), [classe, semestre]);
  const res = d.donnees;
  const tries = [...(res?.resultats ?? [])].sort((a, b) => (a.rang ?? 1e6) - (b.rang ?? 1e6));

  async function exporter() {
    setErreur(null);
    try {
      await telecharger(`/classes/${classe}/deliberation?format=pdf${semestre ? `&semestre_id=${semestre}` : ""}`,
                        `deliberation-${res?.classe.code}.pdf`);
    } catch (e) { setErreur(messageErreur(e)); }
  }

  return (
    <Gabarit fil={["Résultats", "Délibération"]}>
      <div className="phd"><div><h1>Délibération</h1><p className="sub">Moyennes pondérées par les coefficients, décision et rang de chaque étudiant</p></div>
        {res && <button className="btn p" onClick={() => void exporter()}><Icone nom="download" />Procès-verbal (PDF)</button>}
      </div>
      <div className="box"><div className="tb">
        <select className="in" style={{ width: 260 }} value={classe} onChange={(e) => setClasse(e.target.value)} aria-label="Classe">
          <option value="">Choisir une classe</option>
          {(classes.donnees?.elements ?? []).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.libelle}</option>)}
        </select>
        <select className="in" style={{ width: 240 }} value={semestre} onChange={(e) => setSemestre(e.target.value)} aria-label="Semestre">
          <option value="">Année complète</option>
          {(semestres.donnees?.elements ?? []).map((s) => <option key={s.id} value={s.id}>{s.libelle}</option>)}
        </select>
      </div></div>
      {(d.erreur || erreur) && <div style={{ margin: "12px 0" }}><Message type="er">{d.erreur ?? erreur}</Message></div>}
      {!classe && <div style={{ marginTop: 16 }}><Message type="in">Choisissez une classe pour afficher ses résultats.</Message></div>}
      {res && (
        <>
          <div className="g4" style={{ margin: "16px 0" }}>
            <Indicateur icone="users" libelle="Effectif" valeur={res.synthese.effectif} />
            <Indicateur icone="check" ton="ok" libelle="Admis" valeur={res.synthese.admis}
                        detail={res.synthese.effectif ? `${Math.round((100 * res.synthese.admis) / res.synthese.effectif)} % de la classe` : undefined} />
            <Indicateur icone="alert" ton="er" libelle="Ajournés" valeur={res.synthese.ajournes} />
            <Indicateur icone="lock" ton={res.synthese.non_publiees.length ? "wa" : "ok"} libelle="Matières non publiées"
                        valeur={res.synthese.non_publiees.length} detail={res.synthese.non_publiees.join(", ") || "Toutes publiées"} />
          </div>
          {res.synthese.non_publiees.length > 0 && <div style={{ marginBottom: 12 }}>
            <Message type="wa">Certaines matières ne sont pas encore publiées : les résultats ci-dessous sont provisoires.</Message></div>}
          <div className="box defile">
            <table>
              <thead><tr><th className="r">Rang</th><th>Matricule</th><th>Étudiant</th>
                {res.matieres.map((m) => <th key={m.code} className="r" title={`${m.libelle} · coef. ${m.coefficient}`}>{m.code}<br /><span style={{ fontWeight: 500 }}>×{m.coefficient.replace(".0", "")}</span></th>)}
                <th className="r">Moyenne</th><th>Mention</th><th>Décision</th></tr></thead>
              <tbody>
                {tries.map((r) => {
                  const [libelle, ton] = DECISIONS[r.decision];
                  return (
                    <tr key={r.etudiant.id}>
                      <td className="r"><b>{r.rang ?? "–"}</b></td><td className="mono">{r.etudiant.matricule}</td>
                      <td>{r.etudiant.nom} {r.etudiant.prenom}</td>
                      {res.matieres.map((m) => {
                        const v = r.moyennes[m.code];
                        return <td key={m.code} className="r" style={{ color: v && Number(v) < 10 ? "var(--er)" : undefined }}>{v ? note(v) : <span className="muet">–</span>}</td>;
                      })}
                      <td className="r"><b>{r.moyenne_generale ? note(r.moyenne_generale) : "–"}</b></td>
                      <td>{r.mention}</td><td><Statut ton={ton}>{libelle}</Statut></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {tries.length === 0 && <p className="vide">Aucun étudiant inscrit dans cette classe.</p>}
          </div>
        </>
      )}
    </Gabarit>
  );
}
