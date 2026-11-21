from forcekit.layout import autofill, color_for, is_one_shot, kind
from forcekit.names import natural_key


def e(path, hint=None, duration=0.5, error=None, dup_of=None):
    return {"path": path, "type_hint": hint, "duration": duration, "error": error, "dup_of": dup_of}


def test_kind_hats():
    names = ["HH_OH_01.wav", "open hat.wav", "Hat Opn.wav", "ClosedHat.wav", "Shoe hat.wav"]
    assert [kind(e("x/" + n, "hat")) for n in names] == [
        "hat:open", "hat:open", "hat:open", "hat:closed", "hat:closed"]
    assert kind(e("808/OHH.wav", "hat")) == "hat:open" and kind(e("808/CHH.wav", "hat")) == "hat:closed"
    assert kind(e("x/b.wav", "bass")) == "any"
    assert kind(e("x/b.wav")) == "any"
    assert kind(e("x/k.wav", "kick")) == "kick"


def test_is_one_shot():
    assert not is_one_shot(e("a", "loop"))
    assert is_one_shot(e("a", duration=4.0))
    assert not is_one_shot(e("a", duration=4.01))
    assert is_one_shot(e("a", duration=None))


def test_color_for():
    assert color_for("kick") == 0xFF0000 and color_for("clap") == 0xFF4000
    assert color_for(None) == color_for("bass") == 0x3CFF5A


def test_autofill_layout():
    entries = [e("k/Kick 1.wav", "kick"), e("k/Kick 2.wav", "kick"), e("k/Kick 3.wav", "kick"),
               e("s/Snare.wav", "snare"), e("c/Clap.wav", "clap"),
               e("h/Closed HH.wav", "hat"), e("h/Open HH.wav", "hat")]
    assert autofill(entries) == {0: "k/Kick 1.wav", 1: "k/Kick 2.wav", 2: "s/Snare.wav", 3: "c/Clap.wav",
                                 4: "h/Closed HH.wav", 5: "h/Open HH.wav", 16: "k/Kick 3.wav"}


def test_autofill_fallbacks():
    entries = [e("s/Snare 1.wav", "snare"), e("s/Snare 2.wav", "snare"),
               e("m/a.wav"), e("m/b.wav", "bass"), e("m/c.wav")]
    assert autofill(entries) == {2: "s/Snare 1.wav", 3: "s/Snare 2.wav",
                                 13: "m/a.wav", 14: "m/b.wav", 15: "m/c.wav"}


def test_autofill_skips_broken_and_duplicates():
    entries = [e("k/bad.wav", "kick", error="boom"), e("k/dup.wav", "kick", dup_of="k/ok.wav"), e("k/ok.wav", "kick")]
    assert autofill(entries) == {0: "k/ok.wav"}


def test_autofill_caps_at_four_banks():
    entries = [e(f"k/Kick {i}.wav", "kick") for i in range(1, 11)]
    assert sorted(autofill(entries)) == [0, 1, 16, 17, 32, 33, 48, 49]
    assert autofill(entries)[1] == "k/Kick 2.wav"  # natural order, not "Kick 10"


def test_natural_key():
    assert sorted(["Kick 10", "Kick 2"], key=natural_key) == ["Kick 2", "Kick 10"]


def test_kind_hat_variants():
    opens = ["x/OH01.wav", "x/HH_OH01.wav", "x/Hat_Open1.wav", "x/HHOpen.wav", "x/OHH1.wav",
             "x/HiHat Opened.wav", "Open Hats/Hat 01.wav"]
    closes = ["x/CH01.wav", "x/HH 01.wav", "Open Hats/Closed Hat 1.wav", "x/Shoe hat.wav"]
    assert [kind(e(p, "hat")) for p in opens] == ["hat:open"] * len(opens)
    assert [kind(e(p, "hat")) for p in closes] == ["hat:closed"] * len(closes)


def test_every_type_has_its_own_color():
    from forcekit.layout import TYPE_COLORS
    assert set(TYPE_COLORS) == {"kick", "snare", "clap", "hat", "cymbal", "tom", "perc", "fx", "vocal"}
    assert color_for("hat") == 0x1AD8FF and color_for("cymbal") == 0x3A6BFF
