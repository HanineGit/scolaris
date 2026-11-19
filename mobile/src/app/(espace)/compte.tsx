import { File, Paths } from "expo-file-system";
import { router } from "expo-router";
import * as Sharing from "expo-sharing";
import { useCallback, useEffect, useState } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, RefreshControl, ScrollView, View } from "react-native";

import { ErreurApi } from "../../lib/api";
import { changerMotDePasse, dateHeure, fermerSession, reglesMotDePasse, releve, securite, type Securite } from "../../lib/donnees";
import { useNotifications } from "../../lib/notifications";
import { useSession } from "../../lib/session";
import { BarreHaut, Bouton, Carte, Champ, Icone, Message, Onglets, T, useStyles } from "../../ui/composants";
import { allerA } from "../../ui/navigation";
import { police, rayon } from "../../ui/theme";

const texteErreur = (e: unknown) => (e instanceof ErreurApi ? e.message : "Une erreur est survenue.");

/** M9 : compte de l'étudiant — relevé vérifiable (F20), sécurité (F27), déconnexion. */
export default function Compte() {
  const { utilisateur, quitter } = useSession();
  const { nonLues } = useNotifications();
  const { c, s } = useStyles();
  const [d, setD] = useState<Securite | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [telechargement, setTelechargement] = useState(false);
  const [motDePasse, setMotDePasse] = useState(false);
  const charger = useCallback(() => { securite().then(setD).catch((e) => setErreur(texteErreur(e))); }, []);
  useEffect(charger, [charger]);

  async function partagerReleve() {
    setErreur(null); setMessage(null); setTelechargement(true);
    // Le relevé n'est écrit que dans le cache, le temps du partage, puis effacé :
    // aucune note ne reste stockée sur le téléphone (R22).
    const f = new File(Paths.cache, `releve-${utilisateur?.identifiant ?? "scolaris"}.pdf`);
    try {
      const { octets, code } = await releve();
      if (f.exists) f.delete();
      f.create();
      await f.write(octets);
      await Sharing.shareAsync(f.uri, { mimeType: "application/pdf", UTI: "com.adobe.pdf", dialogTitle: "Relevé de notes" });
      if (code) setMessage(`Relevé émis. Code de vérification : ${code}`);
    } catch (e) {
      setErreur(texteErreur(e));
    } finally {
      if (f.exists) f.delete();
      setTelechargement(false);
    }
  }

  return (
    <View style={s.ecran}>
      <BarreHaut titre="Mon compte" sousTitre={utilisateur?.identifiant} notifications={nonLues}
        versNotifications={() => router.push("/notifications")} />
      <ScrollView refreshControl={<RefreshControl refreshing={false} onRefresh={charger} />} contentContainerStyle={{ paddingTop: 16, paddingBottom: 24 }}>
        {erreur && <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}><Message type="er">{erreur}</Message></View>}
        {message && <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}><Message type="ok">{message}</Message></View>}

        <Carte style={{ padding: 18, flexDirection: "row", alignItems: "center", gap: 14 }}>
          <View style={{ width: 52, height: 52, borderRadius: 26, backgroundColor: c.pr, alignItems: "center", justifyContent: "center" }}>
            <T style={{ color: c.prTexte, fontFamily: police.gras, fontSize: 18 }}>
              {`${utilisateur?.prenom?.[0] ?? ""}${utilisateur?.nom?.[0] ?? ""}`.toUpperCase() || "E"}</T>
          </View>
          <View style={{ flex: 1 }}>
            <T style={{ fontFamily: police.gras, fontSize: 17 }}>{[utilisateur?.prenom, utilisateur?.nom].filter(Boolean).join(" ") || "Étudiant"}</T>
            <T style={{ color: c.mu, fontSize: 13.5 }}>{d?.email ?? utilisateur?.identifiant}</T>
          </View>
        </Carte>

        <Carte style={{ padding: 16 }}>
          <View style={{ flexDirection: "row", gap: 12, alignItems: "center", marginBottom: 12 }}>
            <Icone nom="file" couleur={c.pr} />
            <View style={{ flex: 1 }}>
              <T style={{ fontFamily: police.gras }}>Relevé de notes</T>
              <T style={{ color: c.mu, fontSize: 13 }}>PDF officiel avec QR code de vérification</T>
            </View>
          </View>
          <Bouton titre="Télécharger le relevé" icone="file" chargement={telechargement} onPress={() => void partagerReleve()} />
        </Carte>

        <T style={s.section}>SÉCURITÉ</T>
        <Carte style={{ padding: 16 }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 12 }}>
            <View><T style={{ color: c.mu, fontSize: 13 }}>Dernière connexion</T><T style={{ fontFamily: police.demi }}>{dateHeure(d?.derniere_connexion)}</T></View>
          </View>
          <Bouton titre="Changer le mot de passe" icone="key" variante="s" onPress={() => setMotDePasse(true)} />
        </Carte>

        <T style={s.section}>APPAREILS CONNECTÉS</T>
        <View style={s.liste}>
          {(d?.sessions ?? []).map((x) => (
            <View key={x.id} style={[s.ligne, { gap: 12 }]}>
              <Icone nom="device" couleur={c.mu} />
              <View style={{ flex: 1 }}>
                <T style={{ fontFamily: police.demi }}>{x.appareil}{x.courante ? " · cet appareil" : ""}</T>
                <T style={s.ligneSous}>Activité : {dateHeure(x.derniere_activite)}</T>
              </View>
              {!x.courante && (
                <Pressable hitSlop={8} accessibilityRole="button" accessibilityLabel={`Fermer la session ${x.appareil}`}
                  onPress={() => void fermerSession(x.id).then(() => { setMessage(`Session « ${x.appareil} » fermée.`); charger(); }).catch((e) => setErreur(texteErreur(e)))}>
                  <T style={{ color: c.er, fontFamily: police.demi }}>Fermer</T>
                </Pressable>
              )}
            </View>
          ))}
        </View>

        <T style={s.section}>DERNIÈRES CONNEXIONS</T>
        <View style={s.liste}>
          {(d?.connexions ?? []).slice(0, 6).map((x, i) => (
            <View key={i} style={s.ligne}>
              <View style={{ flex: 1 }}><T style={{ fontSize: 14.5 }}>{x.appareil}</T><T style={s.ligneSous}>{dateHeure(x.horodatage)}</T></View>
              <T style={{ color: x.resultat === "SUCCES" ? c.ok : c.er, fontFamily: police.demi, fontSize: 13 }}>
                {x.resultat === "SUCCES" ? "Réussie" : x.resultat === "ECHEC" ? "Échouée" : "Verrouillage"}</T>
            </View>
          ))}
        </View>

        <View style={{ padding: 16, gap: 12 }}>
          <Bouton titre="Se déconnecter" icone="out" variante="d" onPress={() => void quitter()} />
          <T style={{ fontSize: 12, color: c.fa, textAlign: "center" }}>Le thème clair ou sombre suit le réglage de votre téléphone.</T>
        </View>
      </ScrollView>
      <Onglets actif="compte" aller={allerA} />
      {motDePasse && <ChangerMotDePasse onFermer={() => setMotDePasse(false)}
        onFait={() => { setMotDePasse(false); setMessage("Mot de passe modifié. Vos autres appareils ont été déconnectés."); charger(); }} />}
    </View>
  );
}

