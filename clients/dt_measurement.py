from pathlib import Path

def measure(audio_path, game):
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise FileNotFoundError(
            f'Audio file not found in {audio_path}'
            f'(Analysed absolute path: {audio_path.resolve()}, cwd: {Path.cwd()}).'
        )

    if game not in ('maimai', 'chunithm'):
        raise ValueError(
            f'{game} is invalid. The game must be either maimai or chunithm'
        )

    return 114.514
