#!/usr/bin/env python3
"""
Build a Lithuanian lesson transcript (Lesson_NN.txt) into one MP3.

Voices come from Microsoft's free neural text-to-speech (via the edge-tts package):
  NARRATOR  en-AU-WilliamNeural   (English)
  MALE      lt-LT-LeonasNeural    (Lithuanian)
  FEMALE    lt-LT-OnaNeural       (Lithuanian)

Usage
  python build_audio.py Lesson_11.txt                 # builds Lesson_11.mp3
  python build_audio.py Lesson_1*.txt                 # all lessons
  python build_audio.py Lesson_11.txt --dry-run       # show the plan, synthesise nothing
  python build_audio.py Lesson_11.txt --narrator en-AU-NatashaNeural --lt-rate -20%

Requirements (one-off):
  pip install edge-tts pydub
  ffmpeg on your PATH  (Windows: winget install ffmpeg | macOS: brew install ffmpeg)
"""
import argparse, asyncio, hashlib, pathlib, re, sys

# ---------------------------------------------------------------- settings
VOICES = {"NARRATOR": "en-AU-WilliamNeural", "MALE": "lt-LT-LeonasNeural", "FEMALE": "lt-LT-OnaNeural"}
NARR_RATE = "+0%"       # English narrator
LT_RATE = "-5%"        # Lithuanian sentences: a little slower than native speed, for learners
FRAG_RATE = "-10%"      # build-up fragments (one or two syllables) slower still
GAP_AFTER_LINE_MS = 450 # short natural gap after every spoken line
CONCURRENCY = 1         # parallel requests to the speech service (higher values get throttled)
PACE_S = 0.4            # minimum spacing between requests, seconds
# English words that also happen to look like Lithuanian tokens; never voice these in Lithuanian
ENGLISH_BLOCKLIST = {"no", "a", "i", "o", "is", "me", "man", "in", "it", "at", "to", "on", "we"}

# Expression tags at the start of a line, e.g.  FEMALE: (cheerful) Puikiai!
# Mapped to pitch / speed changes of the neural voice (the only expressive controls it offers).
STYLES = {  # name: (pitch, rate adjustment in percentage points)
    "cheerful": ("+6Hz", 6), "excited": ("+10Hz", 10), "warm": ("+2Hz", -4), "surprised": ("+12Hz", 4),
    "curious": ("+5Hz", 0), "apologetic": ("-4Hz", -8), "calm": ("-2Hz", -6), "slow": ("+0Hz", -15),
    "firm": ("-3Hz", 0),
}
STYLE_RE = re.compile(r"^\((" + "|".join(STYLES) + r")\)\s*")

def split_style(text):
    m = STYLE_RE.match(text)
    return (m.group(1), text[m.end():]) if m else (None, text)

def adjust_rate(rate, delta):
    return f"{int(rate.rstrip('%')) + delta:+d}%"

# ---------------------------------------------------------------- parsing
LINE_RE = re.compile(r"^(NARRATOR|MALE|FEMALE): (.*)$")
PAUSE_RE = re.compile(r"^\[PAUSE (\d+)\]$")
QUOTE_RE = re.compile(r"[\"“]([^\"”]+)[\"”]")

def tokens(s):
    return [t for t in re.sub(r"[.,!?;:…–—\"“”'()\[\]]", " ", s.lower()).split() if t]

