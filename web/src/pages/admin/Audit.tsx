import { useEffect, useState } from "react";

import { api, requete } from "../../api";
import { dateHeure, horodatageUtc } from "../../format";
import { Icone } from "../../icons";
import { Gabarit, Message, Pagination, Statut, messageErreur, useChargement } from "../../ui";

interface Evenement {
  id: string; numero: number; horodatage: string; acteur: string | null; role: string | null; action: string;
  ressource: string | null; ressource_id: string | null; resultat: string; adresse_ip: string | null;
}
interface Detail extends Evenement {
  service: string; id_correlation: string | null; details: Record<string, unknown>; empreinte_precedente: string; empreinte: string;
}
interface Integrite { integre: boolean | null; effectuee_le: string | null; nombre: number; premier_defaut: number | null }

const RESULTATS: Record<string, [string, string]> = {
  SUCCES: ["Succès", "ok"], ECHEC: ["Échec", "er"], REFUSE: ["Refusé", "er"], ALERTE: ["Alerte", "wa"],
};
const TAILLE = 20;
const LIBELLES: Record<string, string> = {
  matiere: "Matière", etudiant: "Étudiant", etudiant_id: "Étudiant (id)", avant: "Ancienne valeur", apres: "Nouvelle valeur",
  motif: "Motif", valeur: "Valeur", evaluation: "Évaluation", date: "Date", matricule: "Matricule", code: "Code",
  role_attribue: "Rôle attribué", origine: "Origine", enseignant_id: "Enseignant (id)", annee: "Année", champ: "Champ",
};

/** W12 : journal d'audit, en lecture seule (F13). */
export default function Audit() {
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [action, setAction] = useState("");
  const [resultat, setResultat] = useState("");
  const [acteur, setActeur] = useState("");
  const [page, setPage] = useState(1);
  const [selection, setSelection] = useState<string | null>(null);
  const [integrite, setIntegrite] = useState<Integrite | null>(null);
  const [erreurVerif, setErreurVerif] = useState<string | null>(null);

  useEffect(() => setPage(1), [du, au, action, resultat, acteur]);
  const actions = useChargement(() => api.get<string[]>("/audit/actions"), []);
  const liste = useChargement(() => api.get<{ total: number; elements: Evenement[] }>(`/audit/evenements${requete({
    du, au, action, resultat, acteur: acteur.trim(), page, taille: TAILLE })}`), [du, au, action, resultat, acteur, page]);
  const detail = useChargement(() => selection ? api.get<Detail>(`/audit/evenements/${selection}`) : Promise.resolve(null), [selection]);
  useEffect(() => { api.get<Integrite>("/audit/integrite").then(setIntegrite).catch(() => undefined); }, []);

  async function verifier() {
    setErreurVerif(null);
    try { setIntegrite(await api.post<Integrite>("/audit/integrite/verification")); } catch (e) { setErreurVerif(messageErreur(e)); }
  }

  const d = detail.donnees;
  return (
    <Gabarit fil={["Administration", "Journal d'audit"]}>
      <div className="phd">
        <div><h1>Journal d'audit</h1><p className="sub">Consultation en lecture seule · conservation 12 mois · {liste.donnees?.total ?? 0} événements</p></div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {integrite?.integre === true && <Message type="ok">Chaîne d'intégrité vérifiée le {dateHeure(integrite.effectuee_le)} ({integrite.nombre} événements)</Message>}
          {integrite?.integre === false && <Message type="er">Rupture de la chaîne détectée à l'événement n° {integrite.premier_defaut}</Message>}
          <button className="btn s" onClick={() => void verifier()}><Icone nom="check" />Vérifier maintenant</button>
        </div>
      </div>
      {(liste.erreur || erreurVerif) && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur ?? erreurVerif}</Message></div>}
      <div style={{ display: "grid", gridTemplateColumns: d ? "1fr 380px" : "1fr", gap: 14, alignItems: "start" }}>
        <div className="box">
          <div className="tb">
            <input className="in" style={{ width: 150 }} type="date" value={du} onChange={(e) => setDu(e.target.value)} aria-label="Du" />
            <input className="in" style={{ width: 150 }} type="date" value={au} onChange={(e) => setAu(e.target.value)} aria-label="Au" />
            <select className="in" style={{ width: 190 }} value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action">
              <option value="">Action : toutes</option>
              {(actions.donnees ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select className="in" style={{ width: 140 }} value={resultat} onChange={(e) => setResultat(e.target.value)} aria-label="Résultat">
              <option value="">Résultat : tous</option>
              {Object.entries(RESULTATS).map(([k, [v]]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input className="in" style={{ width: 130 }} placeholder="Acteur" maxLength={80} value={acteur} onChange={(e) => setActeur(e.target.value)} />
          </div>
          <table>
            <thead><tr><th>Horodatage (UTC)</th><th>Acteur</th><th>Action</th><th>Ressource</th><th>Résultat</th><th>Adresse IP</th></tr></thead>
            <tbody>
              {(liste.donnees?.elements ?? []).map((e) => {
                const [libelle, ton] = RESULTATS[e.resultat] ?? [e.resultat, "mu"];
                return (
                  <tr key={e.id} className={`cliquable${e.id === selection ? " sel" : ""}`} onClick={() => setSelection(e.id)}>
                    <td className="mono">{horodatageUtc(e.horodatage)}</td><td>{e.acteur ?? <span className="muet">système</span>}</td>
                    <td>{e.action}</td><td className="mono">{e.ressource}{e.ressource_id ? `/${e.ressource_id.slice(0, 4)}…${e.ressource_id.slice(-3)}` : ""}</td>
                    <td><Statut ton={ton}>{libelle}</Statut></td><td className="mono">{e.adresse_ip ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {liste.donnees?.total === 0 && <p className="vide">Aucun événement ne correspond à ces filtres.</p>}
          <Pagination page={page} total={liste.donnees?.total ?? 0} taille={TAILLE} onPage={setPage} />
        </div>
        {d && (
          <div className="box">
            <div className="bx-h"><h3>Détail de l'événement</h3><button className="fermer" onClick={() => setSelection(null)} aria-label="Fermer"><Icone nom="x" /></button></div>
            <div className="bx-b" style={{ display: "grid", gridTemplateColumns: "120px 1fr", rowGap: 7, fontSize: 13 }}>
              {([
                ["N°", String(d.numero)], ["Action", d.action], ["Service", d.service],
                ["Acteur", `${d.acteur ?? "système"}${d.role ? ` (${d.role.toLowerCase()})` : ""}`],
                ["Adresse IP", d.adresse_ip ?? "—"], ["Ressource", `${d.ressource ?? ""} ${d.ressource_id ?? ""}`],
                ...Object.entries(d.details).map(([k, v]) => [LIBELLES[k] ?? k, typeof v === "string" ? v : JSON.stringify(v)]),
                ["Corrélation", d.id_correlation ?? "—"], ["Empreinte", d.empreinte],
              ] as [string, string][]).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}>
                  <span style={{ color: "var(--mu)" }}>{k}</span>
                  <b className={k === "Empreinte" || k === "Corrélation" ? "mono" : ""} style={{ fontWeight: k === "Empreinte" ? 400 : 600, wordBreak: "break-all" }}>{v}</b>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Gabarit>
  );
}
