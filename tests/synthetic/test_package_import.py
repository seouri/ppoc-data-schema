def test_package_has_version() -> None:
    import synthetic

    assert synthetic.__version__ == "0.1.0"
