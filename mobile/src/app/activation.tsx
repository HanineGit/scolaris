import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, View } from "react-native";

import { ErreurApi, activer, verifierActivation } from "../lib/api";
import { date, reglesMotDePasse } from "../lib/donnees";
import { BarreHaut, Bouton, Champ, Icone, Message, T, useStyles } from "../ui/composants";


/** M2 : activation du compte depuis le lien scolaris://activation?jeton=… (F02). */
export default function Activation() {
  const { c, s } = useStyles();
  const { jeton } = useLocalSearchParams<{ jeton?: string }>();
  const [prep, setPrep] = useState<{ identifiant: string; expire_le: string; role: string } | null>(null);
  const [mdp, setMdp] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [termine, setTermine] = useState(false);
  const [enCours, setEnCours] = useState(false);

  useEffect(() => {
    if (!jeton) { setErreur("Ce lien d'activation est incomplet."); return; }
    verifierActivation(jeton)
      .then((p) => p.role === "ETUDIANT" ? setPrep(p) : setErreur("Ce lien concerne un compte du personnel : ouvrez-le dans un navigateur."))
      .catch((e) => setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue."));
  }, [jeton]);

  const regles = reglesMotDePasse(mdp);
  const valide = regles.every((r) => r.ok) && mdp === confirmation;

  async function valider() {
    if (!jeton) return;
    setEnCours(true);
    setErreur(null);
    try {
      await activer(jeton, mdp, confirmation);
      setTermine(true);
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue.");
    } finally {
      setEnCours(false);
    }
  }

  return (
    <View style={s.ecran}>
      <BarreHaut titre="Activation du compte" sousTitre={prep ? `Lien valable jusqu'au ${date(prep.expire_le)}` : undefined}
        retour={() => router.replace("/connexion")} />
      <ScrollView contentContainerStyle={{ padding: 16 }} keyboardShouldPersistTaps="handled">
        {erreur && <View style={{ marginBottom: 14 }}><Message type="er">{erreur}</Message></View>}
        {termine ? (
          <>
            <Message type="ok">Votre compte est activé.</Message>
            <View style={{ marginTop: 16 }}><Bouton titre="Se connecter" onPress={() => router.replace("/connexion")} /></View>
          </>
        ) : prep && (
          <>
            <Champ libelle="Matricule" value={prep.identifiant} editable={false} />
            <Champ libelle="Nouveau mot de passe" value={mdp} onChangeText={setMdp} secureTextEntry autoCapitalize="none" maxLength={128} />
            <View style={{ backgroundColor: c.surface, borderWidth: 1, borderColor: c.line, borderRadius: 4, padding: 12, marginBottom: 14, gap: 6 }}>
              {regles.map((r) => (
                <View key={r.libelle} style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                  <Icone nom={r.ok ? "check" : "x"} taille={15} couleur={r.ok ? c.ok : c.fa} />
                  <T style={{ fontSize: 13.5, color: r.ok ? c.ok : c.fa }}>{r.libelle}</T>
                </View>
              ))}
              <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                <Icone nom="info" taille={15} couleur={c.fa} />
                <T style={{ fontSize: 13.5, color: c.fa, flex: 1 }}>Absent des mots de passe divulgués (vérifié par le serveur)</T>
              </View>
            </View>
            <Champ libelle="Confirmer le mot de passe" value={confirmation} onChangeText={setConfirmation} secureTextEntry autoCapitalize="none"
              maxLength={128} erreur={confirmation && confirmation !== mdp ? "Les deux mots de passe ne correspondent pas." : null} />
            <Bouton titre="Activer mon compte" onPress={() => void valider()} desactive={!valide} chargement={enCours} />
            <T style={{ color: c.mu, fontSize: 13, marginTop: 12 }}>Ce lien ne peut être utilisé qu'une seule fois.</T>
          </>
        )}
      </ScrollView>
    </View>
  );
}
