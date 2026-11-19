import { Link } from "react-router-dom";

import { api } from "../../api";
import { dateHeure } from "../../format";
import { Barres, Gabarit, Indicateur, Message, useChargement } from "../../ui";

interface Scolarite { actifs: number; archives: number; sans_classe: number; annee_academique: string; par_classe: { code: string; libelle: string; effectif: number }[] }
interface Notes {
  notes_total: number; notes_7_jours: number; saisies_par_jour: { jour: string; notes: number }[];
  matieres_actives: number; matieres_publiees: number; reclamations_ouvertes: number; fenetres_ouvertes: string[];
  moyennes_par_matiere: { code: string; libelle: string; moyenne: number }[];
}
interface Securite { connexions_24h: number; echecs_24h: number; verrouillages_24h: number; comptes_verrouilles: number; comptes_en_attente: number }
interface Evenement { numero: number; horodatage: string; action: string; resultat: string; acteur: string | null }

/** Chaque service est interrogé séparément : l'indisponibilité de l'un n'empêche pas d'afficher les autres. */
function tenter<T>(f: () => Promise<T>) {
  return f().catch(() => null);
}

/** W0 : tableau de bord de l'administrateur (F25). */
export default function TableauDeBord() {
  const { donnees, enCours } = useChargement(async () => {
    const [scolarite, notes, securite, audit] = await Promise.all([
      tenter(() => api.get<Scolarite>("/etudiants/statistiques")),
      tenter(() => api.get<Notes>("/notes/statistiques")),
      tenter(() => api.get<Securite>("/admin/securite")),
      tenter(() => api.get<{ elements: Evenement[] }>("/audit/evenements?taille=8")),
    ]);
    return { scolarite, notes, securite, audit };
  }, []);
  const s = donnees?.scolarite, n = donnees?.notes, sec = donnees?.securite;
  const alerteSecurite = (sec?.echecs_24h ?? 0) >= 10 || (sec?.comptes_verrouilles ?? 0) > 0;

  return (
    <Gabarit fil={["Pilotage", "Tableau de bord"]}>
      <div className="phd"><div><h1>Tableau de bord</h1>
        <p className="sub">Année académique {s?.annee_academique ?? "…"} · vue d'ensemble de la scolarité, des notes et de la sécurité</p></div></div>
      {!enCours && donnees && Object.values(donnees).some((v) => v === null) && (
        <div style={{ marginBottom: 14 }}><Message type="wa">Certains indicateurs sont momentanément indisponibles.</Message></div>
      )}

      <div className="g4" style={{ marginBottom: 16 }}>
        <Indicateur icone="users" libelle="Étudiants actifs" valeur={s?.actifs ?? "–"} detail={s ? `${s.sans_classe} sans classe · ${s.archives} archivés` : undefined} />
        <Indicateur icone="edit" libelle="Notes saisies (7 jours)" valeur={n?.notes_7_jours ?? "–"} detail={n ? `${n.notes_total} au total` : undefined} />
        <Indicateur icone="file" ton="ok" libelle="Matières publiées" valeur={n ? `${n.matieres_publiees} / ${n.matieres_actives}` : "–"}
                    detail={n?.fenetres_ouvertes.length ? `Saisie ouverte : ${n.fenetres_ouvertes.join(", ")}` : "Aucune fenêtre de saisie ouverte"} />
        <Indicateur icone="message" ton={n?.reclamations_ouvertes ? "wa" : undefined} libelle="Réclamations en cours"
                    valeur={n?.reclamations_ouvertes ?? "–"} detail={<Link className="ln" to="/admin/reclamations">Voir</Link>} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 16, alignItems: "start" }}>
        <div>
          <div className="box">
            <div className="bx-h"><h3>Notes saisies sur 14 jours</h3></div>
            <div className="bx-b">
              <Barres series={(n?.saisies_par_jour ?? []).map((j) => ({ libelle: j.jour.slice(8, 10), valeur: j.notes }))} />
            </div>
          </div>
          <div className="box">
            <div className="bx-h"><h3>Moyenne par matière</h3><span className="muet" style={{ fontSize: 12.5 }}>en rouge : sous 10</span></div>
            <table>
              <tbody>
                {(n?.moyennes_par_matiere ?? []).map((m) => (
                  <tr key={m.code}>
                    <td className="mono" style={{ width: 90 }}>{m.code}</td><td>{m.libelle}</td>
                    <td style={{ width: "34%" }}><div className="jauge"><i style={{ width: `${(m.moyenne / 20) * 100}%`, background: m.moyenne < 10 ? "var(--er)" : undefined }} /></div></td>
                    <td className="r" style={{ width: 70 }}><b>{m.moyenne.toFixed(2).replace(".", ",")}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {n?.moyennes_par_matiere.length === 0 && <p className="vide">Aucune note saisie pour l'instant.</p>}
          </div>
        </div>

        <div>
          <div className="box">
            <div className="bx-h"><h3>Sécurité (24 heures)</h3></div>
            <div className="bx-b">
              {alerteSecurite && <div style={{ marginBottom: 12 }}><Message type="wa">Activité inhabituelle : vérifiez le journal d'audit.</Message></div>}
              <div className="g2">
                <div className="kv"><span>Connexions réussies</span><b>{sec?.connexions_24h ?? "–"}</b></div>
                <div className="kv"><span>Échecs de connexion</span><b style={{ color: (sec?.echecs_24h ?? 0) >= 10 ? "var(--er)" : undefined }}>{sec?.echecs_24h ?? "–"}</b></div>
                <div className="kv"><span>Comptes verrouillés</span><b style={{ color: sec?.comptes_verrouilles ? "var(--er)" : undefined }}>{sec?.comptes_verrouilles ?? "–"}</b></div>
                <div className="kv"><span>Comptes en attente d'activation</span><b>{sec?.comptes_en_attente ?? "–"}</b></div>
              </div>
            </div>
          </div>
          <div className="box">
            <div className="bx-h"><h3>Effectifs par classe</h3><Link className="ln" to="/admin/classes">Gérer</Link></div>
            <table><tbody>
              {(s?.par_classe ?? []).map((c) => <tr key={c.code}><td className="mono">{c.code}</td><td>{c.libelle}</td><td className="r"><b>{c.effectif}</b></td></tr>)}
            </tbody></table>
            {s?.par_classe.length === 0 && <p className="vide">Aucune classe pour cette année.</p>}
          </div>
          <div className="box">
            <div className="bx-h"><h3>Activité récente</h3><Link className="ln" to="/admin/audit">Journal complet</Link></div>
            <ul className="chrono">
              {(donnees?.audit?.elements ?? []).map((e) => (
                <li key={e.numero}>
                  <span className={`pt${e.resultat === "SUCCES" ? " ok" : e.resultat === "ALERTE" || e.resultat === "REFUSE" ? " er" : ""}`} />
                  <span><b style={{ fontSize: 12.5 }}>{e.action.replaceAll("_", " ").toLowerCase()}</b>
                    <span className="muet"> · {e.acteur ?? "système"}</span></span>
                  <time>{dateHeure(e.horodatage)}</time>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </Gabarit>
  );
}
