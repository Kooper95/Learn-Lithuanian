LITHUANIAN LESSONS 11-27  -  BUILDING THE AUDIO
================================================

What you have
  Lesson_11.txt ... Lesson_27.txt   the transcripts (three voices + timed pauses)
  build_audio.py                    turns each transcript into one MP3

The voices are Microsoft's free neural voices (the ones built into the Edge browser):
  Narrator  en-AU-WilliamNeural   Australian English, male
  MALE      lt-LT-LeonasNeural    Lithuanian, male
  FEMALE    lt-LT-OnaNeural       Lithuanian, female
No account or API key is needed.

ONE-TIME SETUP (about 5 minutes)
  1. Install Python 3 if you don't have it:  https://www.python.org/downloads/
     (Windows: tick "Add Python to PATH" in the installer.)
  2. Install ffmpeg (joins the clips and writes the MP3):
       Windows:  open PowerShell and run    winget install ffmpeg
       macOS:    open Terminal and run      brew install ffmpeg
     Then close and reopen the terminal.
  3. In the terminal, in this folder, run:
       pip install edge-tts pydub

BUILD A LESSON
  python build_audio.py Lesson_11.txt
  -> Lesson_11.mp3 (about 30 minutes) appears next to it. Allow 3-6 minutes per lesson:
     each lesson is ~350 short clips, fetched 4 at a time.

  All lessons at once:   python build_audio.py Lesson_1*.txt
  Clips are cached in tts_cache/, so rebuilding after a wording change only fetches what changed.

OPTIONS
  --dry-run                     show what would be spoken, fetch nothing
  --word-check                  build Lesson_NN_words.mp3 (2-3 min): every distinct Lithuanian
                                sentence once, so you can audit the pronunciation before a full build
  --build-up word               read each syllable build-up (tas, rytas) as the whole word, slowly,
                                instead of the fragments (see PRONUNCIATION below)
  --concurrency 1               fetch one clip at a time if the service keeps refusing (slower, safer)
  --narrator en-AU-NatashaNeural   female Australian narrator (any Edge voice name works;
                                   list them with:  edge-tts --list-voices)
  --lt-rate -20%                slow the Lithuanian down more (default -12%; -0% = native speed)

HOW THE TRANSCRIPT IS READ
  NARRATOR: ...     English narrator. Lithuanian words inside "quotes" in a narrator line are
                    spoken by the Lithuanian voice that spoke last, so "Labas rytas" in an
                    English sentence is still pronounced by a Lithuanian voice.
  MALE: / FEMALE:   Lithuanian voices, 12% slower than native speed. One- or two-syllable
                    build-up fragments (tas, rytas) are read 25% slower.
  [PAUSE 5]         five seconds of silence for you to answer.
  [SECTION: ...]    labels only; never spoken.

PRONUNCIATION: WHAT TO TRUST
  Leonas and Ona are trained on real Lithuanian speech and place the stress of ordinary words
  (vardas, atsiprašau, dėstytoja) correctly; the full sentences in the lessons are reliable models.
  The one place a machine voice can mislead is the backward build-up: a fragment like "lonu" or
  "tuvis" is not a word, so the voice has to guess its stress. To check this on your system:
    1. python build_audio.py Lesson_11.txt --word-check   -> listen to Lesson_11_words.mp3 (2 min)
    2. python build_audio.py Lesson_11.txt                -> listen to the "Good morning" section
  If the fragments sound unlike the full word, rebuild with  --build-up word : the build-up steps
  then repeat the whole word slowly instead, which keeps the rhythm of the drill with no risk of a
  wrong stress. The stressed syllables are also marked in CAPITALS in the lesson plan, so you can
  always check your ear against the plan.

EXPRESSION TAGS (Lessons 19 onwards)
  Lessons 19 and 27 are practice lessons with no new words.
  A line may start with a tag such as  FEMALE: (cheerful) Puikiai!  The tags are: cheerful, excited,
  warm, surprised, curious, apologetic, calm, slow, firm. build_audio.py turns each into a small
  change of pitch and speed (the only expressive controls these voices offer), so a cheerful
  "Puikiai!" is brighter and quicker, an apologetic "Atsiprašau" lower and slower. They never
  change the words. Lessons 11-18 have no tags; you can add them by hand if you like.

IF SOMETHING GOES WRONG
  "No audio was received"     -> the speech service throttled you after a burst of requests. The
                                 script now spaces requests out and retries each clip up to six
                                 times with increasing waits, then finishes the MP3 with 1 s of
                                 silence for anything still missing and lists it in failed_clips.txt.
                                 Wait a few minutes and run the same command again: only the missing
                                 clips are fetched. Still failing? add  --concurrency 1
  "No module named edge_tts"  -> run  pip install edge-tts pydub  again (try  pip3  or  py -m pip)
  "ffmpeg not found"          -> step 2 above; reopen the terminal afterwards
  Network errors mid-build    -> just run the same command again; finished clips are cached
  A word sounds wrong         -> edit the .txt (e.g. add a hyphen: "at-si-pra-šau") and rebuild;
                                 only that clip is re-fetched

ALTERNATIVE VOICES (optional, paid)
  If you later want more natural voices, Narakeet (narakeet.com) accepts a script with
  (voice: name) and (pause: n) directions and has Lithuanian voices Arvydas (m), Jurga and
  Vaida (f); ElevenLabs has an API with Lithuanian in its multilingual model. Either would need
  this script adapted to its API; the free Microsoft voices are a good place to start, and
  Leonas and Ona are the same voices many paid Lithuanian TTS sites resell.
