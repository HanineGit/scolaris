import { useEffect, useState } from "react";

import { api, requete } from "../../api";
import { STATUTS_COMPTE, dateHeure, emailValide, nomValide } from "../../format";
import { Icone } from "../../icons";
import { useSession } from "../../session";
import { Champ, Gabarit, Message, Pagination, Statut, messageErreur, useChargement } from "../../ui";

interface Compte {
  id: string; identifiant: string; email: string; nom: string | null; prenom: string | null;
  role: string; statut: string; derniere_connexion: string | null;
}
const ROLES: Record<string, [string, string]> = {
  ENSEIGNANT: ["Enseignant", "Saisie et modification des notes des matières affectées"],
  ADMINISTRATEUR: ["Administrateur", "Étudiants, matières, comptes et journal d'audit"],
};
const TAILLE = 20;

/** W11 : comptes du personnel et rôles (F03). */
export default function Comptes() {
  const { utilisateur } = useSession();
  const [q, setQ] = useState("");
  const [recherche, setRecherche] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(1);
  const [panneau, setPanneau] = useState<"creer" | Compte | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => { const t = setTimeout(() => setRecherche(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  useEffect(() => setPage(1), [recherche, role]);
  const liste = useChargement(() => api.get<{ total: number; elements: Compte[] }>(
    `/admin/comptes${requete({ q: recherche, role, page, taille: TAILLE })}`), [recherche, role, page]);

  return (
    <Gabarit fil={["Administration", "Comptes du personnel"]}>
      <div className="phd">
        <div><h1>Comptes du personnel</h1><p className="sub">Enseignants et administrateurs</p></div>
        <button className="btn p" onClick={() => setPanneau("creer")}><Icone nom="plus" />Créer un compte</button>
      </div>
      {message && <div style={{ marginBottom: 12 }}><Message type="ok">{message}</Message></div>}
      {liste.erreur && <div style={{ marginBottom: 12 }}><Message type="er">{liste.erreur}</Message></div>}
      <div className="box" style={{ maxWidth: 820 }}>
        <div className="tb">
          <input className="in" style={{ width: 280 }} placeholder="Nom ou identifiant" maxLength={60} value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="in" style={{ width: 170 }} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">Rôle : tous</option><option value="ENSEIGNANT">Enseignant</option><option value="ADMINISTRATEUR">Administrateur</option>
          </select>
        </div>
        <table>
          <thead><tr><th>Nom</th><th>Identifiant</th><th>Rôle</th><th>Dernière connexion</th><th>Statut</th></tr></thead>
          <tbody>
            {(liste.donnees?.elements ?? []).map((c) => {
              const [libelle, ton] = STATUTS_COMPTE[c.statut] ?? [c.statut, "mu"];
              return (
                <tr key={c.id} className="cliquable" onClick={() => setPanneau(c)}>
                  <td>{c.prenom} {c.nom}</td><td>{c.identifiant}</td><td>{ROLES[c.role]?.[0]}</td>
                  <td>{c.derniere_connexion ? dateHeure(c.derniere_connexion) : <span className="muet">—</span>}</td>
                  <td><Statut ton={ton}>{libelle}</Statut></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <Pagination page={page} total={liste.donnees?.total ?? 0} taille={TAILLE} onPage={setPage} />
      </div>
      {panneau === "creer" && <Creation onFermer={() => setPanneau(null)}
        onCree={(email) => { setPanneau(null); setMessage(`Compte créé ; lien d'activation envoyé à ${email}.`); liste.recharger(); }} />}
      {panneau && panneau !== "creer" && <Gestion c={panneau} soiMeme={panneau.id === utilisateur?.id} onFermer={() => setPanneau(null)}
        onFait={(m) => { setPanneau(null); setMessage(m); liste.recharger(); }} />}
    </Gabarit>
  );
}

function ChoixRole({ valeur, onChange }: { valeur: string; onChange: (r: string) => void }) {
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 4 }}>
      {Object.entries(ROLES).map(([cle, [libelle, description]], i) => (
        <label key={cle} style={{ display: "flex", gap: 10, padding: "9px 10px", alignItems: "flex-start", cursor: "pointer", borderTop: i ? "1px solid var(--line2)" : 0 }}>
          <input type="radio" name="role" checked={valeur === cle} onChange={() => onChange(cle)} style={{ marginTop: 3, accentColor: "var(--pr)" }} />
          <span><b>{libelle}</b><br /><span style={{ fontSize: 12.5, color: "var(--mu)" }}>{description}</span></span>
        </label>
      ))}
    </div>
  );
}

function Creation({ onFermer, onCree }: { onFermer: () => void; onCree: (email: string) => void }) {
  const [nom, setNom] = useState("");
  const [prenom, setPrenom] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("ENSEIGNANT");
  const [erreur, setErreur] = useState<string | null>(null);
  const valide = nomValide(nom) && nomValide(prenom) && emailValide(email);
  async function creer() {
    setErreur(null);
    try {
      await api.post("/admin/comptes", { nom: nom.trim(), prenom: prenom.trim(), email: email.trim(), role });
      onCree(email.trim());
    } catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <div className="panneau">
      <div className="bx-h"><h3>Créer un compte</h3><button className="fermer" onClick={onFermer} aria-label="Fermer"><Icone nom="x" taille={18} /></button></div>
      <div className="bx-b">
        {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
        <div className="g2">
          <Champ libelle="Nom" requis><input className="in" maxLength={60} value={nom} onChange={(e) => setNom(e.target.value)} autoFocus /></Champ>
          <Champ libelle="Prénom" requis><input className="in" maxLength={60} value={prenom} onChange={(e) => setPrenom(e.target.value)} /></Champ>
        </div>
        <Champ libelle="Adresse e-mail professionnelle" requis erreur={email && !emailValide(email) ? "Format d'adresse e-mail invalide." : null}>
          <input className="in" type="email" maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Champ>
        <div className="fg"><span className="lbl">Rôle <em>*</em></span><ChoixRole valeur={role} onChange={setRole} /></div>
        <div style={{ marginBottom: 14 }}><Message type="in">Le compte est créé en attente d'activation. La personne choisit son mot de passe et configure son second facteur à la première connexion.</Message></div>
        <div className="actions"><button className="btn s" onClick={onFermer}>Annuler</button><button className="btn p" disabled={!valide} onClick={() => void creer()}>Créer le compte</button></div>
      </div>
    </div>
  );
}

function Gestion({ c, soiMeme, onFermer, onFait }: { c: Compte; soiMeme: boolean; onFermer: () => void; onFait: (m: string) => void }) {
  const [role, setRole] = useState(c.role);
  const [erreur, setErreur] = useState<string | null>(null);
  const action = async (f: () => Promise<unknown>, message: string) => {
    setErreur(null);
    try { await f(); onFait(message); } catch (e) { setErreur(messageErreur(e)); }
  };
  return (
    <div className="panneau">
      <div className="bx-h"><h3>{c.prenom} {c.nom}</h3><button className="fermer" onClick={onFermer} aria-label="Fermer"><Icone nom="x" taille={18} /></button></div>
      <div className="bx-b">
        {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
        <div className="g2" style={{ marginBottom: 14 }}>
          <div className="kv"><span>Identifiant</span><b>{c.identifiant}</b></div>
          <div className="kv"><span>Adresse e-mail</span><b style={{ wordBreak: "break-all" }}>{c.email}</b></div>
        </div>
        {soiMeme ? <Message type="in">Vous ne pouvez pas modifier votre propre compte.</Message> : (
          <>
            <div className="fg"><span className="lbl">Rôle</span><ChoixRole valeur={role} onChange={setRole} /></div>
            <button className="btn p" disabled={role === c.role} style={{ marginBottom: 16 }}
              onClick={() => void action(() => api.patch(`/admin/comptes/${c.id}`, { role }), "Rôle modifié.")}>Enregistrer le rôle</button>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--line2)", paddingTop: 14 }}>
              {c.statut === "EN_ATTENTE_ACTIVATION" && (
                <button className="btn s" onClick={() => void action(() => api.post(`/admin/comptes/${c.id}/activation/renvoyer`), "Nouveau lien d'activation envoyé.")}>Renvoyer le lien d'activation</button>
              )}
              {c.statut === "ACTIF" && (
                <button className="btn s" onClick={() => void action(() => api.post(`/admin/comptes/${c.id}/mfa/reinitialiser`), "Second facteur réinitialisé ; un nouveau lien a été envoyé.")}>Réinitialiser le second facteur</button>
              )}
              {c.statut === "DESACTIVE"
                ? <button className="btn s" onClick={() => void action(() => api.patch(`/admin/comptes/${c.id}`, { statut: "ACTIF" }), "Compte réactivé.")}>Réactiver le compte</button>
                : <button className="btn d" onClick={() => void action(() => api.patch(`/admin/comptes/${c.id}`, { statut: "DESACTIVE" }), "Compte désactivé ; ses sessions sont fermées.")}>Désactiver le compte</button>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
