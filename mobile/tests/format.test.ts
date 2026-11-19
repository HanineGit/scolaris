import { strict as assert } from "node:assert";
import { test } from "node:test";

import { date, lireDate, mois, note, reglesMotDePasse } from "../src/lib/format.ts";

test("affichage des notes et des dates", () => {
  assert.equal(note("14.50"), "14,50");
  assert.equal(note(null), "—");
  assert.equal(date("2026-10-02"), "02/10/2026");
  assert.equal(mois("2026-09-18"), "Septembre 2026");
});

test("lecture des dates saisies (filtre de période)", () => {
  assert.equal(lireDate("01/09/2026"), "2026-09-01");
  assert.equal(lireDate("31/02/2026"), null);
  assert.equal(lireDate("2026-09-01"), null);
  assert.equal(lireDate("1/9/26"), null);
});

test("politique de mot de passe identique au serveur", () => {
  assert.ok(reglesMotDePasse("Correct-Cheval-42!").every((r) => r.ok));
  assert.ok(!reglesMotDePasse("motdepasse").every((r) => r.ok));
});

test("motif de réclamation contrôlé comme sur le serveur", async () => {
  const { motifValide } = await import("../src/lib/format.ts");
  assert.equal(motifValide("trop court"), false);
  assert.equal(motifValide("L'exercice 3 n'a pas été pris en compte."), true);
  assert.equal(motifValide("L'exercice 3 n'a pas été pris en compte <script>"), false);
  assert.equal(motifValide("x".repeat(501)), false);
});

test("statuts de réclamation et horodatage", async () => {
  const { STATUTS_RECLAMATION, dateHeure } = await import("../src/lib/format.ts");
  assert.deepEqual(STATUTS_RECLAMATION.ACCEPTEE, ["Acceptée", "ok"]);
  assert.equal(dateHeure(null), "—");
  assert.match(dateHeure("2026-11-19T18:14:05+00:00"), /^19\/11\/2026 à \d{2}:14$/);
});
