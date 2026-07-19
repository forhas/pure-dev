# prompt source

Treat the provided text as the full raw requirement.

## Steps

1. If `ref` is empty or a whitespace-only string, ask via `AskUserQuestion`: "What should the ticket cover?" — use a free-text slot, not multiple choice.
2. Parse the text into the output shape:
   - `title` — 5-10 words summarizing the ask. Use the first sentence or imperative phrase from the text; shorten with your own wording if needed.
   - `body` — markdown. If the text is already well-structured, preserve its structure. Otherwise, organize it into sections:
     - `## Requirements` — what needs to exist.
     - `## Acceptance Criteria` — checklist of observable conditions, if inferable.
     - `## Context` — background / motivation, if mentioned.
     - `## Open Questions` — anything that needs user clarification, if the text leaves gaps.
   - `sourceRef` — literal `"prompt"`.
   - `confidence`:
     - `"low"` if text length < 100 characters, or no acceptance criteria could be inferred, or open questions outnumber requirements.
     - `"medium"` if criteria are present but vague, or the user clearly wrote a summary rather than a spec.
     - `"high"` if goal + scope + acceptance are all clean.
3. Return the structured result.

Do not invoke `notion-dev:ticket-interviewer` here — that is the caller's responsibility, based on the returned `confidence`.
