// Stands in for Web Audio in every browser context: nothing sounds, the clock stays at 0, and every voice
// the page starts is appended to window.voicesStarted as { kind, start, gain } for the test to read.
(() => {
    const voicesStarted = [];
    window.voicesStarted = voicesStarted;

    class Param {
        value = 0;
        peak = undefined;

        setValueAtTime(value) {
            this.value = value;
        }

        exponentialRampToValueAtTime(value) {
            this.peak ??= value;
        }
    }

    class Node {
        gain = new Param();
        frequency = new Param();
        Q = new Param();
        threshold = new Param();
        ratio = new Param();
        next = undefined;

        connect(next) {
            this.next = next;
            return next;
        }

        // The voice's level is the first rise of the gain node it flows through.
        level() {
            for (let node = this.next; node; node = node.next) if (node.gain.peak !== undefined) return node.gain.peak;
            return undefined;
        }

        stop() {}
    }

    class Oscillator extends Node {
        start(at) {
            voicesStarted.push({ kind: "tone", start: at, gain: this.level() });
        }
    }

    class BufferSource extends Node {
        buffer = undefined;

        // The one-sample buffer that wakes iOS is no voice.
        start(at = 0) {
            if (this.buffer.length > 1) voicesStarted.push({ kind: "noise", start: at, gain: this.level() });
        }
    }

    class RecordingAudioContext {
        state = "suspended";
        currentTime = 0;
        sampleRate = 8000;
        destination = new Node();

        resume() {
            this.state = "running";
            return Promise.resolve();
        }

        createGain() {
            return new Node();
        }

        createDynamicsCompressor() {
            return new Node();
        }

        createBiquadFilter() {
            return new Node();
        }

        createOscillator() {
            return new Oscillator();
        }

        createBufferSource() {
            return new BufferSource();
        }

        createBuffer(_channels, length) {
            const samples = new Float32Array(length);
            return { length, getChannelData: () => samples };
        }
    }

    window.AudioContext = RecordingAudioContext;
})();
