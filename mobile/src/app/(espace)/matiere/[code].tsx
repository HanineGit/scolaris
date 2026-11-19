import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, View } from "react-native";

import { ErreurApi } from "../../../lib/api";
import { TYPES, date, deposerReclamation, motifValide, note, type NoteEtudiant } from "../../../lib/donnees";
import { BarreHaut, Bouton, Champ, Message, Onglets, T, useStyles } from "../../../ui/composants";
import { allerA } from "../../../ui/navigation";
import { police, rayon } from "../../../ui/theme";
import { useNotes } from "../../../ui/useNotes";

/** M4 : détail d'une matière, évaluations par date (F11) et dépôt d'une réclamation (F19). */
export default function DetailMatiere() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const { c, s } = useStyles();
  // Le code est validé côté serveur (liste blanche) ; l'identité de l'étudiant vient du jeton.
  const { donnees, erreur } = useNotes({ matiere: /^[A-Z0-9]{2,10}$/.test(code ?? "") ? code : "INVALIDE" });
  const [contestee, setContestee] = useState<NoteEtudiant | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const m = donnees?.matieres[0];

  return (
    <View style={s.ecran}>
      <BarreHaut titre={m?.libelle ?? "Matière"} sousTitre={m ? `${code} · Coefficient ${m.coefficient.replace(".0", "")}` : code}
        retour={() => (router.canGoBack() ? router.back() : allerA("notes"))} />
      <ScrollView contentContainerStyle={{ paddingBottom: 20 }}>
        {erreur && <View style={{ padding: 16 }}><Message type="er">{erreur}</Message></View>}
        {succes && <View style={{ padding: 16, paddingBottom: 0 }}><Message type="ok">{succes}</Message></View>}
        {m && (
          <View style={s.resume}>
            <View><T style={{ fontSize: 13, color: c.mu }}>Moyenne de la matière</T>
              <T style={{ fontSize: 28, fontFamily: police.gras, color: Number(m.moyenne) < 10 ? c.er : c.pr }}>{note(m.moyenne)}
                <T style={{ fontSize: 14, color: c.fa }}> / 20</T></T></View>
            <View style={{ alignItems: "flex-end" }}><T style={{ fontSize: 13, color: c.mu }}>Coefficient</T>
              <T style={{ fontSize: 20, fontFamily: police.gras }}>{m.coefficient.replace(".0", "")}</T></View>
          </View>
        )}
        <T style={s.section}>ÉVALUATIONS</T>
        <View style={s.liste}>
          {(donnees?.notes ?? []).map((n) => (
            <View key={n.id} style={s.ligne}>
              <View style={{ flex: 1 }}>
                <T style={s.ligneTitre}>{TYPES[n.type_evaluation] ?? n.type_evaluation}</T>
                <T style={s.ligneSous}>{date(n.date_evaluation)}</T>
                {n.modifiee_le && <T style={s.modifiee}>Modifiée le {date(n.modifiee_le)}</T>}
                <Pressable onPress={() => { setSucces(null); setContestee(n); }} hitSlop={8} accessibilityRole="button"
                  accessibilityLabel={`Contester la note de ${TYPES[n.type_evaluation] ?? n.type_evaluation}`}>
                  <T style={{ color: c.pr, fontFamily: police.demi, fontSize: 13, marginTop: 6 }}>Contester</T>
                </Pressable>
              </View>
              <T style={s.valeur}>{note(n.valeur)}</T>
            </View>
          ))}
        </View>
        <View style={{ padding: 16 }}>
          <Message type="in">Une note peut être contestée dans les 15 jours suivant sa publication. L'enseignant de la matière vous répond dans l'onglet « Réclamations ».</Message>
        </View>
      </ScrollView>
      <Onglets actif="notes" aller={allerA} />
      {contestee && <Contestation n={contestee} onFermer={() => setContestee(null)}
        onFait={() => { setContestee(null); setSucces("Réclamation déposée. Vous serez prévenu de la réponse."); }} />}
    </View>
  );
}

function Contestation({ n, onFermer, onFait }: { n: NoteEtudiant; onFermer: () => void; onFait: () => void }) {
  const { c } = useStyles();
  const [motif, setMotif] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  async function envoyer() {
    setErreur(null); setEnCours(true);
    try { await deposerReclamation(n.id, motif.trim()); onFait(); }
    catch (e) { setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue."); }
    finally { setEnCours(false); }
  }
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onFermer}>
      <Pressable style={{ flex: 1, backgroundColor: "rgba(23,17,13,0.5)" }} onPress={onFermer} accessibilityLabel="Annuler" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={{ backgroundColor: c.surface, borderTopLeftRadius: rayon.l, borderTopRightRadius: rayon.l, padding: 18, paddingBottom: 30 }}>
          <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: c.line, alignSelf: "center", marginBottom: 14 }} />
          <T style={{ fontSize: 18, fontFamily: police.gras }}>Contester une note</T>
          <T style={{ color: c.mu, marginTop: 4, marginBottom: 14 }}>
            {n.matiere_libelle} · {TYPES[n.type_evaluation] ?? n.type_evaluation} du {date(n.date_evaluation)} · {note(n.valeur)} / 20
          </T>
          {erreur && <View style={{ marginBottom: 12 }}><Message type="er">{erreur}</Message></View>}
          <Champ libelle="Motif de la réclamation" value={motif} onChangeText={setMotif} multiline maxLength={500}
            placeholder="Expliquez précisément ce qui vous semble erroné (20 caractères au moins)."
            erreur={motif.trim() && !motifValide(motif) ? "20 à 500 caractères, sans < ni >." : null} />
          <Bouton titre="Envoyer la réclamation" icone="message" desactive={!motifValide(motif)} chargement={enCours} onPress={() => void envoyer()} />
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
