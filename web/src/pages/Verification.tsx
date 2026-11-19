import { useParams } from "react-router-dom";

import { api } from "../api";
import { dateHeure, note } from "../format";
import { Icone } from "../icons";
import { EnTete, BoutonTheme, Message, useChargement } from "../ui";

interface Resultat { valide: boolean; emis_le?: string; annee_academique?: string; matricule?: string; moyenne_generale?: string | null; empreinte?: string }

/** W19 : page publique de vérification d'un relevé de notes (cible du QR code, F20). */
export default function Verification() {
  const { code = "" } = useParams();
  const forme = /^[0-9a-f]{32}$/.test(code);
  const r = useChargement(() => forme ? api.get<Resultat>(`/verification/${code}`) : Promise.resolve<Resultat>({ valide: false }), [code]);
  const d = r.donnees;
  return (
    <>
      <EnTete droite={<><span className="tm">Vérification d'un relevé</span><BoutonTheme /></>} />
      <div className="public">
        <div className="carte large">
          <div className="top"><h1 style={{ fontSize: 21 }}>Authenticité d'un relevé de notes</h1>
            <p className="sub">Comparez ces informations avec celles imprimées sur le document.</p></div>
          <div className="bd">
            {r.erreur && <Message type="er">{r.erreur}</Message>}
            {d && !d.valide && <Message type="er">Aucun relevé ne correspond à ce code. Le document n'a pas été émis par Scolaris ou le code est erroné.</Message>}
            {d?.valide && (
              <>
                <div style={{ marginBottom: 14 }}><Message type="ok">Ce relevé a bien été émis par le service de scolarité.</Message></div>
                <div className="g2" style={{ marginBottom: 12 }}>
                  <div className="kv"><span>Matricule</span><b className="mono">{d.matricule}</b></div>
                  <div className="kv"><span>Année académique</span><b>{d.annee_academique}</b></div>
                  <div className="kv"><span>Émis le</span><b>{dateHeure(d.emis_le)}</b></div>
                  <div className="kv"><span>Moyenne générale</span><b>{d.moyenne_generale ? `${note(d.moyenne_generale)} / 20` : "–"}</b></div>
                </div>
                <div className="kv"><span>Empreinte du document</span></div>
                <div className="cle">{d.empreinte}</div>
              </>
            )}
          </div>
        </div>
        <div className="pied"><Icone nom="shield" taille={15} />Le nom de l'étudiant n'est pas affiché : seules les informations nécessaires à la vérification le sont.</div>
      </div>
    </>
  );
}
