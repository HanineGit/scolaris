import QRCode from "qrcode";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { date, reglesMotDePasse } from "../format";
import { Icone } from "../icons";
import { BoutonTheme, Champ, EnTete, Message, messageErreur } from "../ui";

interface Preparation { identifiant: string; role: string; expire_le: string; mfa_requis: boolean; mfa_uri?: string }

/** F02 : activation d'un compte à partir du lien reçu par e-mail. */
export default function Activation() {
  const [jeton] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("jeton") ?? "");
  const [prep, setPrep] = useState<Preparation | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [mdp, setMdp] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [termine, setTermine] = useState(false);
  const [enCours, setEnCours] = useState(false);

  useEffect(() => {
    // Un nouveau lien ouvert dans le même onglet ne change que le fragment : on recharge.
    const nouveauLien = () => window.location.reload();
    window.addEventListener("hashchange", nouveauLien);
    return () => window.removeEventListener("hashchange", nouveauLien);
  }, []);

  useEffect(() => {
    // Le jeton est retiré de la barre d'adresse et de l'historique dès sa lecture.
    window.history.replaceState(null, "", window.location.pathname);
    if (!jeton) {
      setErreur("Ce lien d'activation est incomplet.");
      return;
    }
    api.post<Preparation>("/auth/activation/verifier", { jeton })
      .then(async (p) => {
        setPrep(p);
        if (p.mfa_uri) setQr(await QRCode.toDataURL(p.mfa_uri, { margin: 1, width: 296, color: { dark: "#2f231b", light: "#ffffff" } }));
      })
      .catch((e) => setErreur(messageErreur(e)));
  }, [jeton]);

  const regles = reglesMotDePasse(mdp);
  const valide = regles.every((r) => r.ok) && mdp === confirmation && (!prep?.mfa_requis || code.length === 6);
  const secret = prep?.mfa_uri ? new URL(prep.mfa_uri).searchParams.get("secret") : null;

  async function activer(e: FormEvent) {
    e.preventDefault();
    setEnCours(true);
    setErreur(null);
    try {
      await api.post("/auth/activation", { jeton, mot_de_passe: mdp, confirmation, code_totp: prep?.mfa_requis ? code : undefined });
      setTermine(true);
      setMdp("");
      setConfirmation("");
    } catch (ex) {
      setErreur(messageErreur(ex));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <>
      <EnTete droite={<><span className="tm">Activation du compte</span><BoutonTheme /></>} />
      <div className="public" style={{ paddingTop: 50 }}>
        <div className="carte large">
          <div className="top">
            <h1 style={{ fontSize: 20 }}>Activation du compte</h1>
            {prep && <p className="sub">Identifiant : <b>{prep.identifiant}</b> · lien valable jusqu'au {date(prep.expire_le)}</p>}
          </div>
          <div className="bd">
            {termine ? (
              <>
                <Message type="ok">Votre compte est activé.</Message>
                <p style={{ margin: "14px 0", fontSize: 13.5 }}>
                  {prep?.role === "ETUDIANT"
                    ? "Vous pouvez maintenant vous connecter dans l'application mobile Scolaris avec votre matricule."
                    : "Vous pouvez maintenant vous connecter au back-office avec votre mot de passe et votre application d'authentification."}
                </p>
                {prep?.role !== "ETUDIANT" && <Link className="btn p plein" to="/connexion">Aller à la connexion</Link>}
              </>
            ) : !prep ? (
              erreur ? <Message type="er">{erreur}</Message> : <p className="chargement">Vérification du lien…</p>
            ) : (
              <form onSubmit={activer}>
                {erreur && <div style={{ marginBottom: 14 }}><Message type="er">{erreur}</Message></div>}
                <Champ libelle="Nouveau mot de passe" requis>
                  <input className="in" type="password" autoComplete="new-password" maxLength={128} value={mdp} onChange={(e) => setMdp(e.target.value)} autoFocus />
                </Champ>
                <div className="regles">
                  {regles.map((r) => <div key={r.libelle} className={r.ok ? "ok" : ""}><Icone nom={r.ok ? "check" : "x"} taille={15} />{r.libelle}</div>)}
                  <div><Icone nom="info" taille={15} />Absent des listes de mots de passe divulgués (vérifié par le serveur)</div>
                </div>
                <Champ libelle="Confirmer le mot de passe" requis erreur={confirmation && confirmation !== mdp ? "Les deux mots de passe ne correspondent pas." : null}>
                  <input className="in" type="password" autoComplete="new-password" maxLength={128} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
                </Champ>
                {prep.mfa_requis && (
                  <>
                    <label className="lbl">Second facteur</label>
                    <div className="qr">
                      {qr && <img src={qr} alt="Code QR à scanner avec l'application d'authentification" />}
                      <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                        Scannez ce code avec votre application d'authentification (Google Authenticator, Microsoft Authenticator, FreeOTP…).
                        {secret && <><br />Ou saisissez la clé :<div className="cle">{secret.match(/.{1,4}/g)?.join(" ")}</div></>}
                      </div>
                    </div>
                    <Champ libelle="Code affiché par l'application" requis>
                      <input className="in otp" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
                    </Champ>
                  </>
                )}
                <button className="btn p plein" disabled={!valide || enCours}>Activer mon compte</button>
                <p className="help" style={{ marginTop: 10 }}>Ce lien ne peut être utilisé qu'une seule fois.</p>
              </form>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
