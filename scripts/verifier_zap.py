"""Seuil de l'analyse dynamique : échec si ZAP signale un risque moyen ou élevé.

    python scripts/verifier_zap.py rapports/zap.json

Les alertes de risque faible ou informatives sont affichées sans bloquer ;
les fausses alertes justifiées sont écartées dans regles-zap.conf.
"""
import json
import sys
from pathlib import Path

SEUIL = 2  # 0 informatif, 1 faible, 2 moyen, 3 élevé
REGLES = Path(__file__).resolve().parents[1] / "regles-zap.conf"


def ignorees() -> set[str]:
    """Règles marquées IGNORE (avec leur justification) dans regles-zap.conf."""
    return {l.split("	")[0] for l in REGLES.read_text(encoding="utf-8").splitlines()
            if not l.startswith("#") and "	IGNORE	" in l}


def main(chemin: Path) -> int:
    rapport = json.loads(chemin.read_text(encoding="utf-8"))
    bloquantes = 0
    exclues = ignorees()
    for site in rapport.get("site", []):
        for alerte in site.get("alerts", []):
            if alerte.get("pluginid") in exclues:
                continue
            niveau = int(alerte.get("riskcode", 0))
            marque = "BLOQUANT" if niveau >= SEUIL else "info"
            print(f"[{marque}] {alerte.get('pluginid')} {alerte.get('alert')} "
                  f"({alerte.get('riskdesc')}, {alerte.get('count', '?')} occurrence(s))")
            bloquantes += niveau >= SEUIL
    if bloquantes:
        print(f"{bloquantes} alerte(s) de risque moyen ou élevé : livraison bloquée.")
        return 1
    print("Aucune alerte de risque moyen ou élevé.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
