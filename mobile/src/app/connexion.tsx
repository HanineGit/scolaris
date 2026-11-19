import { Redirect } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ErreurApi } from "../lib/api";
import { etatEpinglage } from "../lib/pinning";
import { useSession } from "../lib/session";
import { Bouton, Champ, Icone, Message, T, useStyles } from "../ui/composants";
import { police } from "../ui/theme";

/** M1 : connexion de l'étudiant (F01). */
export default function Connexion() {
  const { c, s } = useStyles();
  const { utilisateur, connecter, messageFin } = useSession();
  const marges = useSafeAreaInsets();
  const [matricule, setMatricule] = useState("");
  const [mdp, setMdp] = useState("");
  const [voir, setVoir] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  if (utilisateur) return <Redirect href="/accueil" />;

  async function valider() {
    setErreur(null);
    setEnCours(true);
    try {
      await connecter(matricule.trim().toUpperCase(), mdp);
      setMdp("");
    } catch (e) {
      setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue.");
    } finally {
      setEnCours(false);
    }
  }

  return (
    <KeyboardAvoidingView style={s.ecran} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 22, paddingTop: marges.top + 46, flexGrow: 1 }} keyboardShouldPersistTaps="handled">
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 34 }}>
          <View style={{ width: 36, height: 36, borderRadius: 4, backgroundColor: c.hd, alignItems: "center", justifyContent: "center" }}>
            <T style={{ color: "#E6D4BC", fontFamily: police.gras, fontSize: 18 }}>S</T>
          </View>
          <View><T style={{ fontFamily: police.gras, fontSize: 19 }}>Scolaris</T><T style={{ color: c.mu, fontSize: 13.5 }}>Espace étudiant</T></View>
        </View>
        <T style={{ fontSize: 24, fontFamily: police.moyen, marginBottom: 18 }}>Connexion</T>
        {messageFin && <View style={{ marginBottom: 14 }}><Message type="in">{messageFin}</Message></View>}
        {erreur && <View style={{ marginBottom: 14 }}><Message type="er">{erreur}</Message></View>}
        {etatEpinglage() === "inactif-dev" && (
          <View style={{ marginBottom: 14 }}><Message type="in">Mode développement : l'épinglage du certificat n'est actif que dans les versions compilées.</Message></View>
        )}
        <Champ libelle="Matricule" value={matricule} onChangeText={setMatricule} autoCapitalize="characters" autoCorrect={false}
          placeholder="ETU-2026-0142" maxLength={13} textContentType="username" autoComplete="username" />
        <Champ libelle="Mot de passe" value={mdp} onChangeText={setMdp} secureTextEntry={!voir} autoCapitalize="none" autoCorrect={false}
          maxLength={128} textContentType="password" autoComplete="password" onSubmitEditing={() => void valider()}
          droite={<Pressable onPress={() => setVoir(!voir)} hitSlop={10} accessibilityLabel={voir ? "Masquer le mot de passe" : "Afficher le mot de passe"}>
            <Icone nom="eye" couleur={c.mu} /></Pressable>} />
        <Bouton titre="Se connecter" onPress={() => void valider()} desactive={!matricule || !mdp} chargement={enCours} />
        <T style={{ color: c.mu, fontSize: 13, marginTop: 12, lineHeight: 19 }}>Après 5 tentatives infructueuses, l'accès est suspendu pendant 15 minutes.</T>
        <View style={{ marginTop: 26, paddingTop: 14, borderTopWidth: 1, borderColor: c.line }}>
          <T style={{ color: c.mu, fontSize: 13.5, lineHeight: 20 }}>Première connexion : ouvrez le lien d'activation reçu par e-mail pour créer votre mot de passe.</T>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
