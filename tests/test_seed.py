"""Tests for the seed loader's auto-load policy.

Regression guard: a shipped build must start EMPTY. Only seed.local.json may
auto-load; the anonymised seed.sample.json must never be picked up.
"""

from modules import seed


def test_sample_never_in_autoseed_names():
    assert "seed.local.json" in seed._AUTO_SEED_FILENAMES
    assert "seed.sample.json" not in seed._AUTO_SEED_FILENAMES


def test_sample_only_folder_is_not_autoloaded(tmp_path, monkeypatch):
    # A folder that contains ONLY the sample (as a bundle would) yields nothing.
    (tmp_path / "seed.sample.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(seed, "_candidate_dirs", lambda: [tmp_path])
    assert seed.find_seed_file() is None


def test_local_seed_is_found_over_sample(tmp_path, monkeypatch):
    (tmp_path / "seed.local.json").write_text("{}", encoding="utf-8")
    (tmp_path / "seed.sample.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(seed, "_candidate_dirs", lambda: [tmp_path])
    found = seed.find_seed_file()
    assert found is not None and found.name == "seed.local.json"
