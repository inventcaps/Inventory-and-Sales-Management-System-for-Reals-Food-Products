import sys
import pytest
from django.db import connection
from django.apps import apps


def create_all_tables():
    for model in apps.get_models():
        if model._meta.proxy or model._meta.abstract:
            continue
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.create_model(model)
        except Exception:
            pass


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        create_all_tables()
