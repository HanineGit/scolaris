import { router } from "expo-router";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";

import { dateHeure, marquerLue, toutMarquerLu, type Notification } from "../../lib/donnees";
import { useNotifications } from "../../lib/notifications";
import { BarreHaut, Icone, Message, T, useStyles } from "../../ui/composants";
import { allerA } from "../../ui/navigation";
import { police } from "../../ui/theme";

const ICONES: Record<string, string> = { NOTES: "book", RECLAMATION: "message", SECURITE: "shield", COMPTE: "user" };

/** M8 : centre de notifications (F28). */
export default function Notifications() {
  const { c, s } = useStyles();
  const { elements, nonLues, recharger } = useNotifications();

  async function ouvrir(n: Notification) {
    if (!n.lue) await marquerLue(n.id).catch(() => undefined);
    recharger();
    // Seuls des chemins internes connus sont suivis (le service refuse déjà tout lien externe).
    if (n.lien === "/notes") allerA("notes");
    else if (n.lien === "/reclamations") allerA("reclamations");
    else if (n.lien === "/securite") allerA("compte");
  }

  return (
    <View style={s.ecran}>
      <BarreHaut titre="Notifications" sousTitre={nonLues ? `${nonLues} non lue(s)` : "Tout est lu"}
        retour={() => (router.canGoBack() ? router.back() : allerA("accueil"))}
        actionDroite={nonLues ? { icone: "check", libelle: "Tout marquer comme lu", onPress: () => void toutMarquerLu().then(recharger) } : undefined} />
      <ScrollView refreshControl={<RefreshControl refreshing={false} onRefresh={recharger} />} contentContainerStyle={{ paddingTop: 16, paddingBottom: 20 }}>
        <View style={s.liste}>
          {elements.map((n) => (
            <Pressable key={n.id} onPress={() => void ouvrir(n)} accessibilityRole="button"
              style={({ pressed }) => [s.ligne, { alignItems: "flex-start", gap: 12 }, !n.lue && { backgroundColor: c.prDoux }, pressed && { opacity: 0.85 }]}>
              <View style={{ width: 36, height: 36, borderRadius: 11, backgroundColor: n.categorie === "SECURITE" ? c.erBg : c.surface2,
                             alignItems: "center", justifyContent: "center" }}>
                <Icone nom={ICONES[n.categorie] ?? "info"} couleur={n.categorie === "SECURITE" ? c.er : c.pr} />
              </View>
              <View style={{ flex: 1 }}>
                <T style={{ fontFamily: n.lue ? police.demi : police.gras }}>{n.titre}</T>
                <T style={{ color: c.mu, fontSize: 13.5, marginTop: 2, lineHeight: 19 }}>{n.message}</T>
                <T style={{ color: c.fa, fontSize: 12, marginTop: 4 }}>{dateHeure(n.creee_le)}</T>
              </View>
            </Pressable>
          ))}
        </View>
        {elements.length === 0 && <View style={{ padding: 16 }}><Message type="in">Aucune notification pour l'instant.</Message></View>}
      </ScrollView>
    </View>
  );
}
