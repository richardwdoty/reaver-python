import pytest


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    monkeypatch.setattr('reaver.app.preferences.settings_store',
        lambda: QSettings(str(tmp_path/'preferences.ini'), QSettings.IniFormat))
