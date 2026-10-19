"""Kennungen fuer Profile (Dateinamen)."""
from neondeck.profile.ids import slugify


def test_slugify():
    assert slugify("Größe & Übung") == "groesse-uebung"
    assert slugify("  ") == "profil"
