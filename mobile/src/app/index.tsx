import { Redirect } from "expo-router";
import { View } from "react-native";

import { useSession } from "../lib/session";
import { useCouleurs } from "../ui/theme";

export default function Entree() {
  const { utilisateur, pret } = useSession();
  const c = useCouleurs();
  if (!pret) return <View style={{ flex: 1, backgroundColor: c.bg }} />;
  return <Redirect href={utilisateur ? "/accueil" : "/connexion"} />;
}
