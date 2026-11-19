import { useCallback, useEffect, useState } from "react";

import { ErreurApi } from "../lib/api";
import { mesNotes, type Filtres, type MesNotes } from "../lib/donnees";

/** Chargement des notes : conservées en mémoire uniquement, jamais écrites sur le téléphone. */
export function useNotes(filtres: Filtres) {
  const [donnees, setDonnees] = useState<MesNotes | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(true);
  const cle = JSON.stringify(filtres);

  const charger = useCallback(() => {
    setEnCours(true);
    mesNotes(JSON.parse(cle))
      .then((d) => { setDonnees(d); setErreur(null); })
      .catch((e) => setErreur(e instanceof ErreurApi ? e.message : "Une erreur est survenue."))
      .finally(() => setEnCours(false));
  }, [cle]);

  useEffect(charger, [charger]);
  return { donnees, erreur, enCours, recharger: charger };
}
