import { useMemo, type ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Path } from "react-native-svg";

import { police, rayon, useCouleurs, type Couleurs } from "./theme";

const CHEMINS: Record<string, string> = {
  out: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  back: "m15 18-6-6 6-6",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  cal: "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM16 2v4M8 2v4M3 10h18",
  filter: "M22 3H2l8 9.5V19l4 2v-8.5z",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 16v-4M12 8h.01",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  eye: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  chev: "m9 18 6-6-6-6",
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5V21h16",
  message: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6",
  key: "M7.5 11a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM10.7 12.3 20 3M17 6l3 3M14.5 8.5l2 2",
  device: "M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM12 18h.01",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
};

export function Icone({ nom, taille = 18, couleur }: { nom: string; taille?: number; couleur?: string }) {
  const c = useCouleurs();
  return (
    <Svg width={taille} height={taille} viewBox="0 0 24 24" fill="none" stroke={couleur ?? c.tx} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <Path d={CHEMINS[nom] ?? ""} />
    </Svg>
  );
}

/** Styles calculés pour le thème courant (clair ou sombre). */
export function useStyles() {
  const c = useCouleurs();
  const s = useMemo(() => creerStyles(c), [c]);
  return { c, s };
}

export function T({ style, ...p }: React.ComponentProps<typeof Text>) {
  const c = useCouleurs();
  return <Text {...p} style={[{ fontFamily: police.normal, color: c.tx, fontSize: 15 }, style]} />;
}

/** Barre supérieure des écrans connectés, avec la cloche des notifications. */
export function BarreHaut({ titre, sousTitre, retour, actionDroite, notifications, versNotifications }: {
  titre: string; sousTitre?: string; retour?: () => void; actionDroite?: { icone: string; onPress: () => void; libelle: string };
  notifications?: number; versNotifications?: () => void;
}) {
  const marges = useSafeAreaInsets();
  const { c, s } = useStyles();
  return (
    <View style={[s.barre, { paddingTop: marges.top + 10 }]}>
      <View style={{ flexDirection: "row", alignItems: "center", flex: 1, gap: 4 }}>
        {retour && (
          <Pressable onPress={retour} hitSlop={10} accessibilityRole="button" accessibilityLabel="Retour" style={s.icone}>
            <Icone nom="back" taille={22} couleur={c.hdTexte} />
          </Pressable>
        )}
        <View style={{ flex: 1 }}>
          <T style={s.barreTitre} numberOfLines={1}>{titre}</T>
          {sousTitre && <T style={s.barreSous} numberOfLines={1}>{sousTitre}</T>}
        </View>
      </View>
      {versNotifications && (
        <Pressable onPress={versNotifications} hitSlop={10} accessibilityRole="button"
          accessibilityLabel={`Notifications, ${notifications ?? 0} non lues`} style={s.icone}>
          <Icone nom="bell" taille={21} couleur={c.hdTexte} />
          {!!notifications && <View style={s.pastille}><T style={s.pastilleTexte}>{notifications > 9 ? "9+" : notifications}</T></View>}
        </Pressable>
      )}
      {actionDroite && (
        <Pressable onPress={actionDroite.onPress} hitSlop={10} accessibilityRole="button" accessibilityLabel={actionDroite.libelle} style={s.icone}>
          <Icone nom={actionDroite.icone} taille={20} couleur={c.hdTexte} />
        </Pressable>
      )}
    </View>
  );
}

export function Bouton({ titre, onPress, desactive, chargement, variante = "p", icone }: {
  titre: string; onPress: () => void; desactive?: boolean; chargement?: boolean; variante?: "p" | "s" | "d"; icone?: string;
}) {
  const { c, s } = useStyles();
  const inactif = desactive || chargement;
  const couleurTexte = variante === "p" ? c.prTexte : variante === "d" ? c.er : c.tx;
  return (
    <Pressable onPress={onPress} disabled={inactif} accessibilityRole="button" accessibilityState={{ disabled: !!inactif }}
      style={({ pressed }) => [s.bouton, variante !== "p" && s.boutonS, variante === "d" && { borderColor: c.er },
                               inactif && { opacity: 0.45 }, pressed && { opacity: 0.85, transform: [{ scale: 0.99 }] }]}>
      {chargement ? <ActivityIndicator color={couleurTexte} /> : (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          {icone && <Icone nom={icone} taille={18} couleur={couleurTexte} />}
          <T style={[s.boutonTexte, { color: couleurTexte }]}>{titre}</T>
        </View>
      )}
    </Pressable>
  );
}

export function Champ({ libelle, erreur, droite, ...p }: TextInputProps & { libelle: string; erreur?: string | null; droite?: ReactNode }) {
  const { c, s } = useStyles();
  return (
    <View style={{ marginBottom: 14 }}>
      <T style={s.libelle}>{libelle}</T>
      <View style={[s.champ, erreur ? { borderColor: c.er } : null, p.multiline ? { height: 110, alignItems: "flex-start", paddingVertical: 10 } : null]}>
        <TextInput placeholderTextColor={c.fa} accessibilityLabel={libelle} {...p} style={[s.saisie, p.multiline && { textAlignVertical: "top" }]} />
        {droite}
      </View>
      {erreur ? <T style={s.aideErreur}>{erreur}</T> : null}
    </View>
  );
}

export function Message({ type, children }: { type: "er" | "in" | "ok" | "wa"; children: ReactNode }) {
  const c = useCouleurs();
  const [fond, texte, icone] = { er: [c.erBg, c.er, "alert"], in: [c.inBg, c.in, "info"], ok: [c.okBg, c.ok, "check"], wa: [c.waBg, c.wa, "alert"] }[type];
  return (
    <View style={{ flexDirection: "row", gap: 10, alignItems: "flex-start", borderRadius: rayon.s, padding: 12, backgroundColor: fond }}
      accessibilityRole={type === "er" ? "alert" : "text"}>
      <Icone nom={icone} taille={17} couleur={texte} />
      <T style={{ color: texte, fontSize: 13.5, flex: 1, lineHeight: 19 }}>{children}</T>
    </View>
  );
}

