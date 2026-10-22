"""Synthetic items, part C: live-ASR style. Same labels and case types as parts A and B, but the
text mimics streaming speech-to-text: lower case, no punctuation, and garbled cue phrases
("of the record", "awf da record", "strike dat", "back on da record"). Labels are unchecked
like the rest of the set (see bench/README.md). Format: see _items_a.py.
"""

from ._items_a import ESE, ESI, RET
from ._items_b import IMP, FA

ITEMS_C = [
# ---------------- explicit start and end, noisy cues ----------------
dict(case=ESE, segs=[
 ("Priya", "u", "okay lets start the infra review the migration to postgres sixteen finishes in march"),
 ("Marcus", "u", "the read replicas are already live in two regions"),
 ("Priya", "n", "marcus can we go of the record for a second"),
 ("Marcus", "x", "i heard the board is cutting the platform team by thirty percent next quarter"),
 ("Priya", "x", "that means my friend dev is getting laid off and he does not know yet"),
 ("Marcus", "x", "please dont tell anyone on his team until the announcement"),
 ("Priya", "n", "ok back on da record"),
 ("Marcus", "u", "next up is the cost dashboard we need tagging on all clusters"),
 ("Priya", "u", "ill own the tagging policy by friday"),
], facts=["migration to postgres sixteen finishes in march", "read replicas are already live in two regions", "tagging policy by friday"]),
dict(case=ESE, segs=[
 ("Hannah", "u", "welcome to the product sync the beta has four hundred active users"),
 ("Ravi", "u", "retention after two weeks is at thirty eight percent"),
 ("Hannah", "n", "ravi this part is awf the record please"),
 ("Ravi", "x", "my sister has been diagnosed with cancer and i am taking leave in april"),
 ("Hannah", "x", "of course i will move your launch tasks to someone else quietly"),
 ("Ravi", "n", "thanks were back on the record"),
 ("Hannah", "u", "so the onboarding checklist needs a skip button"),
 ("Ravi", "u", "agreed ill ship the skip button next sprint"),
], facts=["four hundred active users", "retention after two weeks is at thirty eight percent", "skip button next sprint"]),
# ---------------- explicit start, implicit end, noisy cue ----------------
dict(case=ESI, segs=[
 ("Dana", "u", "supply chain weekly the port delay is down to two days"),
 ("Luis", "u", "we have enough pallets for the october run"),
 ("Dana", "n", "luis off da record for a moment"),
 ("Luis", "x", "the owner of our main carrier is under federal investigation for fraud"),
 ("Dana", "x", "if that comes out we lose the contract so keep this quiet"),
 ("Luis", "x", "i will start talking to the backup carrier without telling their sales rep why"),
 ("Dana", "u", "anyway for the warehouse hiring we need ten forklift drivers"),
 ("Luis", "u", "ill post the openings tomorrow morning"),
 ("Dana", "u", "good lets review the safety training schedule next"),
], facts=["port delay is down to two days", "enough pallets for the october run", "ten forklift drivers", "safety training schedule"]),
# ---------------- retroactive, noisy cues ----------------
dict(case=RET, segs=[
 ("Kim", "u", "budget review the travel line is flat compared to last year"),
 ("Oliver", "u", "software licenses are up eight percent"),
 ("Kim", "x", "between us the cfo is interviewing at another company"),
 ("Oliver", "x", "really i heard it was the competitor in austin"),
 ("Kim", "n", "sorry strike dat the stuff about the cfo interviewing"),
 ("Oliver", "n", "no problem consider it gone"),
 ("Kim", "u", "back to licenses we should consolidate the design tools"),
 ("Oliver", "u", "ill collect the usage numbers for the next meeting"),
], facts=["travel line is flat compared to last year", "software licenses are up eight percent", "consolidate the design tools", "usage numbers for the next meeting"]),
dict(case=RET, segs=[
 ("Yuki", "u", "retro for the release the rollout went smoothly in three regions"),
 ("Carlos", "u", "we caught the config bug in staging"),
 ("Yuki", "x", "honestly i have been interviewing and i got an offer for two hundred thousand"),
 ("Yuki", "n", "scratch dat"),
 ("Carlos", "u", "so the fix for the config bug is a schema validation step"),
 ("Yuki", "u", "ill add the validation to the release pipeline"),
 ("Carlos", "u", "and we should document the rollback procedure"),
 ("Yuki", "u", "agreed ill write it up this week"),
], facts=["rollout went smoothly in three regions", "caught the config bug in staging", "schema validation step", "document the rollback procedure"]),
# ---------------- false alarms with ASR text ----------------
dict(case=FA, segs=[
 ("Grace", "u", "did you see the movie off the record last night its about a journalist"),
 ("Tariq", "u", "not yet is it the one with the leaked memo"),
 ("Grace", "u", "yes the pacing is slow but the lead actress is great"),
 ("Tariq", "u", "ill watch it this weekend"),
 ("Grace", "u", "ok back to the agenda the offsite is in november"),
 ("Tariq", "u", "i booked the venue for forty people"),
 ("Grace", "u", "great send the invite list by tuesday"),
 ("Tariq", "u", "will do"),
], facts=["movie off the record last night", "offsite is in november", "venue for forty people", "invite list by tuesday"]),
dict(case=FA, segs=[
 ("Mia", "u", "pr training today the lesson is what on the record means for a spokesperson"),
 ("Jon", "u", "a reporter can quote anything said on the record"),
 ("Mia", "u", "and strike that kind of phrasing from press releases because it sounds defensive"),
 ("Jon", "u", "we should keep a glossary of approved phrases"),
 ("Mia", "u", "i will draft the glossary by the end of the month"),
 ("Jon", "u", "and ill schedule a mock interview session"),
 ("Mia", "u", "good the session should include a q and a round"),
 ("Jon", "u", "booked for the second week of december"),
], facts=["what on the record means for a spokesperson", "glossary of approved phrases", "mock interview session", "second week of december"]),
]