function ChangerMotDePasse({ onFermer, onFait }: { onFermer: () => void; onFait: () => void }) {
  const { c } = useStyles();
  const [actuel, setActuel] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const regles = reglesMotDePasse(nouveau);
  const valide = !!actuel && regles.every((r) => r.ok) && nouveau === confirmation && nouveau !== actuel;
  async function valider() {
    setErreur(null); setEnCours(true);
    try { await changerMotDePasse(actuel, nouveau, confirmation); onFait(); }
    catch (e) { setErreur(texteErreur(e)); } finally { setEnCours(false); }
  }
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onFermer}>
      <Pressable style={{ flex: 1, backgroundColor: "rgba(23,17,13,0.5)" }} onPress={onFermer} accessibilityLabel="Annuler" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={{ backgroundColor: c.surface, borderTopLeftRadius: rayon.l, borderTopRightRadius: rayon.l, padding: 18, paddingBottom: 30 }}>
          <T style={{ fontSize: 18, fontFamily: police.gras, marginBottom: 14 }}>Changer le mot de passe</T>
          {erreur && <View style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></View>}
          <Champ libelle="Mot de passe actuel" value={actuel} onChangeText={setActuel} secureTextEntry autoComplete="current-password" />
          <Champ libelle="Nouveau mot de passe" value={nouveau} onChangeText={setNouveau} secureTextEntry autoComplete="new-password" />
          <View style={{ marginBottom: 12, gap: 4 }}>
            {regles.map((r) => (
              <View key={r.libelle} style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                <Icone nom={r.ok ? "check" : "x"} taille={14} couleur={r.ok ? c.ok : c.fa} />
                <T style={{ fontSize: 13, color: r.ok ? c.ok : c.mu }}>{r.libelle}</T>
              </View>
            ))}
          </View>
          <Champ libelle="Confirmation" value={confirmation} onChangeText={setConfirmation} secureTextEntry autoComplete="new-password"
            erreur={confirmation && confirmation !== nouveau ? "Les deux mots de passe diffèrent." : null} />
          <Bouton titre="Enregistrer" desactive={!valide} chargement={enCours} onPress={() => void valider()} />
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
