This patch adds `audio.py` and instructions for integrating it into your project.

1) Create file `audio.py` at project root with the contents described in the earlier assistant message.

2) Edit `main.py`:
- Add near other imports:

    import audio

- After your game initialization (after pygame.init() / window setup) add:

    audio.init_audio()
    audio.play_bgm()

If you want the BGM to start as soon as `main.py` runs and you're OK with initializing mixer early, you can add the two lines at the top inside a try/except.

3) Edit `enemy.py` (where a guard becomes alerted):
- When the guard transitions to an alerted state (e.g., `self.alerted = True`), add:

    try:
        import audio
        audio.play_sfx('alert_guard')
    except Exception:
        pass

4) Update `requirements.txt` to include:

    pygame>=2.0

5) Testing:

- Install dependencies:

    pip install -r requirements.txt

- Run the game:

    python main.py

- Confirm BGM plays on start and SFX plays when a guard is alerted.

Notes:
- The audio loader uses filename heuristics: it looks for filenames containing "solo" and "bgm"/"music" for BGM, and files containing both "alert" and "guard" for the alert SFX. Rename your sound files if needed.
- If you prefer hard-coded paths, replace the discovery logic in `init_audio()` with explicit assignments to `_bgm_path` and `_sfx['alert_guard']` (use raw Windows paths or project-relative paths).