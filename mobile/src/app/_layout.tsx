import {
  PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold, useFonts,
} from "@expo-google-fonts/plus-jakarta-sans";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import { View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { initialiserEpinglage } from "../lib/pinning";
import { FournisseurSession } from "../lib/session";
import { useCouleurs } from "../ui/theme";

export default function Racine() {
  const [policesPretes] = useFonts({ PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold,
                                     PlusJakartaSans_700Bold, PlusJakartaSans_800ExtraBold });
  const [epinglagePret, setEpinglagePret] = useState(false);
  const c = useCouleurs();

  // L'épinglage du certificat est actif avant tout appel réseau.
  useEffect(() => { void initialiserEpinglage().finally(() => setEpinglagePret(true)); }, []);

  if (!policesPretes || !epinglagePret) return <View style={{ flex: 1, backgroundColor: c.bg }} />;
  return (
    <SafeAreaProvider>
      <FournisseurSession>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.bg } }} />
      </FournisseurSession>
    </SafeAreaProvider>
  );
}
