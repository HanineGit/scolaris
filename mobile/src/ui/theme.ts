import { useColorScheme } from "react-native";

/** Charte Scolaris : tons bruns, style sobre. Le thème suit le réglage clair/sombre du téléphone. */
const clair = {
  hd: "#2A1F18", hdTexte: "#EFE6DA", hdSous: "#C9B9A6", pr: "#6B4A33", prTexte: "#FFFFFF", prDoux: "#F1E7DC", tan: "#C39A69",
  bg: "#F6F2EC", surface: "#FFFFFF", surface2: "#FAF7F3", sand: "#EFE6DA",
  line: "#E4DACD", line2: "#EFE8DF", tx: "#2A221C", tx2: "#4E4339", mu: "#7A6C5F", fa: "#A89A8A",
  ok: "#4F6A2A", okBg: "#EEF2E3", er: "#A23A2A", erBg: "#F9E9E4", wa: "#9A6418", waBg: "#FAF0DD", in: "#3D5A73", inBg: "#E8EFF5",
  ombre: "#2A1F18",
};
const sombre: typeof clair = {
  hd: "#17110D", hdTexte: "#EFE6DA", hdSous: "#A89683", pr: "#D2A878", prTexte: "#1E1611", prDoux: "#3A2C22", tan: "#C39A69",
  bg: "#1B1511", surface: "#241C17", surface2: "#2B221C", sand: "#33281F",
  line: "#3D3128", line2: "#332920", tx: "#F1E9DF", tx2: "#D9CBBB", mu: "#B3A290", fa: "#8A7B6C",
  ok: "#A9C27A", okBg: "#26301A", er: "#F0937F", erBg: "#3A1F19", wa: "#E8B866", waBg: "#382A14", in: "#9DBCD6", inBg: "#1C2833",
  ombre: "#000000",
};
export type Couleurs = typeof clair;

export function useCouleurs(): Couleurs {
  return useColorScheme() === "dark" ? sombre : clair;
}

export const police = {
  normal: "PlusJakartaSans_400Regular",
  moyen: "PlusJakartaSans_500Medium",
  demi: "PlusJakartaSans_600SemiBold",
  gras: "PlusJakartaSans_700Bold",
  titre: "PlusJakartaSans_800ExtraBold",
};

export const rayon = { s: 10, m: 14, l: 20 };
