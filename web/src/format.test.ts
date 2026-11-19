import { describe, expect, it } from "vitest";

import { requete } from "./api";
import { emailValide, lireNote, nomValide, note, reglesMotDePasse } from "./format";

describe("saisie des notes", () => {
  it("accepte la virgule et normalise à deux décimales", () => {
    expect(lireNote("14,5")).toBe("14.50");
    expect(lireNote("20")).toBe("20.00");
    expect(lireNote("0")).toBe("0.00");
  });
  it.each(["21", "-1", "12.345", "abc", "", "1e1", "14,5,0"])("refuse « %s »", (v) => {
    expect(lireNote(v)).toBeNull();
  });
  it("affiche avec une virgule", () => expect(note("14.50")).toBe("14,50"));
});

describe("validation des champs", () => {
  it.each(["Diallo", "N'Diaye", "Jean-Paul", "Éléonore"])("nom valide : %s", (n) => expect(nomValide(n)).toBe(true));
  it.each(["<script>", "A", "Diallo3", "Robert'); DROP TABLE"])("nom refusé : %s", (n) => expect(nomValide(n)).toBe(false));
  it("adresse e-mail", () => {
    expect(emailValide("a.diallo@etu.univ-exemple.cm")).toBe(true);
    expect(emailValide("a.diallo@univ")).toBe(false);
  });
});

describe("politique de mot de passe", () => {
  it("toutes les règles respectées", () => expect(reglesMotDePasse("Correct-Cheval-42!").every((r) => r.ok)).toBe(true));
  it("mot de passe court refusé", () => expect(reglesMotDePasse("Ab1!").every((r) => r.ok)).toBe(false));
});

describe("paramètres de requête", () => {
  it("ignore les valeurs vides et encode les autres", () => {
    expect(requete({ q: "d'ia & co", vide: "", nul: null, page: 2 })).toBe("?q=d%27ia+%26+co&page=2");
    expect(requete({})).toBe("");
  });
});