def parse(path):
    """Return a list of events: ('say', voice, text, rate) or ('pause', ms)."""
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("[SECTION:"))
    except StopIteration:
        start = 0
    body = lines[start:]

    # every token the Lithuanian voices say in this lesson = this lesson's Lithuanian word set
    lt_words = set()
    for l in body:
        m = LINE_RE.match(l)
        if m and m.group(1) in ("MALE", "FEMALE"):
            lt_words.update(tokens(m.group(2)))
    lt_words -= ENGLISH_BLOCKLIST

    events, last_lt_voice = [], "FEMALE"
    for l in body:
        l = l.rstrip()
        if not l or l.startswith("[SECTION:"):
            continue
        m = PAUSE_RE.match(l)
        if m:
            events.append(("pause", int(m.group(1)) * 1000)); continue
        m = LINE_RE.match(l)
        if not m:
            print(f"  ? skipped unparsed line: {l}", file=sys.stderr); continue
        voice, text = m.groups()
        style, text = split_style(text)
        pitch, delta = STYLES[style] if style else ("+0Hz", 0)
        if voice in ("MALE", "FEMALE"):
            last_lt_voice = voice
            rate = FRAG_RATE if len(tokens(text)) <= 2 and not re.search(r"[.!?]$", text) else LT_RATE
            events.append(("say", voice, text, adjust_rate(rate, delta), pitch))
            continue
        # narrator: speak quoted Lithuanian with a Lithuanian voice, the rest in English
        pos = 0
        for q in QUOTE_RE.finditer(text):
            inner = q.group(1)
            toks = tokens(inner)
            if toks and all(t in lt_words for t in toks):
                before = text[pos:q.start()].strip()
                if before:
                    events.append(("say", "NARRATOR", before, adjust_rate(NARR_RATE, delta), pitch))
                events.append(("say", last_lt_voice, inner.strip(), LT_RATE, "+0Hz"))
                pos = q.end()
        rest = text[pos:].strip()
        if rest and rest[0] in ",;:":
            rest = rest[1:].strip()
        if rest:
            events.append(("say", "NARRATOR", rest, adjust_rate(NARR_RATE, delta), pitch))
    events.append(("pause", 1500))
    return events

def fragments_to_words(events):
    """Replace each backward build-up chain (tas, rytas, labas rytas) by its final full word, read slowly."""
    out = list(events)
    def next_say(k):
        k += 1
        while k < len(out) and out[k][0] == "pause":
            k += 1
        return k if k < len(out) else None
    i = 0
    while i < len(out):
        e = out[i]
        if e[0] == "say" and e[3] == FRAG_RATE:
            chain, j = [i], i
            while True:
                n = next_say(j)
                if n is None: break
                f = out[n]
                if f[0] == "say" and f[1] == e[1] and f[3] == FRAG_RATE and out[j][2].lower().strip(".") in f[2].lower():
                    chain.append(n); j = n
                else:
                    break
            full = out[j][2]
            for k in chain:
                out[k] = ("say", e[1], full, FRAG_RATE, "+0Hz")
            i = j + 1
        else:
            i += 1
    return out

def word_check_events(events):
    """Every distinct Lithuanian sentence, once, with a short pause after each: for auditing pronunciation."""
    seen, out = set(), []
    for e in events:
        if e[0] == "say" and e[1] in ("MALE", "FEMALE") and not e[3].startswith(FRAG_RATE):
            key = e[2].lower()
            if key not in seen:
                seen.add(key)
                out += [e, ("pause", 1200)]
    return out

# ---------------------------------------------------------------- synthesis
def clip_path(cache, voice, rate, text, pitch="+0Hz"):
    key = f"{voice}|{rate}|{text}" if pitch == "+0Hz" else f"{voice}|{rate}|{pitch}|{text}"
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    return cache / f"{h}.mp3"

