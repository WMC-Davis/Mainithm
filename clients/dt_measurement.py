import sounddevice as sd
import librosa


SAMPLE_RATE = 44100
RECORD_DURATION = 10  # seconds


def record_loopback(duration=RECORD_DURATION, sr=SAMPLE_RATE, device=None):
    """Record audio from the Stereo Mix device (system audio output)."""
    if device is None:
        device = find_stereo_mix_device()
    print(f"Recording {duration}s from device: {device}")
    audio = sd.rec(
        int(duration * sr),
        samplerate=sr,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()
    return audio.flatten()


def find_stereo_mix_device():
    """Find the Stereo Mix (立体声混音) device for recording system audio output."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            name_lower = dev["name"].lower()
            if "stereo mix" in name_lower or "立体声混音" in name_lower:
                return i

    raise RuntimeError(
        "No Stereo Mix device found. "
        "Enable it in: Sound Settings -> Recording -> right-click -> Show Disabled Devices -> Enable Stereo Mix"
    )


def detect_onsets(audio, sr=SAMPLE_RATE):
    """Detect onset times in the audio signal."""
    onset_env = librosa.onset.onset_strength(y=audio, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        y=audio, sr=sr, onset_envelope=onset_env, backtrack=False
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    return onset_times


def measure_dt(audio=None, sr=SAMPLE_RATE, duration=RECORD_DURATION, device=None):
    """Record (or accept) audio, detect onsets, return time between 1st and 6th peak."""
    if audio is None:
        audio = record_loopback(duration=duration, sr=sr, device=device)

    onset_times = detect_onsets(audio, sr=sr)
    print(f"Detected {len(onset_times)} onsets: {onset_times[:8]}")

    if len(onset_times) < 6:
        raise ValueError(
            f"Need at least 6 onsets but only detected {len(onset_times)}. "
            "Check audio input or adjust detection parameters."
        )

    dt = onset_times[5] - onset_times[0]
    print(f"dt (peak1 -> peak6) = {dt:.4f}s = {dt * 1000:.1f}ms")
    return dt


if __name__ == "__main__":
    dt = measure_dt()
    print(f"\nResult: {dt * 1000:.1f} ms")
