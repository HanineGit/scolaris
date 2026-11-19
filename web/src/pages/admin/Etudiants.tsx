import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, requete } from "../../api";
import { STATUTS_COMPTE } from "../../format";
import { Icone } from "../../icons";
import { Gabarit, Message, Pagination, Statut, useChargement } from "../../ui";
import type { Classe } from "./Classes";

export interface EtudiantVue {
  id: string; matricule: string; nom: string; prenom: string; email: string; statut: string;
  compte: string | null; classe_id: string | null; classe: string | null; cree_le: string; version: number;
}

const TAILLE = 20;

/** W7 : liste des étudiants (F05). */
export default function Etudiants() {
  const naviguer = useNavigate();
  const [q, setQ] = useState("");
  const [recherche, setRecherche] = useState("");
  const [statut, setStatut] = useState("ACTIF");
  const [page, setPage] = useState(1);
  const [parametres, setParametres] = useSearchParams();
  const classe = parametres.get("classe") ?? "";
  const classes = useChargement(() => api.get<{ elements: Classe[] }>("/classes"), []);

  // La recherche part 300 ms après la dernière frappe.
  useEffect(() => { const t = setTimeout(() => setRecherche(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  useEffect(() => setPage(1), [recherche, statut, classe]);

  const liste = useChargement(() => api.get<{ total: number; actifs: number; archives: number; elements: EtudiantVue[] }>(
    `/etudiants${requete({ q: recherche, statut, page, taille: TAILLE, classe_id: classe })}`), [recherche, statut, page, classe]);
  const d = liste.donnees;

  return (
    <Gabarit fil={["Scolarité", "Étudiants"]}>
      <div className="phd">
        <div><h1>Étudiants</h1><p className="sub">{d ? `${d.actifs} actifs · ${d.archives} archivés` : "…"}</p></div>
        <Link className="btn p" to="/admin/etudiants/nouveau"><Icone nom="plus" />Ajouter un étudiant</Link>
      </div>
      {liste.erreur && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur}</Message></div>}
      <div className="box">
        <div className="tb">
          <input className="in" style={{ width: 330 }} placeholder="Rechercher par nom, prénom ou matricule" maxLength={60}
            value={q} onChange={(e) => setQ(e.target.value)} aria-label="Recherche" />
          <select className="in" style={{ width: 170 }} value={statut} onChange={(e) => setStatut(e.target.value)} aria-label="Statut">
            <option value="ACTIF">Statut : Actif</option>
            <option value="ARCHIVE">Statut : Archivé</option>
          </select>
          <select className="in" style={{ width: 210 }} value={classe} aria-label="Classe"
                  onChange={(e) => setParametres(e.target.value ? { classe: e.target.value } : {})}>
            <option value="">Toutes les classes</option>
            {(classes.donnees?.elements ?? []).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.libelle}</option>)}
          </select>
        </div>
        <table>
          <thead><tr><th>Matricule</th><th>Nom</th><th>Prénom</th><th>Classe</th><th>Adresse e-mail</th><th>Compte</th><th>Statut</th></tr></thead>
          <tbody>
            {(d?.elements ?? []).map((e) => {
              const [libelle, ton] = STATUTS_COMPTE[e.compte ?? ""] ?? ["—", "mu"];
              return (
                <tr key={e.id} className="cliquable" onClick={() => naviguer(`/admin/etudiants/${e.id}`)}>
                  <td className="mono">{e.matricule}</td><td>{e.nom}</td><td>{e.prenom}</td>
                  <td>{e.classe ? <span className="pastille">{e.classe}</span> : <span className="muet">–</span>}</td><td>{e.email}</td>
                  <td style={{ color: ton === "ok" ? undefined : `var(--${ton === "mu" ? "fa" : ton})` }}>{libelle}</td>
                  <td><Statut ton={e.statut === "ACTIF" ? "ok" : "mu"}>{e.statut === "ACTIF" ? "Actif" : "Archivé"}</Statut></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {d?.total === 0 && <p className="vide">Aucun étudiant ne correspond à cette recherche.</p>}
        <Pagination page={page} total={d?.total ?? 0} taille={TAILLE} onPage={setPage} />
      </div>
    </Gabarit>
  );
}
