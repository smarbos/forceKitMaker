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


def test_safe_name_never_yields_dot_names():
    from forcekit.names import safe_name
    assert safe_name("..") == "untitled" and safe_name(".") == "untitled"
    assert safe_name(".hidden kit") == "hidden kit"


def test_auto_names_strip_shared_words():
    from forcekit.names import auto_names
    pads = {0: "p/DRUMBOII_KICK_808.wav", 1: "p/DRUMBOII_SNARE_BASIC.wav", 2: "p/DRUMBOII_HAT_OPEN.wav"}
    assert auto_names(pads) == {0: "KICK 808", 1: "SNARE BASIC", 2: "HAT OPEN"}


def test_auto_names_suffix_and_keep_one_word():
    from forcekit.names import auto_names
    assert auto_names({0: "a/Kick-Pack.wav", 1: "a/Snare-Pack.wav"}) == {0: "Kick", 1: "Snare"}
    # everything shared except nothing: each keeps at least one word
    assert auto_names({0: "a/Pack Kick.wav", 1: "b/Pack Kick.wav", 2: "c/Pack.wav"}) == {
        0: "Pack Kick", 1: "Pack Kick", 2: "Pack"}


def test_auto_names_nothing_shared_or_single():
    from forcekit.names import auto_names
    assert auto_names({0: "v/voice_badboy.wav", 1: "v/lovely.wav"}) == {0: "voice badboy", 1: "lovely"}
    assert auto_names({5: "x/DRUMBOII_KICK_808.wav"}) == {5: "DRUMBOII KICK 808"}
    assert auto_names({}) == {}


def test_auto_names_match_what_the_force_gets():
    from forcekit.names import auto_names
    assert auto_names({0: "p/X_CRASH_RIDE\uf025.wav", 1: "p/X_Kick.wav"}) == {0: "CRASH RIDE", 1: "Kick"}
