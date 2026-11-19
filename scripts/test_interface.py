"""Test d'interface du back-office dans un vrai navigateur (Microsoft Edge, piloté par Playwright).

Parcours : activation de l'administrateur, connexion à deux facteurs, création
d'un enseignant, d'une matière et d'un étudiant, affectation, saisie et
modification d'une note par l'enseignant, consultation du journal d'audit.
Chaque écran est capturé dans le dossier indiqué.

Prérequis : pile démarrée à neuf (docker compose down -v && docker compose up -d).
Usage : python scripts/test_interface.py [dossier_captures]
"""
import os
import re
import secrets
import sys
import time
import uuid
from pathlib import Path

import httpx
import pyotp
from playwright.sync_api import Page, expect, sync_playwright

URL = os.environ.get("SCOLARIS_URL", "https://localhost:9443")
MAILPIT = f"http://127.0.0.1:{os.environ.get('MAILPIT_PORT', '8026')}/api/v1"
# Jamais de mot de passe écrit dans le code : variable du pipeline ou valeur aléatoire.
MDP = os.environ.get("SCOLARIS_MDP_TEST") or f"Sc-{secrets.token_urlsafe(12)}9a!"
CAPTURES = Path(sys.argv[1] if len(sys.argv) > 1 else "captures")
CAPTURES.mkdir(parents=True, exist_ok=True)
dernier_pas: dict[str, int] = {}


def lien(destinataire: str) -> str:
    for _ in range(30):
        msgs = httpx.get(f"{MAILPIT}/search", params={"query": f"to:{destinataire}"}).json()["messages"]
        if msgs:
            texte = httpx.get(f"{MAILPIT}/message/{msgs[0]['ID']}").json()["Text"]
            return re.search(r"(https://\S+#jeton=[A-Za-z0-9_\-]+)", texte).group(1)
        time.sleep(0.5)
    raise RuntimeError(f"Aucun e-mail pour {destinataire}")


def code(secret: str) -> str:
    """Code TOTP d'un pas non encore utilisé (le serveur refuse le rejeu)."""
    while int(time.time()) // 30 <= dernier_pas.get(secret, -1):
        time.sleep(1)
    dernier_pas[secret] = int(time.time()) // 30
    return pyotp.TOTP(secret).now()


def capture(page: Page, nom: str):
    page.wait_for_timeout(400)
    page.screenshot(path=str(CAPTURES / f"{nom}.png"))
    print(f"  capture {nom}")


def activer(page: Page, email: str, nom_capture: str | None = None) -> str | None:
    page.goto("about:blank")
    page.goto(lien(email))
    expect(page.get_by_text("Activation du compte").first).to_be_visible()
    page.get_by_label("Nouveau mot de passe").fill(MDP)
    page.get_by_label("Confirmer le mot de passe").fill(MDP)
    secret = None
    if page.locator(".cle").count():
        secret = page.locator(".cle").inner_text().replace(" ", "")
        page.get_by_label("Code affiché par l'application").fill(code(secret))
    if nom_capture:
        capture(page, nom_capture)
    page.get_by_role("button", name="Activer mon compte").click()
    expect(page.get_by_text("Votre compte est activé.")).to_be_visible()
    return secret


def connecter(page: Page, identifiant: str, secret: str, captures: bool = False):
    page.goto(f"{URL}/connexion")
    page.get_by_label("Identifiant").fill(identifiant)
    page.get_by_label("Mot de passe").fill(MDP)
    if captures:
        capture(page, "W01_connexion")
    page.get_by_role("button", name="Continuer").click()
    page.get_by_label("Code").fill(code(secret))
    if captures:
        capture(page, "W02_code")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Déconnexion")).to_be_visible()


def deconnecter(page: Page):
    page.get_by_role("button", name="Déconnexion").click()
    expect(page.get_by_role("heading", name="Connexion du personnel")).to_be_visible()


