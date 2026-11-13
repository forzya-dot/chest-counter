import json

from chest_counter.core.config import DEFAULT_CONFIG, _merge, load_config


def test_creates_default_file_when_missing(tmp_path):
    path = tmp_path / "config.json"
    config = load_config(path)
    assert config == DEFAULT_CONFIG
    assert json.loads(path.read_text(encoding="utf-8")) == DEFAULT_CONFIG


def test_returned_config_is_a_copy(tmp_path):
    config = load_config(tmp_path / "config.json")
    config["hotkeys"]["add"] = "F1"
    assert DEFAULT_CONFIG["hotkeys"]["add"] == "F9"


def test_user_values_are_kept_and_missing_keys_filled(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"hotkeys": {"add": "F6"}, "sound": {"enabled": False}}), encoding="utf-8"
    )
    config = load_config(path)
    assert config["hotkeys"] == {"add": "F6", "undo": "Ctrl+F9", "end_match": "F10"}
    assert config["sound"]["enabled"] is False
    assert config["save_empty_matches"] is False
    # Недостающие ключи дописаны в файл.
    assert json.loads(path.read_text(encoding="utf-8")) == config


def test_wrong_types_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"hotkeys": "F9", "sound": {"enabled": "да"}, "save_empty_matches": 1}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config["hotkeys"] == DEFAULT_CONFIG["hotkeys"]
    assert config["sound"]["enabled"] is True
    assert config["save_empty_matches"] is False


def test_settings_from_old_version_are_dropped(tmp_path):
    """В версии 1.0 был раздел overlay — новая версия его убирает и не падает."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"hotkeys": {"add": "F7"}, "overlay": {"enabled": True, "size": 160}}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert "overlay" not in config
    assert config["hotkeys"]["add"] == "F7"
    assert "overlay" not in json.loads(path.read_text(encoding="utf-8"))


def test_broken_json_is_backed_up_and_replaced(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ это не json", encoding="utf-8")
    config = load_config(path)
    assert config == DEFAULT_CONFIG
    assert (tmp_path / "config.json.bak").read_text(encoding="utf-8") == "{ это не json"
    assert json.loads(path.read_text(encoding="utf-8")) == DEFAULT_CONFIG


def test_file_with_bom_is_read(tmp_path):
    """Блокнот Windows любит сохранять файлы с BOM."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"hotkeys": {"add": "F7"}}), encoding="utf-8-sig")
    assert load_config(path)["hotkeys"]["add"] == "F7"


def test_merge_checks_number_types():
    """Числовых настроек сейчас нет, но правило слияния для них должно работать."""
    defaults = {"size": 160, "ratio": 1.5}
    assert _merge(defaults, {"size": 300, "ratio": 2}) == {"size": 300, "ratio": 2}
    assert _merge(defaults, {"size": "большой", "ratio": True}) == defaults
    # Python читает NaN и Infinity из JSON — в настройках им не место.
    assert _merge(defaults, json.loads('{"size": Infinity, "ratio": NaN}')) == defaults


def test_unwritable_location_still_returns_defaults(tmp_path):
    """Если файл настроек нельзя создать, программа работает с настройками по умолчанию."""
    missing_folder = tmp_path / "нет такой папки" / "config.json"
    assert load_config(missing_folder) == DEFAULT_CONFIG
