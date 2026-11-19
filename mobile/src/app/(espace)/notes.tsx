import { router } from "expo-router";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";

import { note } from "../../lib/donnees";
import { useNotifications } from "../../lib/notifications";
import { BarreHaut, Message, Onglets, T, useStyles } from "../../ui/composants";
import { allerA } from "../../ui/navigation";
import { police } from "../../ui/theme";
import { useNotes } from "../../ui/useNotes";

/** Choix de la vue des notes : par matière (M3) ou par date (M5). */
export function Vues({ active }: { active: "matieres" | "dates" }) {
  const { c } = useStyles();
  const bouton = (cle: "matieres" | "dates", libelle: string, vers: "/notes" | "/dates") => (
    <Pressable onPress={() => cle !== active && router.replace(vers)} accessibilityRole="tab" accessibilityState={{ selected: active === cle }}
      style={{ flex: 1, paddingVertical: 9, borderRadius: 10, alignItems: "center", backgroundColor: active === cle ? c.surface : "transparent" }}>
      <T style={{ fontFamily: police.demi, fontSize: 14, color: active === cle ? c.pr : c.mu }}>{libelle}</T>
    </Pressable>
  );
  return (
    <View style={{ flexDirection: "row", backgroundColor: c.sand, borderRadius: 13, padding: 4, margin: 16, marginBottom: 4 }} accessibilityRole="tablist">
      {bouton("matieres", "Par matière", "/notes")}
      {bouton("dates", "Par date", "/dates")}
    </View>
  );
}

/** M3 : notes par matière avec moyennes (F11). */
export default function NotesParMatiere() {
  const { donnees, erreur, enCours, recharger } = useNotes({});
  const { nonLues } = useNotifications();
  const { c, s } = useStyles();

  return (
    <View style={s.ecran}>
      <BarreHaut titre="Mes notes" sousTitre="Notes publiées par le service de scolarité"
        notifications={nonLues} versNotifications={() => router.push("/notifications")} />
      <Vues active="matieres" />
      <ScrollView refreshControl={<RefreshControl refreshing={enCours} onRefresh={recharger} />} contentContainerStyle={{ paddingBottom: 20 }}>
        {erreur && <View style={{ padding: 16 }}><Message type="er">{erreur}</Message></View>}
        {donnees && (
          <>
            <View style={s.resume}>
              <View>
                <T style={{ fontSize: 13, color: c.mu }}>Moyenne générale</T>
                <T style={{ fontSize: 28, fontFamily: police.gras, color: c.pr }}>{note(donnees.moyenne_generale)}
                  <T style={{ fontSize: 14, color: c.fa }}> / 20</T></T>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <T style={{ fontSize: 13, color: c.mu }}>{donnees.matieres.length} matières</T>
                <T style={{ fontSize: 13, color: c.mu }}>{donnees.notes.length} notes</T>
              </View>
            </View>
            <T style={s.section}>PAR MATIÈRE</T>
            <View style={s.liste}>
              {donnees.matieres.map((m) => {
                const sous = Number(m.moyenne) < 10;
                return (
                  <Pressable key={m.code} style={({ pressed }) => [s.ligne, pressed && { backgroundColor: c.surface2 }]}
                    onPress={() => router.push(`/matiere/${m.code}`)} accessibilityRole="button" accessibilityLabel={`${m.libelle}, moyenne ${note(m.moyenne)}`}>
                    <View style={{ width: 4, alignSelf: "stretch", borderRadius: 2, marginRight: 12, backgroundColor: sous ? c.er : c.tan }} />
                    <View style={{ flex: 1 }}>
                      <T style={s.ligneTitre}>{m.libelle}</T>
                      <T style={s.ligneSous}>Coef. {m.coefficient.replace(".0", "")} · {m.nombre_notes} note{m.nombre_notes > 1 ? "s" : ""}</T>
                    </View>
                    <View><T style={[s.valeur, sous && { color: c.er }]}>{note(m.moyenne)}</T>
                      <T style={{ fontSize: 12, color: c.fa, textAlign: "right" }}>moyenne</T></View>
                  </Pressable>
                );
              })}
            </View>
            {donnees.matieres.length === 0 && <T style={s.vide}>Aucune note n'est encore publiée.</T>}
          </>
        )}
      </ScrollView>
      <Onglets actif="notes" aller={allerA} />
    </View>
  );
}