async def synth_all(events, cache):
    import edge_tts
    from edge_tts.exceptions import NoAudioReceived
    sem = asyncio.Semaphore(CONCURRENCY)
    todo = {}
    for e in events:
        if e[0] == "say":
            p = clip_path(cache, VOICES[e[1]], e[3], e[2], e[4])
            if not p.exists():
                todo[p] = e
    print(f"  {len(todo)} clips to synthesise ({len(events) - len(todo)} reused from cache or pauses)")
    failed = []

    async def fetch(text, voice, rate, p, pitch="+0Hz"):
        tmp = p.with_suffix(".part")
        await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(tmp))
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.rename(p)
            return True
        tmp.unlink(missing_ok=True)
        return False

    async def one(p, e):
        async with sem:
            text, voice, rate, pitch = e[2], VOICES[e[1]], e[3], e[4]
            # variants to try if the service returns nothing for the text as written
            variants = [text]
            if not re.search(r"[.!?]$", text):
                variants.append(text + ".")
            if len(tokens(text)) == 1:
                variants.append(text.strip(".!?") + ", " + text.strip(".!?") + ".")
            delay = 3
            for attempt in range(6):
                v = variants[min(attempt, len(variants) - 1)]
                try:
                    await asyncio.sleep(PACE_S)
                    if await fetch(v, voice, rate, p, pitch):
                        return
                except NoAudioReceived:
                    pass
                except Exception as ex:
                    print(f"    retrying ({type(ex).__name__}): {text}")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 40)
            failed.append(e)

    done = 0
    tasks = [one(p, e) for p, e in todo.items()]
    for coro in asyncio.as_completed(tasks):
        await coro
        done += 1
        if done % 25 == 0 or done == len(tasks):
            print(f"    {done}/{len(tasks)}")
    if failed:
        rep = pathlib.Path("failed_clips.txt")
        rep.write_text("\n".join(f"{e[1]}: {e[2]}" for e in failed), encoding="utf-8")
        print(f"  ! {len(failed)} clips could not be fetched (listed in {rep}); 1 s of silence used instead.")
        print(  "    Run the same command again later: only the missing clips are fetched.")
    return failed

def assemble(events, cache, out):
    from pydub import AudioSegment
    audio = AudioSegment.silent(duration=800)
    for e in events:
        if e[0] == "pause":
            audio += AudioSegment.silent(duration=e[1])
        else:
            p = clip_path(cache, VOICES[e[1]], e[3], e[2], e[4])
            clip = AudioSegment.from_file(p) if p.exists() else AudioSegment.silent(duration=1000)
            audio += clip + AudioSegment.silent(duration=GAP_AFTER_LINE_MS)
    audio = audio.set_frame_rate(44100).set_channels(1)
    audio.export(out, format="mp3", bitrate="96k", tags={"title": out.stem.replace("_", " "), "artist": "Lithuanian course"})
    return len(audio) / 60000

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts", nargs="+")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--narrator", help="e.g. en-AU-NatashaNeural (female), en-GB-RyanNeural")
    ap.add_argument("--lt-rate", help="Lithuanian speed, e.g. -20%% (slower) or +0%%")
    ap.add_argument("--cache", default="tts_cache")
    ap.add_argument("--build-up", choices=["fragments", "word"], default="fragments",
                    help="fragments: read syllable fragments (tas, rytas) as written; "
                         "word: replace each fragment by the whole word, read slowly")
    ap.add_argument("--concurrency", type=int, help="parallel requests (default 2; 1 if you get throttled)")
    ap.add_argument("--word-check", action="store_true",
                    help="build Lesson_NN_words.mp3: every distinct Lithuanian line once, to audit pronunciation")
    a = ap.parse_args()
    if a.narrator: VOICES["NARRATOR"] = a.narrator
    global LT_RATE
    if a.lt_rate: LT_RATE = a.lt_rate
    global CONCURRENCY
    if a.concurrency: CONCURRENCY = a.concurrency
    cache = pathlib.Path(a.cache); cache.mkdir(exist_ok=True)

    for t in a.transcripts:
        t = pathlib.Path(t)
        print(f"\n{t.name}")
        events = parse(t)
        if a.build_up == "word":
            events = fragments_to_words(events)
        if a.word_check:
            events = word_check_events(events)
        says = [e for e in events if e[0] == "say"]
        pause_s = sum(e[1] for e in events if e[0] == "pause") / 1000
        print(f"  {len(says)} spoken lines, {pause_s/60:.1f} min of pauses")
        if a.dry_run:
            for e in events[:40]:
                print("   ", e if e[0] == "pause" else f"{e[1]:8s} {e[3]:5s} {e[4]:6s} {e[2]}")
            print("    ...")
            continue
        asyncio.run(synth_all(events, cache))
        out = t.with_name(t.stem + ("_words" if a.word_check else "") + ".mp3")
        mins = assemble(events, cache, out)
        print(f"  -> {out.name}  ({mins:.1f} min)")

if __name__ == "__main__":
    main()
