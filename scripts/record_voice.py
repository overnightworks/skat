# ruff: noqa: T201 - this script's job is to report each recording it makes
"""Record the voice: one recording per voice catalog key and language, shipped under frontend/src/lib/voice.

The fleet's speech service speaks each text in Qwen3-TTS's `ryan`; ffmpeg trims the silence around it, levels it and
writes a compact MP3, the format every browser's Web Audio decodes. The table never calls the service at play time.
Run a local speech service (its README says how) and give this script its address and the two tokens it asks for:

    SPEECH_URL=http://127.0.0.1:8080 SPEECH_WORKLOAD_TOKEN=... SPEECH_PERSON_TOKEN=... make voice

A recording that exists is kept; `--again` records every key anew.
"""

import argparse
import json
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
RECORDING_SUFFIX: Final = ".mp3"
SPEECH_PATH: Final = "/v1/audio/speech"
SPEECH_MODEL: Final = "qwen3-tts-1.7b"
SPEECH_VOICE: Final = "ryan"
SPEECH_FORMAT: Final = "wav"
SPEECH_TIMEOUT_SECONDS: Final = 120
SERVICE_VARIABLE: Final = "SPEECH_URL"
WORKLOAD_TOKEN_VARIABLE: Final = "SPEECH_WORKLOAD_TOKEN"  # noqa: S105 - the name of the variable, not a secret
PERSON_TOKEN_VARIABLE: Final = "SPEECH_PERSON_TOKEN"  # noqa: S105 - the name of the variable, not a secret
# Trims the silence on both ends (the second pair works on the reversed audio), then levels the recording.
FILTER: Final = (
    "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
    "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
    "loudnorm=I=-20:TP=-2:LRA=7"
)
ENCODER_ARGUMENTS: Final = ("-ac", "1", "-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "48k")


@dataclass(frozen=True)
class SpokenLine:
    language: Language
    key: Key
    text: str

    @property
    def path(self) -> Path:
        return RECORDINGS_DIRECTORY / self.language / f"{self.key}{RECORDING_SUFFIX}"


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
    with urllib.request.urlopen(speech_request(service, line), timeout=SPEECH_TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read()


def encode(wav: bytes) -> bytes:
    """The WAV trimmed, levelled and written as a compact MP3."""
    done = subprocess.run(  # noqa: S603 - fixed arguments, the audio goes through the pipe
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-af", FILTER, *ENCODER_ARGUMENTS, "-f", "mp3", "pipe:1"],  # noqa: S607
        input=wav,
        capture_output=True,
        check=True,
    )
    return done.stdout


def record(
    lines: Sequence[SpokenLine],
    *,
    again: bool,
    speak_line: Callable[[SpokenLine], bytes],
    encode_wav: Callable[[bytes], bytes] = encode,
) -> int:
    """Records each line whose file is missing (or every line with `again`) and returns how many it made."""
    made = 0
    for line in lines:
        if line.path.exists() and not again:
            continue
        line.path.parent.mkdir(parents=True, exist_ok=True)
        line.path.write_bytes(encode_wav(speak_line(line)))
        made += 1
        print(f"{line.language} {line.key}: {line.text}")
    return made


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
    parsed = parser.parse_args(arguments)
    service = service_from(environment)
    made = record(spoken_lines(), again=parsed.again, speak_line=lambda line: speak(service, line))
    print(f"{made} recordings made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], dict(os.environ)))
