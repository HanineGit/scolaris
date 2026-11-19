import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, telecharger } from "../../api";
import { date } from "../../format";
import { Icone } from "../../icons";
import { Barres, Gabarit, Indicateur, Message, messageErreur, useChargement } from "../../ui";
import type { MaMatiere } from "./MesMatieres";

interface Serie {
  nombre: number; moyenne: number | null; mediane: number | null; minimum: number | null; maximum: number | null;
  ecart_type: number | null; taux_reussite: number | null; repartition: number[];
}
interface Stats { matiere: { code: string; libelle: string }; tranches: string[]; global: Serie;
  evaluations: (Serie & { libelle: string; date_evaluation: string; type_evaluation: string })[] }

const nombre = (v: number | null) => (v === null ? "–" : v.toFixed(2).replace(".", ","));

/** W6 : statistiques d'une matière (F22) et exports (F23). */
export default function Statistiques() {
  const [params] = useSearchParams();
  const matieres = useChargement(() => api.get<{ elements: MaMatiere[] }>("/enseignants/moi/matieres"), []);
  const [matiere, setMatiere] = useState(params.get("matiere") ?? "");
  const [erreur, setErreur] = useState<string | null>(null);
  useEffect(() => { if (!matiere && matieres.donnees?.elements.length) setMatiere(matieres.donnees.elements[0].id); }, [matieres.donnees, matiere]);
  const stats = useChargement(() => matiere ? api.get<Stats>(`/matieres/${matiere}/statistiques`) : Promise.resolve(null), [matiere]);
  const s = stats.donnees;
  const exporter = (format: "pdf" | "xlsx") => telecharger(`/matieres/${matiere}/export?format=${format}`, `notes-${s?.matiere.code}.${format}`)
    .catch((e) => setErreur(messageErreur(e)));

  return (
    <Gabarit fil={["Suivi", "Statistiques"]}>
      <div className="phd"><div><h1>Statistiques</h1><p className="sub">Résultats de la classe par évaluation ; moyennes calculées par étudiant</p></div>
        <div className="actions">
          <select className="in" style={{ width: 280 }} value={matiere} onChange={(e) => setMatiere(e.target.value)} aria-label="Matière">
            {(matieres.donnees?.elements ?? []).map((m) => <option key={m.id} value={m.id}>{m.code} · {m.libelle}</option>)}
          </select>
          <button className="btn s" disabled={!s} onClick={() => void exporter("xlsx")}><Icone nom="download" />Excel</button>
          <button className="btn s" disabled={!s} onClick={() => void exporter("pdf")}><Icone nom="download" />PDF</button>
        </div>
      </div>
      {(stats.erreur || erreur) && <div style={{ marginBottom: 12 }}><Message type="er">{stats.erreur ?? erreur}</Message></div>}
      {s && (
        <>
          <div className="g4" style={{ marginBottom: 16 }}>
            <Indicateur icone="users" libelle="Étudiants notés" valeur={s.global.nombre} />
            <Indicateur icone="chart" libelle="Moyenne de la classe" valeur={nombre(s.global.moyenne)} detail={`Médiane ${nombre(s.global.mediane)}`} />
            <Indicateur icone="check" ton={(s.global.taux_reussite ?? 0) >= 50 ? "ok" : "wa"} libelle="Taux de réussite"
                        valeur={s.global.taux_reussite === null ? "–" : `${String(s.global.taux_reussite).replace(".", ",")} %`} detail="moyennes ≥ 10" />
            <Indicateur icone="bars" libelle="Écart-type" valeur={nombre(s.global.ecart_type)}
                        detail={`Min ${nombre(s.global.minimum)} · max ${nombre(s.global.maximum)}`} />
          </div>
          <div className="box">
            <div className="bx-h"><h3>Répartition des moyennes</h3><span className="muet" style={{ fontSize: 12.5 }}>en rouge : sous 10</span></div>
            <div className="bx-b"><Barres series={s.tranches.map((t, i) => ({ libelle: t, valeur: s.global.repartition[i] }))} seuilBas={(i) => i < 3} /></div>
          </div>
          <div className="box">
            <div className="bx-h"><h3>Par évaluation</h3></div>
            <table>
              <thead><tr><th>Évaluation</th><th>Date</th><th className="r">Notes</th><th className="r">Moyenne</th><th className="r">Médiane</th>
                <th className="r">Min</th><th className="r">Max</th><th className="r">Réussite</th></tr></thead>
              <tbody>
                {s.evaluations.map((e) => (
                  <tr key={`${e.type_evaluation}${e.date_evaluation}`}>
                    <td><b>{e.libelle}</b></td><td>{date(e.date_evaluation)}</td><td className="r">{e.nombre}</td>
                    <td className="r"><b>{nombre(e.moyenne)}</b></td><td className="r">{nombre(e.mediane)}</td>
                    <td className="r">{nombre(e.minimum)}</td><td className="r">{nombre(e.maximum)}</td>
                    <td className="r">{e.taux_reussite === null ? "–" : `${String(e.taux_reussite).replace(".", ",")} %`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {s.evaluations.length === 0 && <p className="vide">Aucune note saisie dans cette matière.</p>}
          </div>
        </>
      )}
    </Gabarit>
  );
}
