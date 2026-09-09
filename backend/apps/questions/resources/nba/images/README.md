# Question images

Binaries referenced by this category's YAML — a question's own illustration
(`image:`) and the options of an `image-answer` question. They live here, beside
the questions that name them, rather than in `backend/media/`: a question and its
picture are one authored thing, they are reviewed in the same pull request, and a
resource folder that carries its own assets can be moved or copied whole.

`sync_questions` copies what it needs into `MEDIA_ROOT` (`questions/<category>/`
for a question image, `questions/answers/<category>/` for an option) and stores
the relative path on the model. The copy compares content digests, so re-running
a sync of an unchanged catalog moves no bytes.

**Name a file, not a path.** YAML says `image: court-free-throw-line.png`; the
loader resolves it against this folder. A file named in the YAML and missing here
fails the load, because a stored path to nothing becomes a question that cannot
be answered in a live match.

## The court diagrams

`court-*.png` are generated, not photographed — run
`uv run python scripts/generate_court_diagrams.py` from the repo root to rebuild
them. Adding a fifth line to the question means adding it to that script.

Generated assets are the easy case. **Anything photographic needs a licence that
covers this use**, and neither the loader nor the reviewer can tell one from the
other by looking — so record the source and the licence in the pull request that
adds it.