export function Carte({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  const { s } = useStyles();
  return <View style={[s.carte, style]}>{children}</View>;
}

export function Statut({ ton, children }: { ton: "ok" | "er" | "wa" | "in" | "mu"; children: ReactNode }) {
  const c = useCouleurs();
  const [fond, texte] = { ok: [c.okBg, c.ok], er: [c.erBg, c.er], wa: [c.waBg, c.wa], in: [c.inBg, c.in], mu: [c.surface2, c.mu] }[ton];
  return (
    <View style={{ backgroundColor: fond, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, alignSelf: "flex-start" }}>
      <T style={{ color: texte, fontSize: 12, fontFamily: police.demi }}>{children}</T>
    </View>
  );
}

export type Onglet = "accueil" | "notes" | "reclamations" | "compte";

/** Barre d'onglets du bas. */
export function Onglets({ actif, aller }: { actif: Onglet; aller: (o: Onglet) => void }) {
  const marges = useSafeAreaInsets();
  const { c, s } = useStyles();
  const onglet = (cle: Onglet, icone: string, libelle: string) => (
    <Pressable key={cle} onPress={() => cle !== actif && aller(cle)} style={s.onglet} accessibilityRole="tab"
      accessibilityState={{ selected: actif === cle }} accessibilityLabel={libelle}>
      <View style={[s.ongletPastille, actif === cle && { backgroundColor: c.prDoux }]}>
        <Icone nom={icone} taille={21} couleur={actif === cle ? c.pr : c.fa} />
      </View>
      <T style={[s.ongletTexte, { color: actif === cle ? c.pr : c.fa }]}>{libelle}</T>
    </Pressable>
  );
  return (
    <View style={[s.onglets, { paddingBottom: Math.max(marges.bottom, 6) }]} accessibilityRole="tablist">
      {onglet("accueil", "home", "Accueil")}
      {onglet("notes", "book", "Notes")}
      {onglet("reclamations", "message", "Réclamations")}
      {onglet("compte", "user", "Compte")}
    </View>
  );
}

function creerStyles(c: Couleurs) {
  const ombre = { shadowColor: c.ombre, shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 2 };
  return StyleSheet.create({
    ecran: { flex: 1, backgroundColor: c.bg },
    barre: { backgroundColor: c.hd, paddingHorizontal: 16, paddingBottom: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    barreTitre: { color: "#FFFFFF", fontSize: 20, fontFamily: police.gras, letterSpacing: -0.3 },
    barreSous: { color: c.hdSous, fontSize: 13, marginTop: 1 },
    icone: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 12 },
    pastille: { position: "absolute", top: 3, right: 3, minWidth: 18, height: 18, borderRadius: 9, backgroundColor: "#D0563F",
      alignItems: "center", justifyContent: "center", paddingHorizontal: 4, borderWidth: 2, borderColor: c.hd },
    pastilleTexte: { color: "#FFFFFF", fontSize: 10, fontFamily: police.gras },
    bouton: { backgroundColor: c.pr, height: 50, borderRadius: rayon.m, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: c.pr, paddingHorizontal: 18 },
    boutonS: { backgroundColor: c.surface, borderColor: c.line },
    boutonTexte: { fontSize: 16, fontFamily: police.demi },
    libelle: { fontSize: 13.5, fontFamily: police.demi, marginBottom: 7, color: c.tx2 },
    champ: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: c.line, borderRadius: rayon.m, backgroundColor: c.surface, paddingHorizontal: 14, height: 50 },
    saisie: { flex: 1, fontFamily: police.normal, fontSize: 16, color: c.tx, height: "100%" },
    aideErreur: { color: c.er, fontSize: 12.5, marginTop: 5 },
    carte: { backgroundColor: c.surface, borderRadius: rayon.l, marginHorizontal: 16, marginBottom: 12, overflow: "hidden", ...ombre },
    resume: { backgroundColor: c.surface, borderRadius: rayon.l, margin: 16, marginBottom: 4, padding: 18, flexDirection: "row",
      justifyContent: "space-between", alignItems: "center", ...ombre },
    section: { fontSize: 12, fontFamily: police.gras, color: c.mu, letterSpacing: 0.8, paddingHorizontal: 20, paddingTop: 18, paddingBottom: 8 },
    liste: { backgroundColor: c.surface, borderRadius: rayon.l, marginHorizontal: 16, overflow: "hidden", ...ombre },
    ligne: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: c.line },
    ligneTitre: { fontSize: 15.5, fontFamily: police.demi },
    ligneSous: { fontSize: 13, color: c.mu, marginTop: 2 },
    valeur: { fontSize: 19, fontFamily: police.gras, textAlign: "right" },
    modifiee: { fontSize: 12.5, color: c.wa, fontFamily: police.demi, marginTop: 3 },
    onglets: { flexDirection: "row", backgroundColor: c.surface, borderTopWidth: StyleSheet.hairlineWidth, borderColor: c.line, paddingTop: 6 },
    onglet: { flex: 1, alignItems: "center", justifyContent: "center", gap: 3 },
    ongletPastille: { width: 52, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center" },
    ongletTexte: { fontSize: 11.5, fontFamily: police.demi },
    puce: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: c.line, backgroundColor: c.surface, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 },
    vide: { textAlign: "center", color: c.mu, padding: 32 },
  });
}
