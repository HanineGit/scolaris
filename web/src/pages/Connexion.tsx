import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";

import { ErreurApi, api, type Jetons } from "../api";
import { Icone } from "../icons";
import { useSession } from "../session";
import { BoutonTheme, Champ, EnTete, Message, messageErreur } from "../ui";

/** W1 puis W2 : connexion du personnel en deux étapes (mot de passe, puis code TOTP). */
export default function Connexion() {
  const { utilisateur, connecter, messageFin, effacerMessage } = useSession();
  const [identifiant, setIdentifiant] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [voir, setVoir] = useState(false);
  const [jetonMfa, setJetonMfa] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  if (utilisateur) return <Navigate to="/" replace />;

  async function etape1(e: FormEvent) {
    e.preventDefault();
    effacerMessage();
    setErreur(null);
    setEnCours(true);
    try {
      const r = await api.post<Jetons | { mfa_requis: true; jeton_mfa: string }>("/auth/connexion", { identifiant, mot_de_passe: motDePasse });
      setMotDePasse("");
      if ("mfa_requis" in r) {
        setJetonMfa(r.jeton_mfa);
      } else {
        // Un étudiant n'a pas accès au back-office : sa session est refermée aussitôt.
        await fetch("/api/v1/auth/deconnexion", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${r.jeton_acces}` },
          body: JSON.stringify({ jeton_rafraichissement: r.jeton_rafraichissement }),
          credentials: "omit",
        }).catch(() => undefined);
        setErreur("Cet espace est réservé au personnel. Les étudiants consultent leurs notes dans l'application mobile.");
      }
    } catch (ex) {
      setErreur(ex instanceof ErreurApi && ex.statut === 401 ? "Identifiant ou mot de passe incorrect." : messageErreur(ex));
    } finally {
      setEnCours(false);
    }
  }

  async function etape2(e: FormEvent) {
    e.preventDefault();
    setErreur(null);
    setEnCours(true);
    try {
      connecter(await api.post<Jetons>("/auth/mfa/verifier", { jeton_mfa: jetonMfa, code }));
    } catch (ex) {
      setCode("");
      if (ex instanceof ErreurApi && ex.code === "SESSION_INVALIDE") {
        setJetonMfa(null);
        setErreur("Le délai de saisie du code est dépassé. Recommencez la connexion.");
      } else {
        setErreur(ex instanceof ErreurApi && ex.statut === 401 ? "Code de vérification incorrect." : messageErreur(ex));
      }
    } finally {
      setEnCours(false);
    }
  }

  return (
    <>
      <EnTete droite={<><span className="tm">Espace du personnel</span><BoutonTheme /></>} />
      <div className="public">
        <div className="carte">
          {!jetonMfa ? (
            <form onSubmit={etape1}>
              <div className="top"><h1 style={{ fontSize: 20 }}>Connexion du personnel</h1><p className="sub">Enseignants et administration</p></div>
              <div className="bd">
                {messageFin && <div style={{ marginBottom: 14 }}><Message type="in">{messageFin}</Message></div>}
                {erreur && <div style={{ marginBottom: 14 }}><Message type="er">{erreur}</Message></div>}
                <Champ libelle="Identifiant">
                  <input className="in" autoComplete="username" value={identifiant} maxLength={254}
                    onChange={(e) => setIdentifiant(e.target.value)} placeholder="adresse e-mail ou identifiant" autoFocus />
                </Champ>
                <Champ libelle="Mot de passe">
                  <div style={{ position: "relative" }}>
                    <input className="in" type={voir ? "text" : "password"} autoComplete="current-password" value={motDePasse}
                      maxLength={128} onChange={(e) => setMotDePasse(e.target.value)} style={{ paddingRight: 70 }} />
                    <button type="button" className="lien" style={{ position: "absolute", right: 10, top: 9 }} onClick={() => setVoir(!voir)}>
                      {voir ? "Masquer" : "Afficher"}
                    </button>
                  </div>
                </Champ>
                <button className="btn p plein" disabled={enCours || !identifiant || !motDePasse}>Continuer</button>
                <p className="help" style={{ marginTop: 12 }}>Étape 1 sur 2. Un code de vérification sera demandé ensuite.</p>
              </div>
            </form>
          ) : (
            <form onSubmit={etape2}>
              <div className="top"><h1 style={{ fontSize: 20 }}>Code de vérification</h1><p className="sub">Étape 2 sur 2 · {identifiant}</p></div>
              <div className="bd">
                {erreur && <div style={{ marginBottom: 14 }}><Message type="er">{erreur}</Message></div>}
                <p style={{ fontSize: 13.5, lineHeight: 1.5, marginBottom: 14 }}>Saisissez le code à 6 chiffres affiché dans votre application d'authentification.</p>
                <Champ libelle="Code" aide="Le code est renouvelé toutes les 30 secondes.">
                  <input className="in otp" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} autoFocus />
                </Champ>
                <button className="btn p plein" disabled={enCours || code.length !== 6}>Se connecter</button>
                <button type="button" className="btn s plein" style={{ marginTop: 8 }} onClick={() => { setJetonMfa(null); setCode(""); setErreur(null); }}>Retour</button>
              </div>
            </form>
          )}
        </div>
        <div className="pied"><Icone nom="info" taille={15} /><span>
          {jetonMfa
            ? "En cas de perte de votre téléphone, contactez l'administrateur pour réinitialiser votre second facteur."
            : "Accès réservé au personnel habilité. Après 5 tentatives infructueuses, le compte est suspendu 15 minutes. Les connexions sont enregistrées."}
        </span></div>
      </div>
    </>
  );
}
