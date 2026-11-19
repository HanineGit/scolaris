"""Briques de sécurité partagées par les microservices Scolaris.

Chaque microservice reste propriétaire de ses données ; cette bibliothèque ne
contient que des mécanismes transverses : lecture des secrets, vérification des
jetons, gestion des erreurs, journalisation et publication des événements
d'audit.
"""
