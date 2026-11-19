import { router } from "expo-router";
import { useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, View } from "react-native";

import { TYPES, date, lireDate, mois, note, type Filtres } from "../../lib/donnees";
import { useNotifications } from "../../lib/notifications";
import { BarreHaut, Bouton, Champ, Icone, Message, Onglets, T, useStyles } from "../../ui/composants";
import { allerA } from "../../ui/navigation";
import { police, rayon } from "../../ui/theme";
import { Vues } from "./notes";
import { useNotes } from "../../ui/useNotes";

/** M5 : notes par date, groupées par mois ; M6 : filtres par matière et par période (F11). */
export default function NotesParDate() {
  const { nonLues } = useNotifications();
  const { c, s } = useStyles();
  const [filtres, setFiltres] = useState<Filtres>({});
  const [panneau, setPanneau] = useState(false);
  const { donnees, erreur } = useNotes(filtres);
  const toutes = useNotes({}).donnees;  // liste des matières pour le filtre

  const groupes = useMemo(() => {
    const g: { mois: string; notes: NonNullable<typeof donnees>["notes"] }[] = [];
    for (const n of donnees?.notes ?? []) {
      const m = mois(n.date_evaluation);
      if (g.length === 0 || g[g.length - 1].mois !== m) g.push({ mois: m, notes: [] });
      g[g.length - 1].notes.push(n);
    }
    return g;
  }, [donnees]);

  const libelleMatiere = filtres.matiere ? toutes?.matieres.find((m) => m.code === filtres.matiere)?.libelle ?? filtres.matiere : "Toutes les matières";
  const libellePeriode = filtres.du || filtres.au ? `${filtres.du ? date(filtres.du) : "…"} – ${filtres.au ? date(filtres.au) : "…"}` : "Toute la période";

  return (
    <View style={s.ecran}>
      <BarreHaut titre="Mes notes" sousTitre="Notes publiées par le service de scolarité"
        notifications={nonLues} versNotifications={() => router.push("/notifications")} />
      <Vues active="dates" />
      <Pressable onPress={() => setPanneau(true)} accessibilityRole="button" accessibilityLabel="Filtrer les notes"
        style={{ paddingHorizontal: 16, paddingTop: 10, flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
        <View style={s.puce}><Icone nom="filter" taille={14} couleur={c.mu} /><T style={{ fontSize: 13.5 }}>{libelleMatiere}</T></View>
        <View style={s.puce}><Icone nom="cal" taille={14} couleur={c.mu} /><T style={{ fontSize: 13.5 }}>{libellePeriode}</T></View>
      </Pressable>
      <ScrollView contentContainerStyle={{ paddingBottom: 20 }}>
        {erreur && <View style={{ padding: 16 }}><Message type="er">{erreur}</Message></View>}
        {groupes.map((g) => (
          <View key={g.mois}>
            <T style={s.section}>{g.mois.toUpperCase()}</T>
            <View style={s.liste}>
              {g.notes.map((n, i) => (
                <View key={i} style={s.ligne}>
                  <View style={{ flex: 1 }}>
                    <T style={s.ligneTitre}>{n.matiere_libelle}</T>
                    <T style={s.ligneSous}>{TYPES[n.type_evaluation] ?? n.type_evaluation} · {date(n.date_evaluation)}</T>
                    {n.modifiee_le && <T style={s.modifiee}>Modifiée le {date(n.modifiee_le)}</T>}
                  </View>
                  <T style={s.valeur}>{note(n.valeur)}</T>
                </View>
              ))}
            </View>
          </View>
        ))}
        {donnees && groupes.length === 0 && <T style={s.vide}>Aucune note pour ces critères.</T>}
      </ScrollView>
      <Onglets actif="notes" aller={allerA} />
      <PanneauFiltres visible={panneau} filtres={filtres} matieres={toutes?.matieres ?? []}
        onFermer={() => setPanneau(false)} onAppliquer={(f) => { setFiltres(f); setPanneau(false); }} />
    </View>
  );
}

function PanneauFiltres({ visible, filtres, matieres, onFermer, onAppliquer }: {
  visible: boolean; filtres: Filtres; matieres: { code: string; libelle: string }[];
  onFermer: () => void; onAppliquer: (f: Filtres) => void;
}) {
  const [matiere, setMatiere] = useState(filtres.matiere ?? "");
  const [du, setDu] = useState(filtres.du ? date(filtres.du) : "");
  const [au, setAu] = useState(filtres.au ? date(filtres.au) : "");
  const duIso = du ? lireDate(du) : undefined;
  const auIso = au ? lireDate(au) : undefined;
  const valide = duIso !== null && auIso !== null && (!duIso || !auIso || duIso <= auIso);
  const { c, s } = useStyles();

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onFermer}>
      <Pressable style={{ flex: 1, backgroundColor: "rgba(40,30,22,0.45)" }} onPress={onFermer} accessibilityLabel="Fermer les filtres" />
      <View style={{ backgroundColor: c.surface, borderTopLeftRadius: rayon.l, borderTopRightRadius: rayon.l, padding: 18, paddingBottom: 30 }}>
        <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: c.line, alignSelf: "center", marginBottom: 12 }} />
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <T style={{ fontSize: 18, fontFamily: police.gras }}>Filtrer les notes</T>
          <Pressable onPress={() => { setMatiere(""); setDu(""); setAu(""); }} hitSlop={10}>
            <T style={{ color: c.pr, fontFamily: police.demi }}>Réinitialiser</T>
          </Pressable>
        </View>
        <T style={s.libelle}>Matière</T>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }} contentContainerStyle={{ gap: 8 }}>
          {[{ code: "", libelle: "Toutes" }, ...matieres].map((m) => (
            <Pressable key={m.code} onPress={() => setMatiere(m.code)} accessibilityRole="radio" accessibilityState={{ selected: matiere === m.code }}
              style={[s.puce, matiere === m.code && { backgroundColor: c.pr, borderColor: c.pr }]}>
              <T style={{ fontSize: 13.5, color: matiere === m.code ? c.prTexte : c.tx }}>{m.libelle}</T>
            </Pressable>
          ))}
        </ScrollView>
        <View style={{ flexDirection: "row", gap: 10 }}>
          <View style={{ flex: 1 }}><Champ libelle="Du" value={du} onChangeText={setDu} placeholder="JJ/MM/AAAA" keyboardType="numbers-and-punctuation" maxLength={10}
            erreur={du && duIso === null ? "Date invalide" : null} /></View>
          <View style={{ flex: 1 }}><Champ libelle="Au" value={au} onChangeText={setAu} placeholder="JJ/MM/AAAA" keyboardType="numbers-and-punctuation" maxLength={10}
            erreur={au && auIso === null ? "Date invalide" : null} /></View>
        </View>
        <Bouton titre="Appliquer" desactive={!valide}
          onPress={() => onAppliquer({ matiere: matiere || undefined, du: duIso ?? undefined, au: auIso ?? undefined })} />
      </View>
    </Modal>
  );
}
