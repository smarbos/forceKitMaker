from forcekit.names import parse_note, note_name, key_ranges, safe_name, unique_name


def test_parse_note():
    assert parse_note("ARP_SYNC_C3") == 60
    assert parse_note("Lead-F#2") == 54
    assert parse_note("Pad Db4") == 73
    assert parse_note("Bass_C-1_v2") == 12
    assert parse_note("Kick01") is None
    assert parse_note("Snare 03") is None
    assert parse_note("A2 to C3") == 60  # last token wins


def test_note_name():
    assert note_name(60) == "C3"
    assert note_name(61) == "C#3"
    assert note_name(0) == "C-2"


def test_key_ranges():
    assert key_ranges([60]) == [(0, 127)]
    assert key_ranges([48, 60, 72]) == [(0, 54), (55, 66), (67, 127)]
    assert key_ranges([60, 61]) == [(0, 60), (61, 127)]


def test_safe_name():
    assert safe_name("sonidios de dios/Golpe ñandú?.wav") == "sonidios de diosGolpe nandu.wav"
    assert safe_name("   ") == "untitled"
    assert len(safe_name("x" * 100)) == 48


def test_unique_name():
    taken = set()
    assert [unique_name("Kick 01", taken) for _ in range(3)] == ["Kick 01", "Kick 01 2", "Kick 01 3"]
