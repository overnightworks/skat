"""Tests for the script that records the voice from the speech service."""

import http.client
import json
import math
from typing import TYPE_CHECKING

import pytest

from scripts import record_voice
from skat.engine.bidding import VALID_BIDS
from skat.engine.kontra import Word
from skat.web.words import LANGUAGES

if TYPE_CHECKING:
    from pathlib import Path

SERVICE = record_voice.Service("http://127.0.0.1:9/", "workload-token", "person-token")


def lines_of(language: str) -> list[record_voice.SpokenLine]:
    return [line for line in record_voice.spoken_lines() if line.language == language]


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_speaks_a_pass_each_word_of_kontra_and_each_valid_bid(language: str) -> None:
    keys = {line.key for line in lines_of(language)}

    expected = {"voice.pass", *(f"voice.{word.value}" for word in Word), *(f"voice.value{bid}" for bid in VALID_BIDS)}
    assert keys == expected


def test_a_recording_lies_in_the_directory_of_its_language_under_its_key(tmp_path: Path) -> None:
    line = record_voice.SpokenLine("de", "voice.kontra", "Kontra")

    assert line.path_in(tmp_path).relative_to(tmp_path).as_posix() == "de/voice.kontra.mp3"


def test_the_request_asks_ryan_for_the_text_in_its_language_with_both_tokens() -> None:
    request = record_voice.speech_request(SERVICE, record_voice.SpokenLine("en", "voice.value18", "eighteen"))

    assert request.full_url == "http://127.0.0.1:9/v1/audio/speech"
    assert isinstance(request.data, bytes)
    assert json.loads(request.data) == {
        "model": "qwen3-tts-1.7b",
        "input": "eighteen",
        "voice": "ryan",
        "language": "en",
        "response_format": "wav",
    }
    assert request.get_header("Speech-workload-token") == "workload-token"
    assert request.get_header("Authorization") == "Bearer person-token"


def test_a_run_records_the_missing_keys_and_keeps_the_ones_it_has(tmp_path: Path) -> None:
    lines = lines_of("de")[:3]
    lines[0].path_in(tmp_path).parent.mkdir(parents=True)
    lines[0].path_in(tmp_path).write_bytes(b"kept")
    spoken: list[str] = []

    def speak(line: record_voice.SpokenLine) -> bytes:
        spoken.append(line.key)
        return line.text.encode()

    made = record_voice.record(lines, tmp_path, again=False, speak_line=speak, encode_wav=lambda wav: b"mp3:" + wav)

    assert made == len(lines) - 1
    assert spoken == [line.key for line in lines[1:]]
    assert lines[0].path_in(tmp_path).read_bytes() == b"kept"
    assert lines[1].path_in(tmp_path).read_bytes() == b"mp3:" + lines[1].text.encode()


def test_a_run_with_again_records_every_key_anew(tmp_path: Path) -> None:
    lines = lines_of("de")[:2]
    lines[0].path_in(tmp_path).parent.mkdir(parents=True)
    lines[0].path_in(tmp_path).write_bytes(b"old")

    made = record_voice.record(lines, tmp_path, again=True, speak_line=lambda _: b"new", encode_wav=lambda wav: wav)

    assert made == len(lines)
    assert lines[0].path_in(tmp_path).read_bytes() == b"new"


def test_a_recording_that_runs_on_past_its_text_is_made_again(tmp_path: Path) -> None:
    line = record_voice.SpokenLine("de", "voice.kontra", "Kontra")
    seconds = [20.0, 1.0]
    bytes_per_second = record_voice.MP3_BITS_PER_SECOND // record_voice.BITS_PER_BYTE

    def speak(_: record_voice.SpokenLine) -> bytes:
        return b"x" * round(seconds.pop(0) * bytes_per_second)

    made = record_voice.record([line], tmp_path, again=False, speak_line=speak, encode_wav=lambda wav: wav)

    assert made == 1
    assert len(line.path_in(tmp_path).read_bytes()) == bytes_per_second


