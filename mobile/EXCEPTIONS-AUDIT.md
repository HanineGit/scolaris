# Exceptions de l'audit des dépendances mobiles (risque accepté)

Ces trois avis sont autorisés dans `audit-ci.json`. Tous proviennent de
l'outillage de construction d'Expo (`@expo/cli`, `@expo/config`,
`@expo/config-plugins`, `@expo/fingerprint`, `@expo/metro-config`). Ce code
tourne uniquement sur le poste du développeur ou dans le pipeline au moment de
construire l'application. Il n'est pas embarqué dans l'APK installé chez
l'étudiant et ne traite aucune donnée venant des utilisateurs.

| Avis | Paquet | Faiblesse | Pourquoi le risque est accepté |
|---|---|---|---|
| GHSA-mrhx-c7xc-m3w5 | zod 3.25 | Épuisement mémoire sur des collections très volumineuses | Ne valide que les options de la ligne de commande Expo. |
| GHSA-3g3m-2fjr-6pw4 | glob 13 | Annulation par AbortSignal contournée | Parcourt uniquement le dossier du projet pendant la construction. |
| GHSA-g3hv-75wg-m249 | minimatch 10 | Déni de service par des motifs construits | Les motifs sont écrits par l'équipe, jamais fournis par un utilisateur. |

Ces exceptions sont revues à chaque mise à jour du SDK Expo et supprimées dès
qu'une version corrigée est disponible (`npx expo install --fix`). Tout nouvel
avis non listé fait échouer le pipeline.

## Corrections plutôt qu'exceptions

- node-forge (GHSA-6889-vf6x-f3g5, GHSA-w4xr-hqv8-ch44, GHSA-6cv4-p8m7-4r25, GHSA-j8rw-jp99-435v) : version
  corrigée 1.4.3 imposée par `overrides` dans package.json, aucune exception nécessaire.
- deepmerge (GHSA-gcqx-w48m-w2h4) : disparu avec la mise à jour des modules Expo, exception retirée.
