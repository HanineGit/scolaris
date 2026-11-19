import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api";
import { anneeCourante } from "../../format";
import { Icone } from "../../icons";
import { Champ, Gabarit, Message, Modale, Statut, messageErreur, useChargement } from "../../ui";

export interface Classe {
  id: string; code: string; libelle: string; filiere: string; niveau: string; annee_academique: string; active: boolean; effectif: number;
}
interface LigneRapport { ligne: number; nom: string | null; prenom: string | null; email: string | null; erreurs: string[] }
interface Rapport { lignes: number; valides: number; invalides: number; importes: number; rapport: LigneRapport[] }

const NIVEAUX = ["L1", "L2", "L3", "M1", "M2"];
const TAILLE_MAX = 1_000_000;

/** W13 : classes (promotions) de l'année et import d'une promotion (F15, F16). */
export default function Classes() {
  const [annee, setAnnee] = useState(anneeCourante());
  const liste = useChargement(() => api.get<{ elements: Classe[] }>(`/classes?annee=${annee}`), [annee]);
  const [creation, setCreation] = useState(false);
  const [importClasse, setImportClasse] = useState<Classe | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const elements = liste.donnees?.elements ?? [];

  async function basculer(c: Classe) {
    setErreur(null);
    try { await api.patch(`/classes/${c.id}`, { active: !c.active }); liste.recharger(); } catch (e) { setErreur(messageErreur(e)); }
  }

  return (
    <Gabarit fil={["Scolarité", "Classes et inscriptions"]}>
      <div className="phd">
        <div><h1>Classes et inscriptions</h1><p className="sub">Promotions de l'année, effectifs et import d'une liste d'étudiants</p></div>
        <div className="actions">
          <select className="in" style={{ width: 150 }} value={annee} onChange={(e) => setAnnee(e.target.value)} aria-label="Année académique">
            {[0, -1, -2].map((d) => { const a = Number(anneeCourante().slice(0, 4)) + d; return <option key={a}>{`${a}-${a + 1}`}</option>; })}
          </select>
          <button className="btn p" onClick={() => setCreation(true)}><Icone nom="plus" />Nouvelle classe</button>
        </div>
      </div>
      {(liste.erreur || erreur) && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur ?? erreur}</Message></div>}
      <div className="box">
        <table>
          <thead><tr><th>Code</th><th>Libellé</th><th>Filière</th><th>Niveau</th><th className="r">Effectif</th><th>État</th><th /></tr></thead>
          <tbody>
            {elements.map((c) => (
              <tr key={c.id}>
                <td className="mono"><b>{c.code}</b></td><td>{c.libelle}</td><td>{c.filiere}</td>
                <td><span className="pastille">{c.niveau}</span></td><td className="r"><b>{c.effectif}</b></td>
                <td><Statut ton={c.active ? "ok" : "mu"}>{c.active ? "Ouverte" : "Fermée"}</Statut></td>
                <td className="r" style={{ whiteSpace: "nowrap" }}>
                  <Link className="ln" to={`/admin/etudiants?classe=${c.id}`}>Étudiants</Link> &nbsp;·&nbsp;
                  {c.active && <><button className="lien" onClick={() => setImportClasse(c)}>Importer</button> &nbsp;·&nbsp; </>}
                  <button className="lien" onClick={() => void basculer(c)}>{c.active ? "Fermer" : "Rouvrir"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!liste.enCours && elements.length === 0 && <p className="vide">Aucune classe pour {annee}. Créez la première avec « Nouvelle classe ».</p>}
      </div>
      <div style={{ marginTop: 16, maxWidth: 760 }}>
        <Message type="in">Une classe fermée n'accepte plus d'inscription. Les matières se rattachent à une classe dans « Matières et publication ».</Message>
      </div>
      {creation && <Creation annee={annee} onFermer={() => setCreation(false)} onCree={() => { setCreation(false); liste.recharger(); }} />}
      {importClasse && <Import classe={importClasse} onFermer={() => setImportClasse(null)} onImporte={liste.recharger} />}
    </Gabarit>
  );
}

function Creation({ annee, onFermer, onCree }: { annee: string; onFermer: () => void; onCree: () => void }) {
  const [code, setCode] = useState("");
  const [libelle, setLibelle] = useState("");
  const [filiere, setFiliere] = useState("");
  const [niveau, setNiveau] = useState("L1");
  const [erreur, setErreur] = useState<string | null>(null);
  const valide = /^[A-Z0-9][A-Z0-9-]{1,11}$/.test(code) && libelle.trim().length >= 3 && filiere.trim().length >= 2;
  async function creer() {
    setErreur(null);
    try {
      await api.post("/classes", { code, libelle: libelle.trim(), filiere: filiere.trim(), niveau, annee_academique: annee });
      onCree();
    } catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <Modale titre={`Nouvelle classe · ${annee}`} onFermer={onFermer} largeur={520} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!valide} onClick={() => void creer()}>Créer la classe</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <div className="g2">
        <Champ libelle="Code" requis aide="Ex. L2-INFO (12 caractères au plus).">
          <input className="in mono" maxLength={12} value={code} autoFocus onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, ""))} />
        </Champ>
        <Champ libelle="Niveau" requis>
          <select className="in" value={niveau} onChange={(e) => setNiveau(e.target.value)}>{NIVEAUX.map((n) => <option key={n}>{n}</option>)}</select>
        </Champ>
      </div>
      <Champ libelle="Libellé" requis><input className="in" maxLength={80} value={libelle} placeholder="Licence 2 Informatique" onChange={(e) => setLibelle(e.target.value)} /></Champ>
      <Champ libelle="Filière" requis><input className="in" maxLength={60} value={filiere} placeholder="Informatique" onChange={(e) => setFiliere(e.target.value)} /></Champ>
    </Modale>
  );
}

