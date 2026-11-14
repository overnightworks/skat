# ruff: noqa: T201 - this script's job is to report each recording it makes
"""Record the voice: one recording per voice catalog key and language, shipped under frontend/src/lib/voice.

The fleet's speech service speaks each text in Qwen3-TTS's `ryan`; ffmpeg trims the silence around it, this script
brings it to the loudness in `level.json` (the loudness the sound sets are held to, measured as a phone's speaker plays
it) and ffmpeg writes a compact MP3, the format every browser's Web Audio decodes. The table never calls the service at play time.
Run a local speech service (its README says how) and give this script its address and the two tokens it asks for:

    SPEECH_URL=http://127.0.0.1:8080 SPEECH_WORKLOAD_TOKEN=... SPEECH_PERSON_TOKEN=... make voice

A recording that exists is kept; `--again` records every key anew; `--level` brings the recordings that exist to the
target again, which needs no speech service and re-encodes each file once.
"""

import argparse
import array
import http.client
import json
import math
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "src"))

from skat.web.words import LANGUAGES, WORDS  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from skat.web.words import Key, Language

VOICE_KEY_PREFIX: Final = "voice."
RECORDINGS_DIRECTORY: Final = REPOSITORY / "frontend" / "src" / "lib" / "voice"
LEVEL_FILE: Final = RECORDINGS_DIRECTORY / "level.json"
RECORDING_SUFFIX: Final = ".mp3"
SPEECH_PATH: Final = "/v1/audio/speech"
SPEECH_MODEL: Final = "qwen3-tts-1.7b"
SPEECH_VOICE: Final = "ryan"
SPEECH_FORMAT: Final = "wav"
SPEECH_TIMEOUT_SECONDS: Final = 60
SERVICE_VARIABLE: Final = "SPEECH_URL"
WORKLOAD_TOKEN_VARIABLE: Final = "SPEECH_WORKLOAD_TOKEN"  # noqa: S105 - the name of an environment variable and no secret
PERSON_TOKEN_VARIABLE: Final = "SPEECH_PERSON_TOKEN"  # noqa: S105 - the name of an environment variable and no secret
# Trims the silence on both ends; the second pair works on the reversed audio.
TRIM_FILTER: Final = (
    "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
    "silenceremove=start_periods=1:start_threshold=-50dB,areverse"
)
# The loudness of a recording is measured as the sound sets' loudness test measures a set: the mean power of the loudest
# 200 ms after a second-order Butterworth high-pass at the cutoff below which a phone's speaker plays nothing.
SAMPLE_RATE: Final = 48_000
LEVEL_WINDOW_SECONDS: Final = 0.2
SPEAKER_CUTOFF_HERTZ: Final = 200
SILENCE_POWER: Final = 1e-12
MP3_BITS_PER_SECOND: Final = 48_000
ENCODER_ARGUMENTS: Final = ("-ac", "1", "-ar", "44100", "-codec:a", "libmp3lame", "-b:a", f"{MP3_BITS_PER_SECOND}")
# The model now and then runs on past its text for seconds; a spoken line is about 0.1 s a letter after the silence is
# trimmed, so a recording past this many seconds per letter, and a second more, is made again.
SECONDS_PER_LETTER_LIMIT: Final = 0.15
SECONDS_LIMIT_BASE: Final = 1.5
ATTEMPTS: Final = 5
BITS_PER_BYTE: Final = 8


@dataclass(frozen=True)
class SpokenLine:
    language: Language
    key: Key
    text: str

    def path_in(self, directory: Path) -> Path:
        return directory / self.language / f"{self.key}{RECORDING_SUFFIX}"


@dataclass(frozen=True)
class Service:
    url: str
    workload_token: str
    person_token: str


def spoken_lines(languages: Sequence[Language] = LANGUAGES) -> list[SpokenLine]:
    """The text of every voice key in each language, in catalog order."""
    return [
        SpokenLine(language, key, text)
        for language in languages
        for key, text in WORDS[language].items()
        if key.startswith(VOICE_KEY_PREFIX) and isinstance(text, str)
    ]


def speech_request(service: Service, line: SpokenLine) -> urllib.request.Request:
    body = {
        "model": SPEECH_MODEL,
        "input": line.text,
        "voice": SPEECH_VOICE,
        "language": line.language,
        "response_format": SPEECH_FORMAT,
    }
    return urllib.request.Request(  # noqa: S310 - the operator names the service's http address
        f"{service.url.rstrip('/')}{SPEECH_PATH}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Speech-Workload-Token": service.workload_token,
            "Authorization": f"Bearer {service.person_token}",
        },
        method="POST",
    )


def speak(service: Service, line: SpokenLine) -> bytes:
    """The service's recording of one line, as WAV."""
    with urllib.request.urlopen(speech_request(service, line), timeout=SPEECH_TIMEOUT_SECONDS) as response:  # noqa: S310 - the service address is the operator's own setting
        return response.read()


def ffmpeg(audio: bytes, *arguments: str) -> bytes:
    """What ffmpeg writes for the audio given on its input."""
    done = subprocess.run(  # noqa: S603 - fixed arguments and the audio goes through the pipe
        ["ffmpeg", "-v", "error", "-i", "pipe:0", *arguments, "pipe:1"],  # noqa: S607 - ffmpeg is looked up on the operator's path
        input=audio,
        capture_output=True,
        check=True,
    )
    return done.stdout


