import json

from chest_counter.core.config import DEFAULT_CONFIG, load_config


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
        json.dumps({"hotkeys": {"add": "F6"}, "overlay": {"size": 300}}), encoding="utf-8"
    )
    config = load_config(path)
    assert config["hotkeys"] == {"add": "F6", "undo": "Ctrl+F9", "end_match": "F10"}
    assert config["overlay"]["size"] == 300
    assert config["overlay"]["duration_ms"] == 1500
    assert config["sound"]["enabled"] is True
    # Недостающие ключи дописаны в файл.
    assert json.loads(path.read_text(encoding="utf-8")) == config


def test_wrong_types_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "hotkeys": "F9",
                "sound": {"enabled": "да"},
                "overlay": {"size": "большой", "enabled": 1, "duration_ms": True},
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config["hotkeys"] == DEFAULT_CONFIG["hotkeys"]
    assert config["sound"]["enabled"] is True
    assert config["overlay"]["size"] == 160
    assert config["overlay"]["enabled"] is True
    assert config["overlay"]["duration_ms"] == 1500


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


def test_nan_and_infinity_are_rejected(tmp_path):
    """Python читает NaN и Infinity из JSON — в настройках им не место."""
    path = tmp_path / "config.json"
    path.write_text(
        '{"overlay": {"size": Infinity, "duration_ms": NaN, "offset_x": -Infinity}}',
        encoding="utf-8",
    )
    overlay = load_config(path)["overlay"]
    assert (overlay["size"], overlay["duration_ms"], overlay["offset_x"]) == (160, 1500, 40)


def test_unwritable_location_still_returns_defaults(tmp_path):
    """Если файл настроек нельзя создать, программа работает с настройками по умолчанию."""
    missing_folder = tmp_path / "нет такой папки" / "config.json"
    assert load_config(missing_folder) == DEFAULT_CONFIG
