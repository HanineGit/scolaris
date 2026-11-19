"""Tests du service Audit : chaînage, intégrité, accès (R23 à R26)."""
import uuid

import pytest
from sqlalchemy import update

from scolaris_common.audit import construire_evenement
from scolaris_common.testing import entetes


def admin():
    return entetes("ADMINISTRATEUR", identifiant="a.tchinda")


def publier(env, action="NOTE_MODIFIEE", **kw):
    from app.chaine import inserer
    ev = construire_evenement(service="notes", action=action, resultat=kw.pop("resultat", "SUCCES"),
                              acteur_id=uuid.uuid4(), acteur_identifiant=kw.pop("acteur", "j.abena"),
                              role="ENSEIGNANT", ressource="note", ressource_id=uuid.uuid4(), details=kw)
    assert inserer(env.bdd.fabrique, ev)
    return ev


def test_chaine_integre_apres_insertions(env):
    for i in range(5):
        publier(env, avant=str(i), apres=str(i + 1))
    r = env.client.post("/api/v1/audit/integrite/verification", headers=admin()).json()
    assert r["integre"] is True and r["nombre"] == 5


def test_alteration_detectee(env):
    """R23 : toute altération est détectée par la vérification de la chaîne."""
    from app.models import EvenementAudit
    for i in range(4):
        publier(env, apres=str(i))
    with env.bdd.fabrique() as s:  # simulation d'une falsification directe en base
        s.execute(update(EvenementAudit).where(EvenementAudit.numero == 2).values(details={"apres": "20"}))
        s.commit()
    r = env.client.post("/api/v1/audit/integrite/verification", headers=admin()).json()
    assert r["integre"] is False and r["premier_defaut"] == 2
    assert env.client.get("/api/v1/audit/integrite", headers=admin()).json()["integre"] is False


def test_suppression_detectee(env):
    from app.models import EvenementAudit
    for _ in range(3):
        publier(env)
    with env.bdd.fabrique() as s:
        s.query(EvenementAudit).filter(EvenementAudit.numero == 2).delete()
        s.commit()
    assert env.client.post("/api/v1/audit/integrite/verification", headers=admin()).json()["integre"] is False


def test_evenement_rejoue_non_duplique(env):
    """R25 : un message renvoyé deux fois par le bus n'est enregistré qu'une fois."""
    from app.chaine import inserer
    ev = publier(env)
    assert inserer(env.bdd.fabrique, ev) is False
    assert env.client.get("/api/v1/audit/evenements", headers=admin()).json()["total"] == 1


def test_message_mal_forme_refuse(env):
    from app.chaine import inserer
    with pytest.raises(ValueError):
        inserer(env.bdd.fabrique, {"action": "x; DROP TABLE", "id": "pas-un-uuid"})


def test_secrets_masques_meme_si_le_service_source_les_envoie(env):
    publier(env, mot_de_passe="Secret123!", jeton="abc")
    e = env.client.get("/api/v1/audit/evenements", headers=admin()).json()["elements"][0]
    detail = env.client.get(f"/api/v1/audit/evenements/{e['id']}", headers=admin()).json()
    assert detail["details"]["mot_de_passe"] == "***" and detail["details"]["jeton"] == "***"


def test_filtres_et_detail(env):
    publier(env, action="AUTH_ECHEC", resultat="ECHEC", acteur="ETU-2026-0151")
    publier(env, action="NOTE_AJOUTEE")
    liste = env.client.get("/api/v1/audit/evenements?resultat=ECHEC", headers=admin()).json()
    assert liste["total"] == 1 and liste["elements"][0]["acteur"] == "ETU-2026-0151"
    assert env.client.get("/api/v1/audit/evenements?acteur=abena", headers=admin()).json()["total"] == 1
    assert "AUTH_ECHEC" in env.client.get("/api/v1/audit/actions", headers=admin()).json()


@pytest.mark.parametrize("role", ["ENSEIGNANT", "ETUDIANT"])
def test_journal_reserve_a_l_administrateur(env, role):
    """R26 : un enseignant reçoit 403 et le refus entre lui-même dans la chaîne."""
    assert env.client.get("/api/v1/audit/evenements", headers=entetes(role, identifiant="m.ngono")).status_code == 403
    liste = env.client.get("/api/v1/audit/evenements?action=ACCES_REFUSE", headers=admin()).json()
    assert liste["total"] == 1 and liste["elements"][0]["acteur"] == "m.ngono"


def test_aucune_route_d_ecriture_sur_le_journal(env):
    publier(env)
    e = env.client.get("/api/v1/audit/evenements", headers=admin()).json()["elements"][0]
    for methode in ("put", "patch", "delete"):
        assert getattr(env.client, methode)(f"/api/v1/audit/evenements/{e['id']}", headers=admin()).status_code == 405


def test_us25_verification_de_100000_evenements_en_moins_d_une_minute(env):
    """Critère : « La vérification de 100 000 événements dure moins d'une minute. »"""
    import time
    import uuid as _uuid
    from datetime import datetime, timezone

    from app.chaine import ORIGINE, calculer
    from app.models import EvenementAudit
    precedente, lignes = ORIGINE, []
    for n in range(1, 100_001):
        e = EvenementAudit(numero=n, id=_uuid.uuid4(), horodatage=datetime.now(timezone.utc), service="notes",
                           action="NOTE_AJOUTEE", resultat="SUCCES", acteur_identifiant="j.abena", details={"valeur": "12.00"},
                           empreinte_precedente=precedente)
        e.empreinte = calculer(precedente, e)
        precedente = e.empreinte
        lignes.append(e)
    with env.bdd.fabrique() as s:
        s.add_all(lignes)
        s.commit()
    debut = time.perf_counter()
    r = env.client.post("/api/v1/audit/integrite/verification", headers=admin()).json()
    duree = time.perf_counter() - debut
    assert r["integre"] is True and r["nombre"] == 100_000
    assert duree < 60, f"{duree:.1f} s"
