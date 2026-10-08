## Memory
Memory workspace: ops  (Agency Memory connector)
- Call `context` once at session start for this workspace (the task in one line); call it again only if the task changes.
- Before reading wikis, specs, transcripts or old threads to answer "what did we decide / why", call `recall` (k=3) in this workspace only.
- At the end, `remember` at most 3 durable lessons (1-3 sentences, dated, with the why). If one corrects an older memory, save the fix, then `forget` the old id.
- Never store secrets or lead, customer or downline personal data.
- If the connector isn't available in this session, say so once and carry on.
