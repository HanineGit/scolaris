import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, View } from "react-native";

import { ErreurApi } from "../../lib/api";
import { STATUTS_RECLAMATION, TYPES, date, dateHeure, mesReclamations, note, type Reclamation } from "../../lib/donnees";
import { useNotifications } from "../../lib/notifications";
import { BarreHaut, Carte, Message, Onglets, Statut, T, useStyles } from "../../ui/composants";
import { allerA } from "../../ui/navigation";
import { police } from "../../ui/theme";

/** M7 : suivi des réclamations de l'étudiant (F19). */
export default function Reclamations() {
  const { c, s } = useStyles();
  const { nonLues } = useNotifications();
  const [liste, setListe] = useState<Reclamation[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(true);
  const charger = useCallback(() => {
    setEnCours(true);
    mesReclamations().then((d) => { setListe(d.elements); setErreur(null); })
      .catch((e) => setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue."))
      .finally(() => setEnCours(false));
  }, []);
  useEffect(charger, [charger]);

  return (
    <View style={s.ecran}>
      <BarreHaut titre="Réclamations" sousTitre="Suivi de vos contestations" notifications={nonLues}
        versNotifications={() => router.push("/notifications")} />
      <ScrollView refreshControl={<RefreshControl refreshing={enCours} onRefresh={charger} />} contentContainerStyle={{ paddingTop: 16, paddingBottom: 20 }}>
        {erreur && <View style={{ padding: 16 }}><Message type="er">{erreur}</Message></View>}
        {(liste ?? []).map((r) => {
          const [libelle, ton] = STATUTS_RECLAMATION[r.statut];
          return (
            <Carte key={r.id} style={{ padding: 16 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <T style={{ fontFamily: police.gras, fontSize: 15.5 }}>{r.note.matiere_libelle}</T>
                  <T style={{ color: c.mu, fontSize: 13, marginTop: 2 }}>{TYPES[r.note.type_evaluation]} du {date(r.note.date_evaluation)}</T>
                </View>
                <T style={s.valeur}>{note(r.note.valeur)}</T>
              </View>
              <View style={{ marginTop: 10 }}><Statut ton={ton}>{libelle}</Statut></View>
              <T style={{ fontSize: 13.5, color: c.tx2, marginTop: 10, lineHeight: 19 }}>« {r.motif} »</T>
              {r.reponse && (
                <View style={{ backgroundColor: c.surface2, borderRadius: 10, padding: 12, marginTop: 10 }}>
                  <T style={{ fontFamily: police.demi, fontSize: 12.5, color: c.mu, marginBottom: 4 }}>Réponse de l'enseignant</T>
                  <T style={{ fontSize: 13.5, lineHeight: 19 }}>{r.reponse}</T>
                </View>
              )}
              <T style={{ fontSize: 12, color: c.fa, marginTop: 10 }}>Déposée le {dateHeure(r.soumise_le)}</T>
            </Carte>
          );
        })}
        {liste?.length === 0 && (
          <View style={{ padding: 16 }}>
            <Message type="in">Aucune réclamation. Pour contester une note publiée, ouvrez la matière dans l'onglet « Notes » puis choisissez « Contester ».</Message>
          </View>
        )}
      </ScrollView>
      <Onglets actif="reclamations" aller={allerA} />
    </View>
  );
}
