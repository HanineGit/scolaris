import { useState } from "react";

import { api } from "../api";
import { dateHeure, reglesMotDePasse } from "../format";
import { Icone } from "../icons";
import { Champ, Gabarit, Message, Modale, Statut, messageErreur, useChargement } from "../ui";

interface SessionVue { id: string; appareil: string; adresse_ip: string | null; ouverte_le: string; derniere_activite: string; courante: boolean }
interface Securite {
  identifiant: string; email: string; role: string; double_facteur: boolean; derniere_connexion: string | null;
  sessions: SessionVue[]; connexions: { horodatage: string; resultat: string; appareil: string; adresse_ip: string | null }[];
}
const RESULTATS: Record<string, [string, string]> = { SUCCES: ["Réussie", "ok"], ECHEC: ["Échouée", "er"], VERROUILLAGE: ["Compte verrouillé", "er"] };

/** W18 : espace sécurité du compte (F27). */
export default function SecuritePage() {
  const s = useChargement(() => api.get<Securite>("/moi/securite"), []);
  const [motDePasse, setMotDePasse] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const d = s.donnees;
  const autres = (d?.sessions ?? []).filter((x) => !x.courante).length;

  const action = async (f: () => Promise<unknown>, succes: string) => {
    setErreur(null); setMessage(null);
    try { await f(); setMessage(succes); s.recharger(); } catch (e) { setErreur(messageErreur(e)); }
  };

  return (
    <Gabarit fil={["Compte", "Sécurité du compte"]}>
      <div className="phd"><div><h1>Sécurité du compte</h1><p className="sub">Appareils connectés, historique des connexions et mot de passe</p></div>
        <button className="btn p" onClick={() => setMotDePasse(true)}><Icone nom="key" />Changer le mot de passe</button></div>
      {(s.erreur || erreur) && <div style={{ marginBottom: 12 }}><Message type="er">{s.erreur ?? erreur}</Message></div>}
      {message && <div style={{ marginBottom: 12 }}><Message type="ok">{message}</Message></div>}
      {d && (
        <>
          <div className="box bx-b" style={{ marginBottom: 16 }}>
            <div className="g4">
              <div className="kv"><span>Identifiant</span><b>{d.identifiant}</b></div>
              <div className="kv"><span>Adresse e-mail</span><b>{d.email}</b></div>
              <div className="kv"><span>Double authentification</span><b>{d.double_facteur ? <Statut ton="ok">Activée</Statut> : <Statut ton="mu">Non concernée</Statut>}</b></div>
              <div className="kv"><span>Dernière connexion</span><b>{dateHeure(d.derniere_connexion)}</b></div>
            </div>
          </div>
          <div className="box">
            <div className="bx-h"><h3>Sessions ouvertes</h3>
              {autres > 0 && <button className="btn s sm" onClick={() => void action(() => api.post("/moi/sessions/fermeture-des-autres"), "Les autres sessions ont été fermées.")}>
                <Icone nom="out" />Fermer les {autres} autre(s) session(s)</button>}</div>
            <table>
              <thead><tr><th>Appareil</th><th>Adresse IP</th><th>Ouverte le</th><th>Dernière activité</th><th /></tr></thead>
              <tbody>
                {d.sessions.map((x) => (
                  <tr key={x.id}>
                    <td><span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}><Icone nom="device" />{x.appareil}</span>
                      {x.courante && <span className="pastille" style={{ marginLeft: 8 }}>Cet appareil</span>}</td>
                    <td className="mono">{x.adresse_ip ?? "–"}</td><td>{dateHeure(x.ouverte_le)}</td><td>{dateHeure(x.derniere_activite)}</td>
                    <td className="r">{!x.courante && <button className="lien" onClick={() => void action(() => api.delete(`/moi/sessions/${x.id}`), `Session « ${x.appareil} » fermée.`)}>Fermer</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="box">
            <div className="bx-h"><h3>Dernières connexions</h3><span className="muet" style={{ fontSize: 12.5 }}>Une connexion inconnue ? Changez votre mot de passe.</span></div>
            <table>
              <thead><tr><th>Date</th><th>Résultat</th><th>Appareil</th><th>Adresse IP</th></tr></thead>
              <tbody>
                {d.connexions.map((c, i) => {
                  const [libelle, ton] = RESULTATS[c.resultat] ?? [c.resultat, "mu"];
                  return <tr key={i}><td>{dateHeure(c.horodatage)}</td><td><Statut ton={ton}>{libelle}</Statut></td><td>{c.appareil}</td><td className="mono">{c.adresse_ip ?? "–"}</td></tr>;
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      {motDePasse && <ChangerMotDePasse onFermer={() => setMotDePasse(false)}
        onFait={() => { setMotDePasse(false); setMessage("Mot de passe modifié. Vos autres sessions ont été fermées."); s.recharger(); }} />}
    </Gabarit>
  );
}

function ChangerMotDePasse({ onFermer, onFait }: { onFermer: () => void; onFait: () => void }) {
  const [actuel, setActuel] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const regles = reglesMotDePasse(nouveau);
  const valide = actuel && regles.every((r) => r.ok) && nouveau === confirmation && nouveau !== actuel;
  async function valider() {
    setErreur(null);
    try { await api.put("/moi/mot-de-passe", { actuel, nouveau, confirmation }); onFait(); } catch (e) { setErreur(messageErreur(e)); }
  }
  return (
    <Modale titre="Changer le mot de passe" onFermer={onFermer} largeur={480} pied={<>
      <button className="btn s" onClick={onFermer}>Annuler</button>
      <button className="btn p" disabled={!valide} onClick={() => void valider()}>Enregistrer</button></>}>
      {erreur && <div style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></div>}
      <Champ libelle="Mot de passe actuel" requis><input className="in" type="password" autoComplete="current-password" value={actuel} onChange={(e) => setActuel(e.target.value)} autoFocus /></Champ>
      <Champ libelle="Nouveau mot de passe" requis><input className="in" type="password" autoComplete="new-password" value={nouveau} onChange={(e) => setNouveau(e.target.value)} /></Champ>
      <div className="regles">{regles.map((r) => <div key={r.libelle} className={r.ok ? "ok" : ""}><Icone nom={r.ok ? "check" : "x"} taille={14} />{r.libelle}</div>)}</div>
      <Champ libelle="Confirmation" requis erreur={confirmation && confirmation !== nouveau ? "Les deux mots de passe diffèrent." : null}>
        <input className="in" type="password" autoComplete="new-password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></Champ>
    </Modale>
  );
}
