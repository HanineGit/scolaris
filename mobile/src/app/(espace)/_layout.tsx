import { Redirect, Stack } from "expo-router";
import { usePreventScreenCapture } from "expo-screen-capture";
import { View } from "react-native";

import { FournisseurNotifications } from "../../lib/notifications";
import { useSession } from "../../lib/session";
import { useCouleurs } from "../../ui/theme";

/**
 * Espace connecté de l'étudiant.
 * - Accès réservé à une session ouverte (sinon retour à la connexion).
 * - Captures d'écran et enregistrements bloqués sur tous les écrans de notes (R22).
 * - Chaque interaction repousse la fermeture automatique après 15 minutes d'inactivité.
 * - Les notifications ne sont interrogées que pendant une session ouverte.
 */
export default function Espace() {
  const { utilisateur, pret, signalerActivite } = useSession();
  const c = useCouleurs();
  usePreventScreenCapture("notes");
  if (!pret) return <View style={{ flex: 1, backgroundColor: c.bg }} />;
  if (!utilisateur) return <Redirect href="/connexion" />;
  return (
    <FournisseurNotifications>
      <View style={{ flex: 1 }} onTouchStart={signalerActivite}>
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.bg }, animation: "fade" }} />
      </View>
    </FournisseurNotifications>
  );
}