with sync_playwright() as p:
    # NAVIGATEUR=chromium dans le pipeline (Linux) ; Microsoft Edge par défaut sur le poste.
    canal = None if os.environ.get("NAVIGATEUR") == "chromium" else "msedge"
    navigateur = p.chromium.launch(channel=canal, headless=True)
    contexte = navigateur.new_context(ignore_https_errors=True, viewport={"width": 1440, "height": 900}, locale="fr-FR")
    page = contexte.new_page()
    erreurs_console = []
    page.on("console", lambda m: m.type == "error" and erreurs_console.append(m.text))
    suffixe = uuid.uuid4().hex[:5]

    print("1. Administrateur : activation et connexion à deux facteurs")
    secret_admin = activer(page, "admin@univ-exemple.cm", "A1_activation_personnel")
    connecter(page, "admin@univ-exemple.cm", secret_admin, captures=True)
    expect(page).to_have_url(re.compile("/admin/etudiants"))

    print("2. Création d'un enseignant (W11)")
    page.get_by_role("link", name="Comptes du personnel").click()
    page.get_by_role("button", name="Créer un compte").click()
    panneau = page.locator(".panneau")
    panneau.get_by_label(re.compile(r"^Nom")).fill("Abena")
    panneau.get_by_label("Prénom").fill("Jean")
    email_prof = f"j.abena.{suffixe}@univ-exemple.cm"
    panneau.get_by_label("Adresse e-mail professionnelle").fill(email_prof)
    capture(page, "W11_comptes_creation")
    panneau.get_by_role("button", name="Créer le compte").click()
    expect(page.get_by_text("Compte créé")).to_be_visible()
    capture(page, "W11_comptes")

    print("3. Création d'une matière (W10)")
    page.get_by_role("link", name="Matières et affectations").click()
    page.get_by_role("button", name="Nouvelle matière").click()
    code_matiere = f"INF{suffixe[:3].upper()}"
    page.get_by_label("Code").fill(code_matiere)
    page.get_by_label("Coefficient").fill("3")
    page.get_by_label("Libellé").fill("Sécurité logicielle")
    page.get_by_role("button", name="Créer la matière").click()
    expect(page.get_by_role("heading", name=re.compile(code_matiere))).to_be_visible()

    print("4. Ajout d'un étudiant (W8) avec erreur de saisie puis correction")
    page.get_by_role("link", name="Étudiants", exact=True).click()
    page.get_by_role("link", name="Ajouter un étudiant").click()
    page.get_by_label(re.compile(r"^Nom")).fill("Diallo")
    page.get_by_label("Prénom").fill("Aminata3")
    email_etu = f"a.diallo.{suffixe}@etu.univ-exemple.cm"
    page.get_by_label("Adresse e-mail").fill("a.diallo@univ")
    expect(page.get_by_role("button", name="Enregistrer l'étudiant")).to_be_disabled()
    capture(page, "W08_ajout_erreurs")
    page.get_by_label("Prénom").fill("Aminata")
    page.get_by_label("Adresse e-mail").fill(email_etu)
    page.get_by_role("button", name="Enregistrer l'étudiant").click()
    expect(page.get_by_text("Le lien d'activation a été envoyé")).to_be_visible()
    matricule = page.locator(".sub .mono").inner_text()
    capture(page, "W09_fiche")
    page.get_by_role("link", name="Étudiants", exact=True).click()
    expect(page).to_have_url(re.compile(r"/admin/etudiants$"))
    expect(page.get_by_role("cell", name=matricule)).to_be_visible()
    capture(page, "W07_etudiants")
    deconnecter(page)

    print("5. Activation de l'enseignant et de l'étudiant")
    secret_prof = activer(page, email_prof)
    activer(page, email_etu, "A2_activation_etudiant")

    print("6. Affectation de l'enseignant à la matière (W10)")
    connecter(page, "admin@univ-exemple.cm", secret_admin)
    page.get_by_role("link", name="Matières et affectations").click()
    page.get_by_role("row", name=re.compile(code_matiere)).click()
    page.get_by_label("Enseignant").select_option(label="ABENA Jean")
    page.get_by_role("button", name="Affecter").click()
    expect(page.locator(".bx-b").get_by_text("Jean ABENA")).to_be_visible()
    capture(page, "W10_matieres")
    deconnecter(page)

    print("7. Enseignant : mes matières, saisie, modification (W3 à W6)")
    connecter(page, email_prof, secret_prof)
    expect(page.get_by_text(code_matiere)).to_be_visible()
    capture(page, "W03_mes_matieres")
    page.get_by_role("link", name="Saisie des notes").click()
    page.get_by_label("Étudiant (matricule)").fill(matricule)
    page.get_by_role("button", name="Rechercher").click()
    expect(page.get_by_text("DIALLO Aminata")).to_be_visible()
    page.get_by_label("Note sur 20").fill("21")
    expect(page.get_by_role("button", name="Enregistrer", exact=True)).to_be_disabled()
    capture(page, "W04_saisie_erreur")
    page.get_by_label("Note sur 20").fill("13,5")
    page.get_by_role("button", name="Enregistrer", exact=True).click()
    expect(page.get_by_text("Note de 13,50 enregistrée")).to_be_visible()
    capture(page, "W04_saisie")
    page.get_by_role("link", name="Consultation des notes").click()
    expect(page).to_have_url(re.compile("/enseignant/notes"))
    expect(page.get_by_text("13,50", exact=True)).to_be_visible()
    capture(page, "W05_notes")
    page.get_by_role("button", name="Modifier").first.click()
    page.get_by_label("Nouvelle valeur").fill("14,5")
    page.get_by_label("Motif de la modification").fill("Erreur de report : question 4 non comptabilisée.")
    capture(page, "W06_modification")
    page.get_by_role("button", name="Confirmer la modification").click()
    expect(page.get_by_text("14,50", exact=True)).to_be_visible()
    deconnecter(page)

    print("8. Administrateur : fiche étudiant et journal d'audit (W9, W12)")
    connecter(page, "admin@univ-exemple.cm", secret_admin)
    page.get_by_role("row", name=re.compile(matricule)).click()
    expect(page.get_by_text("(modifiée)")).to_be_visible()
    page.get_by_role("button", name="Archiver").click()
    page.get_by_label("Saisissez le matricule pour confirmer").fill(matricule[:-1])
    expect(page.locator(".df").get_by_role("button", name="Archiver")).to_be_disabled()
    capture(page, "W09_archivage")
    page.get_by_role("button", name="Annuler").click()
    page.get_by_role("link", name="Journal d'audit").click()
    page.wait_for_timeout(3000)
    page.reload()
    connecter(page, "admin@univ-exemple.cm", secret_admin)  # recharger ferme la session : jetons en mémoire uniquement
    page.get_by_role("link", name="Journal d'audit").click()
    page.get_by_role("button", name="Vérifier maintenant").click()
    expect(page.get_by_text("Chaîne d'intégrité vérifiée")).to_be_visible()
    page.get_by_role("row", name=re.compile("NOTE_MODIFIEE")).first.click()
    expect(page.get_by_text("Détail de l'événement")).to_be_visible()
    capture(page, "W12_audit")

    navigateur.close()
    if erreurs_console:
        print("Erreurs dans la console du navigateur :", erreurs_console)
        sys.exit(1)
    print(f"\nParcours d'interface réussi ; captures dans {CAPTURES.resolve()}")