def target_decibels() -> float:
    """The loudness the voice is brought to, which the sound sets' loudness test holds the sets to."""
    return float(json.loads(LEVEL_FILE.read_text())["decibels"])


def loudness_decibels(samples: Sequence[float]) -> float:
    """The mean power in decibels of the loudest 200 ms, as a phone's speaker plays it."""
    omega = 2 * math.pi * SPEAKER_CUTOFF_HERTZ / SAMPLE_RATE
    alpha = math.sin(omega) / math.sqrt(2)
    scale = 1 + alpha
    forward = (1 + math.cos(omega)) / 2 / scale
    back_one = -2 * math.cos(omega) / scale
    back_two = (1 - alpha) / scale
    window = round(LEVEL_WINDOW_SECONDS * SAMPLE_RATE)
    previous_in = older_in = previous_out = older_out = 0.0
    powers: list[float] = []
    for sample in samples:
        out = forward * (sample - 2 * previous_in + older_in) - back_one * previous_out - back_two * older_out
        older_in, previous_in, older_out, previous_out = previous_in, sample, previous_out, out
        powers.append(out * out)
    energy = loudest = 0.0
    for index, power in enumerate(powers):
        energy += power - (powers[index - window] if index >= window else 0.0)
        loudest = max(loudest, energy / window)
    return 10 * math.log10(max(loudest, SILENCE_POWER))


def decoded(audio: bytes) -> list[float]:
    """The samples of a recording at the rate the measure uses, as one channel."""
    raw = ffmpeg(audio, "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE))
    samples = array.array("f")
    samples.frombytes(raw)
    return list(samples)


def leveled(audio: bytes) -> bytes:
    """The recording written as a compact MP3 at the gain that brings its loudness to the target."""
    gain = target_decibels() - loudness_decibels(decoded(audio))
    return ffmpeg(audio, "-af", f"volume={gain:.2f}dB", *ENCODER_ARGUMENTS, "-f", "mp3")


def encode(wav: bytes) -> bytes:
    """The WAV trimmed, levelled and written as a compact MP3."""
    return leveled(ffmpeg(wav, "-af", TRIM_FILTER, "-f", "wav"))


def seconds_of(recording: bytes) -> float:
    """The length of an MP3 this script encoded, which has a constant bit rate."""
    return len(recording) * BITS_PER_BYTE / MP3_BITS_PER_SECOND


def recording_of(
    line: SpokenLine, speak_line: Callable[[SpokenLine], bytes], encode_wav: Callable[[bytes], bytes]
) -> bytes:
    """A recording of the line that does not run on past its text, made again while it does."""
    longest = SECONDS_LIMIT_BASE + SECONDS_PER_LETTER_LIMIT * len(line.text)
    for _ in range(ATTEMPTS):
        try:
            recording = encode_wav(speak_line(line))
        except OSError, http.client.HTTPException:
            # A model that runs on is cut off by the service, which ends the answer or leaves it unfinished.
            continue
        if seconds_of(recording) <= longest:
            return recording
    message = f"record_voice: {line.language} {line.key} gave no recording within {longest:.1f} s in {ATTEMPTS} tries"
    raise SystemExit(message)


def record(
    lines: Sequence[SpokenLine],
    directory: Path,
    *,
    again: bool,
    speak_line: Callable[[SpokenLine], bytes],
    encode_wav: Callable[[bytes], bytes] = encode,
) -> int:
    """Records each line whose file is missing (or every line with `again`) and returns how many it made."""
    made = 0
    for line in lines:
        path = line.path_in(directory)
        if path.exists() and not again:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(recording_of(line, speak_line, encode_wav))
        made += 1
        print(f"{line.language} {line.key}: {line.text}")
    return made


def level_recordings(
    lines: Sequence[SpokenLine], directory: Path, *, level_recording: Callable[[bytes], bytes] = leveled
) -> int:
    """Brings each line's recording that exists to the target loudness and returns how many it changed."""
    changed = 0
    for line in lines:
        path = line.path_in(directory)
        if not path.exists():
            continue
        path.write_bytes(level_recording(path.read_bytes()))
        changed += 1
        print(f"{line.language} {line.key}: levelled")
    return changed


def service_from(environment: dict[str, str]) -> Service:
    missing = [
        name for name in (SERVICE_VARIABLE, WORKLOAD_TOKEN_VARIABLE, PERSON_TOKEN_VARIABLE) if not environment.get(name)
    ]
    if missing:
        raise SystemExit(f"record_voice: set {', '.join(missing)}")
    return Service(
        environment[SERVICE_VARIABLE], environment[WORKLOAD_TOKEN_VARIABLE], environment[PERSON_TOKEN_VARIABLE]
    )


def main(arguments: Sequence[str], environment: dict[str, str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--again", action="store_true", help="record every key anew, not only the missing ones")
    parser.add_argument("--level", action="store_true", help="bring the recordings that exist to the target loudness")
    parsed = parser.parse_args(arguments)
    if parsed.level:
        print(f"{level_recordings(spoken_lines(), RECORDINGS_DIRECTORY)} recordings levelled")
        return 0
    service = service_from(environment)
    made = record(
        spoken_lines(), RECORDINGS_DIRECTORY, again=parsed.again, speak_line=lambda line: speak(service, line)
    )
    print(f"{made} recordings made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], dict(os.environ)))