def test_a_recording_the_service_cut_off_is_made_again(tmp_path: Path) -> None:
    line = record_voice.SpokenLine("de", "voice.kontra", "Kontra")
    answers: list[bytes | Exception] = [http.client.IncompleteRead(b""), TimeoutError(), b"mp3"]

    def speak(_: record_voice.SpokenLine) -> bytes:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    record_voice.record([line], tmp_path, again=False, speak_line=speak, encode_wav=lambda wav: wav)

    assert line.path_in(tmp_path).read_bytes() == b"mp3"


def test_a_line_that_always_runs_on_stops_the_run_and_keeps_no_file(tmp_path: Path) -> None:
    line = record_voice.SpokenLine("de", "voice.kontra", "Kontra")
    runaway = b"x" * (20 * record_voice.MP3_BITS_PER_SECOND // record_voice.BITS_PER_BYTE)

    with pytest.raises(SystemExit, match=r"voice\.kontra"):
        record_voice.record([line], tmp_path, again=False, speak_line=lambda _: runaway, encode_wav=lambda wav: wav)

    assert not line.path_in(tmp_path).exists()


def test_the_service_and_both_tokens_come_from_the_environment() -> None:
    environment = {
        "SPEECH_URL": "http://127.0.0.1:9",
        "SPEECH_WORKLOAD_TOKEN": "workload-token",
        "SPEECH_PERSON_TOKEN": "person-token",
    }

    assert record_voice.service_from(environment) == record_voice.Service(
        "http://127.0.0.1:9", "workload-token", "person-token"
    )


def test_a_missing_setting_is_named_and_stops_the_run() -> None:
    with pytest.raises(SystemExit, match="SPEECH_PERSON_TOKEN"):
        record_voice.service_from({"SPEECH_URL": "http://127.0.0.1:9", "SPEECH_WORKLOAD_TOKEN": "x"})


def test_a_run_without_its_settings_records_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        record_voice.main([], {})

    assert capsys.readouterr().out == ""


def sine(amplitude: float, hertz: float, seconds: float = 0.5) -> list[float]:
    rate = record_voice.SAMPLE_RATE
    return [amplitude * math.sin(2 * math.pi * hertz * index / rate) for index in range(round(seconds * rate))]


def test_a_tone_in_the_speaker_s_range_measures_its_mean_power() -> None:
    amplitude = 0.1

    measured = record_voice.loudness_decibels(sine(amplitude, 1000))

    assert measured == pytest.approx(20 * math.log10(amplitude / math.sqrt(2)), abs=0.1)


def test_a_tone_below_the_speaker_s_cutoff_measures_far_quieter() -> None:
    assert record_voice.loudness_decibels(sine(0.1, 50)) < record_voice.loudness_decibels(sine(0.1, 1000)) - 20


def test_a_word_is_measured_by_its_loudest_window_not_by_its_silence() -> None:
    silence = [0.0] * record_voice.SAMPLE_RATE

    assert record_voice.loudness_decibels([*silence, *sine(0.1, 1000), *silence]) == pytest.approx(
        record_voice.loudness_decibels(sine(0.1, 1000)), abs=0.5
    )


def test_a_level_run_gives_each_recording_the_gain_that_brings_it_to_the_target(tmp_path: Path) -> None:
    lines = lines_of("de")[:2]
    for line in lines:
        line.path_in(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        line.path_in(tmp_path).write_bytes(line.text.encode())
    gains: list[bytes] = []

    def level(recording: bytes) -> bytes:
        gains.append(recording)
        return b"levelled:" + recording

    made = record_voice.level_recordings(lines, tmp_path, level_recording=level)

    assert made == len(lines)
    assert gains == [line.text.encode() for line in lines]
    assert lines[0].path_in(tmp_path).read_bytes() == b"levelled:" + lines[0].text.encode()
