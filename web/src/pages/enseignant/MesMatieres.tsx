import { Link } from "react-router-dom";

import { api } from "../../api";
import { TYPES_EVALUATION, date } from "../../format";
import { Gabarit, Message, Statut, useChargement } from "../../ui";
import type { Semestre } from "../admin/Calendrier";

export interface MaMatiere {
  id: string; code: string; libelle: string; coefficient: string; active: boolean;
  notes_saisies: number; notes_modifiees: number; derniere_evaluation: { type: string; date: string } | null;
  classe_id: string | null; semestre: Semestre | null; publiee_le: string | null;
}

/** W3 : matières affectées à l'enseignant pour l'année en cours. */
export default function MesMatieres() {
  const { donnees, erreur, enCours } = useChargement(
    () => api.get<{ annee_academique: string; elements: MaMatiere[] }>("/enseignants/moi/matieres"), []);
  const elements = donnees?.elements ?? [];
  const somme = (f: (m: MaMatiere) => number) => elements.reduce((s, m) => s + f(m), 0);

  return (
    <Gabarit fil={["Enseignement", "Mes matières"]}>
      <div className="phd"><div><h1>Mes matières</h1>
        <p className="sub">Année académique {donnees?.annee_academique ?? "…"} · matières qui vous sont affectées par l'administration</p></div></div>
      {erreur && <Message type="er">{erreur}</Message>}
      <div className="box">
        <table>
          <thead><tr><th>Code</th><th>Matière</th><th className="r">Coef.</th><th className="r">Notes</th><th>Dernière évaluation</th><th>Saisie</th><th /></tr></thead>
          <tbody>
            {elements.map((m) => (
              <tr key={m.id}>
                <td className="mono">{m.code}</td>
                <td><b>{m.libelle}</b>{!m.active && <span className="muet"> · désactivée</span>}</td>
                <td className="r">{m.coefficient.replace(".0", "")}</td>
                <td className="r">{m.notes_saisies}</td>
                <td>{m.derniere_evaluation ? `${TYPES_EVALUATION[m.derniere_evaluation.type]} · ${date(m.derniere_evaluation.date)}` : <span className="muet">Aucune</span>}</td>
                <td>{m.publiee_le ? <Statut ton="ok">Publiée</Statut>
                  : m.semestre && !m.semestre.saisie_ouverte ? <Statut ton="mu">Fenêtre fermée</Statut> : <Statut ton="wa">Ouverte</Statut>}</td>
                <td className="r" style={{ whiteSpace: "nowrap" }}>
                  {m.active && !m.publiee_le && <><Link className="ln" to={`/enseignant/${m.classe_id ? "grille" : "saisie"}?matiere=${m.id}`}>Saisir</Link> &nbsp;·&nbsp; </>}
                  <Link className="ln" to={`/enseignant/notes?matiere=${m.id}`}>Consulter</Link> &nbsp;·&nbsp;
                  <Link className="ln" to={`/enseignant/statistiques?matiere=${m.id}`}>Statistiques</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!enCours && elements.length === 0 && <p className="vide">Aucune matière ne vous est affectée pour cette année.</p>}
      </div>
      <div className="g3" style={{ marginTop: 16 }}>
        <div className="box stat kv"><span>Matières affectées</span><b>{elements.length}</b></div>
        <div className="box stat kv"><span>Notes saisies</span><b>{somme((m) => m.notes_saisies)}</b></div>
        <div className="box stat kv"><span>Notes modifiées</span><b>{somme((m) => m.notes_modifiees)}</b></div>
      </div>
      <div style={{ marginTop: 16, maxWidth: 720 }}>
        <Message type="in">Vous ne pouvez saisir et modifier des notes que dans les matières listées ci-dessus. Pour toute nouvelle affectation, adressez-vous au service de scolarité.</Message>
      </div>
    </Gabarit>
  );
}
