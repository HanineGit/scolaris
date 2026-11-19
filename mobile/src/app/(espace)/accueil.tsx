import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";

import { ErreurApi } from "../../lib/api";
import { dateHeure, note, synthese, type Synthese } from "../../lib/donnees";
import { useNotifications } from "../../lib/notifications";
import { useSession } from "../../lib/session";
import { BarreHaut, Carte, Icone, Message, Onglets, Statut, T, useStyles } from "../../ui/composants";
import { allerA } from "../../ui/navigation";
import { police } from "../../ui/theme";

/** M0 : tableau de bord de l'étudiant (F24). */
export default function Accueil() {
  const { utilisateur } = useSession();
  const { nonLues } = useNotifications();
  const { c, s } = useStyles();
  const [d, setD] = useState<Synthese | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(true);
  const charger = useCallback(() => {
    setEnCours(true);
    synthese().then((x) => { setD(x); setErreur(null); })
      .catch((e) => setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue."))
      .finally(() => setEnCours(false));
  }, []);
  useEffect(charger, [charger]);

  const moyenne = d?.moyenne_generale ? Number(d.moyenne_generale) : null;
  const points = (d?.evolution ?? []).filter((e) => e.moyenne !== null);
  return (
    <View style={s.ecran}>
      <BarreHaut titre={`Bonjour${utilisateur?.prenom ? ` ${utilisateur.prenom}` : ""}`} sousTitre={utilisateur?.identifiant}
        notifications={nonLues} versNotifications={() => router.push("/notifications")} />
      <ScrollView refreshControl={<RefreshControl refreshing={enCours} onRefresh={charger} />} contentContainerStyle={{ paddingBottom: 20 }}>
        {erreur && <View style={{ padding: 16 }}><Message type="er">{erreur}</Message></View>}
        {d && (
          <>
            <Carte style={{ marginTop: 16, padding: 20, backgroundColor: c.pr }}>
              <T style={{ color: c.prTexte, opacity: 0.8, fontSize: 13.5 }}>Moyenne générale</T>
              <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 6, marginTop: 4 }}>
                <T style={{ color: c.prTexte, fontSize: 44, fontFamily: police.titre, letterSpacing: -1 }}>{note(d.moyenne_generale)}</T>
                <T style={{ color: c.prTexte, opacity: 0.75, fontSize: 16, marginBottom: 9 }}>/ 20</T>
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 8 }}>
                <T style={{ color: c.prTexte, fontFamily: police.demi }}>{d.mention}</T>
                <T style={{ color: c.prTexte, opacity: 0.85 }}>{d.matieres_validees} / {d.matieres} matières validées</T>
              </View>
              {moyenne !== null && (
                <View style={{ height: 8, borderRadius: 4, backgroundColor: "rgba(255,255,255,0.25)", marginTop: 14, overflow: "hidden" }}>
                  <View style={{ width: `${(moyenne / 20) * 100}%`, height: "100%", backgroundColor: c.prTexte, borderRadius: 4 }} />
                </View>
              )}
            </Carte>

            {points.length > 0 && (
              <Carte style={{ padding: 16 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <Icone nom="trend" couleur={c.pr} /><T style={{ fontFamily: police.gras, fontSize: 15.5 }}>Évolution par semestre</T>
                </View>
                <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 12, height: 130 }} accessibilityRole="image"
                  accessibilityLabel={points.map((p) => `${p.libelle} : ${note(p.moyenne)}`).join(", ")}>
                  {points.map((p) => {
                    const v = Number(p.moyenne);
                    return (
                      <View key={p.libelle} style={{ flex: 1, alignItems: "center", gap: 6, justifyContent: "flex-end", height: "100%" }}>
                        <T style={{ fontFamily: police.gras, fontSize: 13 }}>{note(p.moyenne)}</T>
                        <View style={{ width: "70%", height: `${Math.max(6, (v / 20) * 80)}%`, borderRadius: 8, backgroundColor: v < 10 ? c.er : c.tan }} />
                        <T style={{ fontSize: 11.5, color: c.mu }} numberOfLines={1}>{p.libelle}</T>
                      </View>
                    );
                  })}
                </View>
              </Carte>
            )}

            {d.a_surveiller.length > 0 && (
              <>
                <T style={s.section}>MATIÈRES À SURVEILLER</T>
                <View style={s.liste}>
                  {d.a_surveiller.map((m) => (
                    <Pressable key={m.code} style={s.ligne} onPress={() => router.push(`/matiere/${m.code}`)} accessibilityRole="button">
                      <View style={{ flex: 1 }}><T style={s.ligneTitre}>{m.libelle}</T><T style={s.ligneSous}>{m.code} · sous la moyenne</T></View>
                      <T style={[s.valeur, { color: c.er }]}>{note(m.moyenne)}</T>
                    </Pressable>
                  ))}
                </View>
              </>
            )}

            <T style={s.section}>RACCOURCIS</T>
            <View style={{ flexDirection: "row", gap: 12, marginHorizontal: 16 }}>
              {[["book", "Mes notes", () => allerA("notes")], ["message", "Réclamations", () => allerA("reclamations")],
                ["file", "Relevé PDF", () => allerA("compte")]].map(([icone, libelle, action]) => (
                <Pressable key={libelle as string} onPress={action as () => void} accessibilityRole="button"
                  style={({ pressed }) => [s.carte, { flex: 1, marginHorizontal: 0, padding: 14, alignItems: "center", gap: 8 }, pressed && { opacity: 0.85 }]}>
                  <View style={{ width: 42, height: 42, borderRadius: 13, backgroundColor: c.prDoux, alignItems: "center", justifyContent: "center" }}>
                    <Icone nom={icone as string} couleur={c.pr} />
                  </View>
                  <T style={{ fontFamily: police.demi, fontSize: 13 }}>{libelle as string}</T>
                </Pressable>
              ))}
            </View>

            <View style={{ padding: 16, gap: 8 }}>
              {d.reclamations_ouvertes > 0 && <Statut ton="wa">{`${d.reclamations_ouvertes} réclamation(s) en cours`}</Statut>}
              <T style={{ fontSize: 12.5, color: c.fa }}>
                {d.derniere_publication ? `Dernière publication de notes : ${dateHeure(d.derniere_publication)}` : "Aucune note publiée pour l'instant."}
              </T>
            </View>
          </>
        )}
      </ScrollView>
      <Onglets actif="accueil" aller={allerA} />
    </View>
  );
}