function Import({ classe, onFermer, onImporte }: { classe: Classe; onFermer: () => void; onImporte: () => void }) {
  const [contenu, setContenu] = useState<string | null>(null);
  const [nom, setNom] = useState("");
  const [rapport, setRapport] = useState<Rapport | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  async function lireFichier(f: File | undefined) {
    setRapport(null); setErreur(null);
    if (!f) return;
    if (f.size > TAILLE_MAX) { setErreur("Le fichier dépasse 1 Mo."); return; }
    if (!/\.(csv|txt)$/i.test(f.name)) { setErreur("Choisissez un fichier .csv."); return; }
    setNom(f.name);
    const texte = await f.text();
    setContenu(texte);
    await envoyer(texte, false);
  }
  async function envoyer(texte: string, confirmer: boolean) {
    setEnCours(true); setErreur(null);
    try {
      const r = await api.post<Rapport>("/etudiants/import", { contenu: texte, classe_id: classe.id, confirmer });
      setRapport(r);
      if (confirmer) onImporte();
    } catch (e) { setErreur(messageErreur(e)); } finally { setEnCours(false); }
  }

  const termine = (rapport?.importes ?? 0) > 0;
  return (
    <Modale titre={`Importer des étudiants · ${classe.code}`} onFermer={onFermer} largeur={760} pied={<>
      <button className="btn s" onClick={onFermer}>{termine ? "Fermer" : "Annuler"}</button>
      {!termine && <button className="btn p" disabled={!contenu || !rapport || rapport.invalides > 0 || enCours}
        onClick={() => contenu && void envoyer(contenu, true)}>Importer {rapport?.valides ?? 0} étudiant(s)</button>}</>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      {termine ? (
        <Message type="ok">{rapport!.importes} étudiant(s) inscrits dans {classe.code}. Chacun reçoit son lien d'activation par e-mail.</Message>
      ) : (
        <>
          <p style={{ fontSize: 13.5, color: "var(--tx2)", marginBottom: 10 }}>
            Fichier CSV avec les colonnes <span className="mono">nom</span>, <span className="mono">prenom</span>, <span className="mono">email</span> (séparateur « ; » ou « , »), 1 000 lignes au plus.
            Le fichier est d'abord vérifié : rien n'est enregistré tant qu'une ligne est en erreur.
          </p>
          <label className="btn s" style={{ marginBottom: 12 }}>
            <Icone nom="upload" />{nom || "Choisir un fichier"}
            <input type="file" accept=".csv,text/csv" hidden onChange={(e) => void lireFichier(e.target.files?.[0])} />
          </label>
          {rapport && (
            <>
              <div style={{ marginBottom: 10 }}>
                <Message type={rapport.invalides ? "wa" : "ok"}>
                  {rapport.lignes} ligne(s) lues : {rapport.valides} valide(s), {rapport.invalides} en erreur.
                  {rapport.invalides > 0 && " Corrigez le fichier puis choisissez-le de nouveau."}
                </Message>
              </div>
              <div className="box defile" style={{ maxHeight: 320, overflowY: "auto" }}>
                <table>
                  <thead><tr><th className="r">Ligne</th><th>Nom</th><th>Prénom</th><th>E-mail</th><th>Contrôle</th></tr></thead>
                  <tbody>
                    {rapport.rapport.map((l) => (
                      <tr key={l.ligne}>
                        <td className="r mono">{l.ligne}</td><td>{l.nom ?? <span className="muet">–</span>}</td>
                        <td>{l.prenom ?? <span className="muet">–</span>}</td><td>{l.email ?? <span className="muet">–</span>}</td>
                        <td>{l.erreurs.length ? <Statut ton="er">{l.erreurs.join(", ")}</Statut> : <Statut ton="ok">Valide</Statut>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </Modale>
  );
}
