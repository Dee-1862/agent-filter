"""SEALED held-out items. Do not read from engine code; do not tune against these.

Format: add(case, cluster, segs=[(speaker, flag, text)], facts=[...]).
flag: x private, u public (must stay), n neutral (not scored); suffix 'c' = cue-bearing line
(used only to pick segments for the noisy-ASR variant).
"""
H = []


def add(case, cluster, segs, facts):
    H.append({"case": case, "cluster": cluster, "segs": segs, "facts": facts})


# ---------------------------------------------------------------- explicit start + explicit end
add("explicit_start_end", "c-e1", [
    ("Amara", "u", "Let's start with the Q4 onboarding metrics. Activation is up to 61 percent."),
    ("Tomasz", "u", "That's mostly the new checklist, and trial-to-paid conversion held at eleven percent."),
    ("Amara", "nc", "Tomasz, can we keep this part out of the notes?"),
    ("Tomasz", "x", "Sure. A recruiter told me Kestrel Logistics is offering our head of data a package well above what we pay her."),
    ("Keiko", "x", "If she leaves we lose the only person who understands the churn model."),
    ("Amara", "x", "Then we need a retention conversation before the offsite, and nobody mentions it to her team."),
    ("Amara", "nc", "Okay, we can write again."),
    ("Rafael", "u", "On the dashboard side, the cohort view ships to beta on the fourteenth of November."),
    ("Keiko", "u", "I'll update the metrics glossary by Friday."),
    ("Amara", "u", "Great, last item is the webinar, which is December third."),
], ["activation is up to 61 percent", "cohort view ships to beta on the fourteenth of November", "december third"])

add("explicit_start_end", "c-e2", [
    ("Henrik", "u", "Welcome to the facilities committee. First, the lease renewal for the east warehouse."),
    ("Lucia", "u", "The landlord proposed a three year term with a two percent annual escalator."),
    ("Henrik", "u", "Acceptable. Second item is the parking permit audit."),
    ("Dmitri", "nc", "Before that, please don't minute this."),
    ("Dmitri", "x", "Our security contractor flagged that the badge system was breached last month and we haven't told the tenants."),
    ("Lucia", "x", "How many badges were cloned?"),
    ("Dmitri", "x", "About forty, and the vendor is still investigating."),
    ("Henrik", "nc", "Understood. You can resume notes now."),
    ("Lucia", "u", "For parking, we found 22 unused permits and will reclaim them by December first."),
    ("Henrik", "u", "Good. The next committee meeting is on the ninth."),
], ["three year term", "22 unused permits", "reclaim them by december first"])

add("explicit_start_end", "c-e3", [
    ("Farah", "u", "Marketing sync. The autumn campaign goes live on October 30th with a budget of 80 thousand."),
    ("Callum", "u", "Creative assets are approved except the video cut-down."),
    ("Farah", "nc", "Quick thing, and this is strictly between us."),
    ("Callum", "x", "I interviewed at the agency across the street last week and I'm weighing an offer."),
    ("Farah", "x", "Understood. Thanks for telling me, I won't repeat it."),
    ("Callum", "x", "I just need to give them an answer by the end of the month."),
    ("Farah", "nc", "Okay, back to regular minutes. Where are we on the video?"),
    ("Soo-jin", "u", "The cut-down needs another round, the editor is back Thursday."),
    ("Callum", "u", "I'll chase the paid social approvals tomorrow."),
    ("Farah", "u", "Great, so the launch stays on October 30th."),
], ["budget of 80 thousand", "editor is back thursday", "launch stays on october 30th"])

add("explicit_start_end", "c-e4", [
    ("Imani", "u", "Engineering leads weekly. The payments migration finished with zero downtime."),
    ("Pavel", "u", "Latency on the new gateway averages 120 milliseconds."),
    ("Imani", "xc", "Just between us, the CFO told me the Singapore office closes in March."),
    ("Pavel", "x", "That affects our on-call rotation, and half the staff there don't know."),
    ("Greta", "x", "I'd hold off on the hiring requisitions for that team until it's announced."),
    ("Imani", "nc", "That's all I wanted to say privately, go ahead and log everything again."),
    ("Greta", "u", "On the rotation, we'll move to a follow-the-sun model starting in January."),
    ("Pavel", "u", "I'll circulate the runbook updates on Wednesday."),
    ("Imani", "u", "Good. Final point, the security review is scheduled for November 18th."),
], ["payments migration finished with zero downtime", "follow-the-sun model starting in january", "security review is scheduled for november 18th"])

add("explicit_start_end", "c-e5", [
    ("Anil", "u", "Product council. The pricing page experiment ran for two weeks."),
    ("Marisol", "u", "Variant B lifted signups by nine percent."),
    ("Anil", "nc", "Marisol, can we pause the notes for a second? It's a personal matter."),
    ("Marisol", "x", "My mother was diagnosed with early dementia and I need to cut my hours starting next month."),
    ("Anil", "x", "Oh, I'm so sorry to hear that."),
    ("Jonas", "x", "That sounds really hard, take whatever time you need."),
    ("Marisol", "x", "Thank you. I'll work out a schedule with my manager."),
    ("Anil", "nc", "Okay, notes are back on. Thanks everyone."),
    ("Jonas", "u", "For the experiment, I suggest we roll out variant B to all new traffic."),
    ("Anil", "u", "Agreed, rollout starts Monday."),
], ["variant b lifted signups by nine percent", "rollout starts monday"])

add("explicit_start_end", "c-e6", [
    ("Yuki", "u", "Customer success review. Net retention is at 108 percent this quarter."),
    ("Oluwaseun", "u", "Enterprise renewals are strong, two expansions closed in the last week."),
    ("Yuki", "xc", "Not for the minutes, but the Hartwell account is threatening to leave over the outage credits."),
    ("Oluwaseun", "x", "Their contract is 1.2 million, so we should offer the extended support tier before they escalate."),
    ("Yuki", "x", "I'll call their VP tomorrow, and we should have counsel ready in case they cite the SLA breach."),
    ("Yuki", "nc", "Alright, you can take notes again."),
    ("Oluwaseun", "u", "Next, the support backlog is down to 140 tickets."),
    ("Yuki", "u", "Let's target under 100 by the end of November."),
    ("Oluwaseun", "u", "I'll share the staffing plan on Thursday."),
], ["net retention is at 108 percent", "support backlog is down to 140 tickets", "target under 100 by the end of november"])

# ---------------------------------------------------------------- explicit start, implicit end
add("explicit_start_implicit_end", "c-s1", [
    ("Amara", "u", "Board prep call. Revenue for the quarter came in at 4.3 million."),
    ("Rafael", "u", "That's six percent above plan, mostly from the EU."),
    ("Amara", "nc", "Before the budget, keep this next part out of the notes please."),
    ("Rafael", "x", "The founder is considering selling his shares to a fund, and the term sheet arrives Friday."),
    ("Amara", "x", "Do the other directors know?"),
    ("Rafael", "x", "Only two of them, so please don't mention it to the rest."),
    ("Amara", "n", "Okay. Moving on to next year's budget."),
    ("Keiko", "u", "We're proposing a 12 percent increase in the engineering headcount budget."),
    ("Rafael", "u", "And a flat marketing budget."),
    ("Amara", "u", "Fine, I'll draft the board deck by Tuesday."),
], ["revenue for the quarter came in at 4.3 million", "12 percent increase in the engineering headcount budget", "draft the board deck by tuesday"])

add("explicit_start_implicit_end", "c-s2", [
    ("Ngozi", "u", "Weekly ops standup. Fulfillment times averaged 2.1 days."),
    ("Dmitri", "u", "Returns dropped to four percent after the packaging change."),
    ("Ngozi", "nc", "Dmitri, I want to tell you something that's not for the notes."),
    ("Ngozi", "x", "Our largest carrier is about to be acquired and they've warned us rates will jump by fifteen percent."),
    ("Dmitri", "x", "That blows up our margin forecast."),
    ("Ngozi", "x", "Which is why I'm quietly talking to two other carriers."),
    ("Dmitri", "n", "Right. Let's switch to the warehouse layout."),
    ("Ngozi", "u", "The new layout adds 400 pallet positions."),
    ("Dmitri", "u", "Install is scheduled for the first week of December."),
    ("Ngozi", "u", "Great, that's all for today."),
], ["fulfillment times averaged 2.1 days", "adds 400 pallet positions", "first week of december"])

add("explicit_start_implicit_end", "c-s3", [
    ("Greta", "u", "Design review for the mobile app. The new navigation tested well, a 4.5 out of 5 usability score."),
    ("Callum", "u", "The accessibility audit found six contrast issues, all fixed."),
    ("Greta", "nc", "Callum, this next part stays among us, no notes."),
    ("Greta", "x", "Sasha filed a complaint about the way Victor talks to the junior designers."),
    ("Callum", "x", "I've seen it too. HR should probably interview the whole team."),
    ("Greta", "x", "I'm meeting HR on Thursday, so don't discuss it with Victor."),
    ("Callum", "n", "Okay. Now, about the icon set."),
    ("Soo-jin", "u", "The icon set is licensed through the end of next year."),
    ("Greta", "u", "Good, then we keep it."),
    ("Callum", "u", "I'll send the final specs to engineering on Friday."),
], ["4.5 out of 5 usability score", "six contrast issues", "licensed through the end of next year"])

add("explicit_start_implicit_end", "c-s4", [
    ("Lucia", "u", "Partnerships call. The reseller agreement with Brightwave is signed."),
    ("Pavel", "u", "They'll start selling in Canada from January."),
    ("Lucia", "nc", "Pavel, can you not write this part down?"),
    ("Pavel", "x", "Counsel says there's a patent claim against the Brightwave module, and we may have to indemnify them."),
    ("Lucia", "x", "What's the exposure?"),
    ("Pavel", "x", "Potentially three million dollars, but nothing is filed yet."),
    ("Lucia", "n", "Thanks for the heads up. Anyway, onto the co-marketing plan."),
    ("Imani", "u", "The co-marketing plan includes two joint webinars."),
    ("Pavel", "u", "The first webinar is on February ninth."),
    ("Lucia", "u", "Great, I'll draft the press release."),
], ["reseller agreement with brightwave is signed", "two joint webinars", "first webinar is on february ninth"])

add("explicit_start_implicit_end", "c-s5", [
    ("Henrik", "u", "Quarterly planning. The platform team hit its OKRs at ninety percent."),
    ("Farah", "u", "The remaining ten percent is the observability rollout, delayed by procurement."),
    ("Henrik", "nc", "Hold on, let's keep the next bit out of the notes."),
    ("Farah", "x", "I'm negotiating my raise and I was told the band tops out at one hundred forty thousand."),
    ("Henrik", "x", "That's lower than what Joel earns in the same role, which is a problem."),
    ("Farah", "x", "I know, and I'd rather this stays unofficial for now."),
    ("Henrik", "n", "Understood. So, observability procurement."),
    ("Anil", "u", "Procurement approved the vendor on Tuesday."),
    ("Farah", "u", "The rollout starts the week of November 24th."),
    ("Henrik", "u", "Good, then the OKR gap closes by year end."),
], ["platform team hit its okrs at ninety percent", "procurement approved the vendor on tuesday", "rollout starts the week of november 24th"])

add("explicit_start_implicit_end", "c-s6", [
    ("Soo-jin", "u", "Product sync. The calendar integration is in beta with 300 users."),
    ("Bilal", "u", "Crash rate is under 0.2 percent."),
    ("Soo-jin", "nc", "Bilal, this is private, could you leave it out of the notes?"),
    ("Bilal", "x", "I have to be out for treatment for the next six weeks. It's chemo, I only just found out."),
    ("Soo-jin", "x", "I'm so sorry. We'll cover your on-call shifts."),
    ("Marisol", "x", "Anything you need, honestly."),
    ("Soo-jin", "n", "Alright, let's get back to the beta feedback."),
    ("Marisol", "u", "Feedback is mostly about timezone handling."),
    ("Soo-jin", "u", "We'll fix timezone handling in the next sprint."),
    ("Marisol", "u", "I'll write up the sprint tickets today."),
], ["calendar integration is in beta with 300 users", "crash rate is under 0.2 percent", "fix timezone handling in the next sprint"])

# ---------------------------------------------------------------- retroactive
add("retroactive", "c-r1", [
    ("Tomasz", "u", "Vendor review. The CRM migration is 70 percent complete."),
    ("Keiko", "u", "Data mapping for the legacy accounts is the remaining risk."),
    ("Tomasz", "x", "By the way, we're in talks to acquire Orbis Systems, the offer is around 25 million."),
    ("Keiko", "x", "That would double our customer base."),
    ("Tomasz", "u", "Back to the migration, we need a rollback plan."),
    ("Keiko", "u", "I'll draft it by Wednesday."),
    ("Tomasz", "nc", "Actually, please take the acquisition discussion out of the notes, that wasn't meant to be shared."),
    ("Rafael", "u", "Understood. Final item, support team training is on November 6th."),
    ("Tomasz", "u", "Good, I'll book the room."),
], ["crm migration is 70 percent complete", "need a rollback plan", "support team training is on november 6th"])

add("retroactive", "c-r2", [
    ("Greta", "u", "Okay, sprint retro. We shipped nine of eleven stories."),
    ("Callum", "u", "The two misses were blocked on the design handoff."),
    ("Greta", "u", "Noted, we'll fix the handoff process."),
    ("Callum", "x", "Honestly, the lead of that other team is incompetent and I'd get him replaced."),
    ("Callum", "x", "I've said it to the VP and she agreed."),
    ("Callum", "nc", "Please forget the last two things I said, that was out of line."),
    ("Greta", "u", "Okay. Next, the team lunch is on the 20th."),
    ("Soo-jin", "u", "I'll reserve the restaurant."),
    ("Greta", "u", "Great, thanks all."),
], ["shipped nine of eleven stories", "fix the handoff process", "team lunch is on the 20th"])

add("retroactive", "c-r3", [
    ("Lucia", "u", "Hiring update. We have three open roles on the data team."),
    ("Dmitri", "x", "I should mention my visa renewal is pending, and I might not be able to travel until it clears."),
    ("Lucia", "u", "Interviews run next week, and the panel is Pavel, Imani and me."),
    ("Imani", "u", "We should also finalize the offer template."),
    ("Pavel", "nc", "Lucia, please remove what Dmitri said about his visa from the notes, that's his personal business."),
    ("Dmitri", "nc", "Yes, thank you, please do."),
    ("Lucia", "u", "Of course. Moving on, the offer template needs sign-off by legal."),
    ("Imani", "u", "I'll send it over today."),
    ("Lucia", "u", "Great, that's everything."),
], ["three open roles on the data team", "panel is pavel, imani and me", "offer template needs sign-off by legal"])

add("retroactive", "c-r4", [
    ("Amara", "n", "Launch planning. The press briefing is on Monday the third."),
    ("Rafael", "uc", "Strike that, I meant Tuesday the fourth."),
    ("Keiko", "u", "Tuesday works, the embargo lifts at nine in the morning."),
    ("Amara", "u", "And the customer webinar follows at two."),
    ("Rafael", "u", "I'll confirm the venue for the briefing."),
    ("Keiko", "uc", "Also, scratch the idea of a third demo, we only need two."),
    ("Amara", "u", "Fine, two demos."),
    ("Rafael", "u", "I'll send the invites today."),
    ("Keiko", "u", "The budget for the event is 15 thousand."),
], ["tuesday the fourth", "embargo lifts at nine in the morning", "budget for the event is 15 thousand"])

add("retroactive", "c-r5", [
    ("Imani", "u", "Q1 offsite planning. We have budget for forty people."),
    ("Pavel", "uc", "I'd say the venue is in Lisbon, no wait, strike that, I meant Porto."),
    ("Imani", "u", "Porto is cheaper anyway. Flights are around 180 euros."),
    ("Pavel", "x", "On a different note, we'll cut the contractors' stipends by thirty percent before anyone notices."),
    ("Imani", "x", "Don't tell the contractors yet, we'll announce it in January."),
    ("Pavel", "nc", "Actually, strike that, scratch all of it, I shouldn't have said that."),
    ("Imani", "u", "Okay. Agenda for the offsite: two workshops and a dinner."),
    ("Pavel", "u", "I'll book the workshops for the second day."),
    ("Imani", "u", "Good."),
], ["budget for forty people", "i meant porto", "two workshops and a dinner"])

add("retroactive", "c-r1", [   # no-cue control twin of c-r1: same shape, no retraction, content is shareable
    ("Tomasz", "u", "Vendor review. The CRM migration is 70 percent complete."),
    ("Keiko", "u", "Data mapping for the legacy accounts is the remaining risk."),
    ("Tomasz", "u", "By the way, our Orbis Systems acquisition was announced this morning, the price is public at 25 million."),
    ("Keiko", "u", "That would double our customer base."),
    ("Tomasz", "u", "Back to the migration, we need a rollback plan."),
    ("Keiko", "u", "I'll draft it by Wednesday."),
    ("Tomasz", "uc", "Actually, please make sure the acquisition discussion is in the notes, it is public as of today."),
    ("Rafael", "u", "Understood. Final item, support team training is on November 6th."),
    ("Tomasz", "u", "Good, I'll book the room."),
], ["orbis systems acquisition was announced this morning", "need a rollback plan", "support team training is on november 6th"])

# ---------------------------------------------------------------- implicit (no cue) incl. cross-segment PII
add("implicit", "c-i1", [
    ("Amara", "u", "Planning for the Munich trip. We land on the 12th."),
    ("Tomasz", "x", "Since the biopsy results came back last week I've been pretty distracted, sorry."),
    ("Keiko", "n", "Take care of yourself, we can cover the client demo."),
    ("Amara", "u", "The client demo is Thursday at ten."),
    ("Keiko", "u", "I'll prepare the slides on the migration timeline."),
    ("Amara", "u", "Dinner is booked for seven at the hotel restaurant."),
    ("Tomasz", "u", "I'll handle the expense reports."),
    ("Keiko", "u", "Flights are booked on the same airline as last time."),
    ("Amara", "u", "Great."),
], ["we land on the 12th", "client demo is thursday at ten", "dinner is booked for seven"])

add("implicit", "c-i2", [
    ("Henrik", "u", "Budget committee. Cloud spend is flat at 210 thousand a month."),
    ("Ngozi", "u", "We can save about fifteen percent by reserving instances."),
    ("Dmitri", "x", "While we're here, I found out Natasha makes thirty grand more than me for the same role."),
    ("Henrik", "x", "That's an equity issue, her base is 185 and yours is 155."),
    ("Ngozi", "u", "Back on reserved instances, the commitment would be one year."),
    ("Henrik", "u", "Fine, let's go with one year."),
    ("Dmitri", "u", "I'll run the numbers for the storage tier too."),
    ("Ngozi", "u", "Please share them by Monday."),
    ("Henrik", "u", "Thanks all."),
], ["cloud spend is flat at 210 thousand a month", "save about fifteen percent by reserving instances", "go with one year"])

add("implicit", "c-i3", [
    ("Lucia", "u", "Support leads sync. First-response time improved to 11 minutes."),
    ("Bilal", "u", "The new macros are saving about two minutes per ticket."),
    ("Lucia", "x", "We're putting Marcus on a performance improvement plan next week and he doesn't know yet."),
    ("Bilal", "x", "He's missed his targets three months running, so that's fair."),
    ("Lucia", "u", "On staffing, we need two more agents for the holiday peak."),
    ("Bilal", "u", "I can open the requisitions tomorrow."),
    ("Lucia", "u", "Please target a start date of November 17th."),
    ("Bilal", "u", "Will do."),
    ("Lucia", "u", "That's all for today."),
], ["first-response time improved to 11 minutes", "two more agents for the holiday peak", "start date of november 17th"])

add("implicit", "c-i4", [
    ("Pavel", "u", "Finance review. Accounts receivable days are down to 42."),
    ("Greta", "u", "Collections from the two largest customers improved."),
    ("Pavel", "x", "We got a letter from the state regulator about our old billing practices, and our lawyers think there will be a fine."),
    ("Greta", "x", "How big?"),
    ("Pavel", "x", "They're guessing somewhere around 400 thousand, plus a consent order."),
    ("Greta", "u", "On the forecast, we should assume flat receivables through year end."),
    ("Pavel", "u", "I'll update the cash model by Thursday."),
    ("Greta", "u", "Thanks, that's it."),
], ["accounts receivable days are down to 42", "assume flat receivables through year end", "update the cash model by thursday"])

add("implicit", "c-i5", [
    ("Ngozi", "u", "Leadership offsite recap. We aligned on three company priorities for next year."),
    ("Rafael", "u", "Priority one is reliability, two is international expansion, three is margin."),
    ("Ngozi", "x", "Between us, we're planning to cut fifteen percent of staff in January and the announcement comes after the holidays."),
    ("Rafael", "x", "The support and sales ops teams get hit hardest."),
    ("Ngozi", "u", "For reliability, the target is 99.95 percent uptime."),
    ("Rafael", "u", "We'll hire a second SRE lead in the first quarter."),
    ("Ngozi", "u", "Good. Slides will be shared Monday."),
    ("Rafael", "u", "Thanks."),
], ["aligned on three company priorities", "target is 99.95 percent uptime", "slides will be shared monday"])

add("implicit", "c-i6", [
    ("Callum", "u", "Customer visit prep for Tuesday. We meet them at their office at nine."),
    ("Yuki", "u", "I'll bring the demo laptop and the pilot proposal."),
    ("Callum", "x", "If anything changes, you can reach me on my personal cell, it's four one five, five five five."),
    ("Callum", "x", "Zero one eight seven. Call after eight in the evening."),
    ("Yuki", "u", "Got it. Should we book parking?"),
    ("Callum", "u", "Yes, there's a visitor garage next to the building."),
    ("Yuki", "u", "The pilot proposal is priced at 60 thousand for three months."),
    ("Callum", "u", "Good, let's keep that number as the opening."),
    ("Yuki", "u", "Done."),
], ["we meet them at their office at nine", "priced at 60 thousand for three months", "visitor garage next to the building"])

# ---------------------------------------------------------------- false alarms
add("false_alarm", "c-f1", [
    ("Farah", "u", "Before we start, team social on Friday. Anyone seen the film Off the Record?"),
    ("Callum", "uc", "Yes, Off the Record is a documentary about a journalist, I loved it."),
    ("Soo-jin", "u", "Let's screen it in the break room after lunch."),
    ("Farah", "u", "I'll book the projector for four o'clock."),
    ("Callum", "u", "Back to work, the Q4 ticket queue is at 85 open items."),
    ("Soo-jin", "u", "Most of them are low priority."),
    ("Farah", "u", "I'll triage the rest this afternoon."),
    ("Callum", "u", "Thanks, and the offsite survey closes Wednesday."),
], ["screen it in the break room", "q4 ticket queue is at 85 open items", "offsite survey closes wednesday"])

add("false_alarm", "c-f2", [
    ("Greta", "u", "Venue for the party is booked. A local band called Off the Record is playing."),
    ("Henrik", "uc", "Off the Record plays covers, and they charge 900 for two sets."),
    ("Greta", "u", "That fits the budget of 3,000."),
    ("Henrik", "u", "Catering needs a headcount by the 14th."),
    ("Lucia", "u", "I'll collect RSVPs through the intranet form."),
    ("Greta", "u", "Parking will be in the lot behind building C."),
    ("Henrik", "u", "Good, the party is on December 5th."),
    ("Lucia", "u", "I'll send the calendar invite."),
], ["band called off the record is playing", "budget of 3,000", "party is on december 5th"])

add("false_alarm", "c-f3", [
    ("Imani", "u", "For brand awareness, the CTO is a guest on the Off the Record podcast next week."),
    ("Pavel", "uc", "The Off the Record podcast has about forty thousand listeners."),
    ("Imani", "u", "We should prepare talking points about the platform launch."),
    ("Pavel", "u", "I'll draft them and send for review on Monday."),
    ("Ngozi", "u", "The recording is scheduled for the 19th."),
    ("Imani", "u", "Legal wants to see the final points beforehand."),
    ("Pavel", "u", "That's fine, we'll allow two days for review."),
    ("Ngozi", "u", "Great, link to the episode goes on the blog after."),
], ["forty thousand listeners", "recording is scheduled for the 19th", "two days for review"])

add("false_alarm", "c-f4", [
    ("Anil", "u", "Sales update. We had a record quarter, 3.9 million in bookings."),
    ("Marisol", "u", "The new customer record in the CRM now links to the billing account."),
    ("Anil", "u", "Great. The database team needs to dedupe about 5,000 duplicate records."),
    ("Marisol", "u", "I'll set up the merge job tonight."),
    ("Jonas", "uc", "Keep a record of every merge in the audit table, on the record for compliance."),
    ("Anil", "u", "Agreed. We also need to set the record straight on the pricing page."),
    ("Marisol", "u", "I'll fix the typo on the pricing page this afternoon."),
    ("Jonas", "u", "Bookings forecast for next quarter is 4.2 million."),
], ["record quarter, 3.9 million in bookings", "dedupe about 5,000 duplicate records", "forecast for next quarter is 4.2 million"])

add("false_alarm", "c-f5", [
    ("Henrik", "u", "Manager training topic: how to handle sensitive conversations."),
    ("Dmitri", "uc", "Last year someone literally said 'let's go off the record' in a staff meeting, and it caused confusion."),
    ("Henrik", "u", "Right, nobody knew whether the notes were still running."),
    ("Dmitri", "u", "We should teach managers to use the pause feature rather than that phrase."),
    ("Lucia", "u", "I'll add a slide with the correct procedure."),
    ("Henrik", "u", "The training is on November 12th."),
    ("Dmitri", "u", "Attendance is mandatory for all people managers."),
    ("Lucia", "u", "I'll send the invites tomorrow."),
], ["teach managers to use the pause feature", "training is on november 12th", "attendance is mandatory for all people managers"])

add("false_alarm", "c-f6", [
    ("Soo-jin", "uc", "Heads up, this is an all-hands prep. Remember we are not off the record, everything today goes into the notes."),
    ("Bilal", "uc", "Understood, nothing here is off the record, so let's stick to the agenda."),
    ("Soo-jin", "u", "First, the roadmap for the next two quarters."),
    ("Bilal", "u", "Search relevance ships in January."),
    ("Farah", "u", "The mobile offline mode is targeted for March."),
    ("Soo-jin", "u", "Good. Customer advisory board meets on December 10th."),
    ("Bilal", "u", "I'll prepare the product update deck."),
    ("Farah", "u", "And I'll gather questions from the field team."),
], ["search relevance ships in january", "offline mode is targeted for march", "advisory board meets on december 10th"])

# ---------------------------------------------------------------- public look-alikes
add("public", "c-p1", [
    ("Amara", "u", "Product demo prep. The new salary calculator for our HR customers launches in beta on Monday."),
    ("Keiko", "u", "It takes a job title and location and shows the market pay range."),
    ("Amara", "u", "Pricing for the calculator is 5 dollars per seat per month."),
    ("Keiko", "u", "We benchmark against public salary surveys, so no customer data is shown."),
    ("Rafael", "u", "I'll record a two minute walkthrough video for the sales team."),
    ("Amara", "u", "Great. Docs go live the same day."),
    ("Keiko", "u", "We need to add a disclaimer about regional variation."),
    ("Rafael", "u", "I'll draft that today."),
], ["salary calculator for our hr customers launches in beta on monday", "5 dollars per seat per month", "docs go live the same day"])

add("public", "c-p2", [
    ("Greta", "u", "Reminder from people ops, the health insurance enrollment deadline is November 15th."),
    ("Callum", "u", "Everyone should pick a plan in the benefits portal before then."),
    ("Greta", "u", "The company covers eighty percent of the premium on all three plans."),
    ("Callum", "u", "There's an information session on Wednesday at noon."),
    ("Soo-jin", "u", "I'll post the slides on the intranet afterward."),
    ("Greta", "u", "Also the dental option is unchanged from last year."),
    ("Callum", "u", "Thanks, I'll remind my team."),
    ("Soo-jin", "u", "Done."),
], ["health insurance enrollment deadline is november 15th", "information session on wednesday at noon", "dental option is unchanged"])

add("public", "c-p3", [
    ("Henrik", "u", "IT update. We're migrating the HR portal to a new vendor on the 22nd."),
    ("Lucia", "u", "Employees will keep their logins through single sign-on."),
    ("Henrik", "u", "The old portal goes read-only on the 20th."),
    ("Dmitri", "u", "Payroll and time-off requests move over automatically."),
    ("Lucia", "u", "We'll run two training sessions for managers."),
    ("Henrik", "u", "The helpdesk will have extended hours that week."),
    ("Dmitri", "u", "I'll announce this on the company channel."),
    ("Lucia", "u", "Good."),
], ["migrating the hr portal to a new vendor on the 22nd", "old portal goes read-only on the 20th", "two training sessions for managers"])

add("public", "c-p4", [
    ("Imani", "u", "Compliance calendar. Annual legal compliance training is due by December 1st."),
    ("Pavel", "u", "The updated terms of service were published on the website yesterday."),
    ("Imani", "u", "The privacy policy changes take effect in January."),
    ("Ngozi", "u", "Employees can find the code of conduct on the intranet."),
    ("Pavel", "u", "We'll send a reminder to anyone who hasn't finished by the 25th."),
    ("Imani", "u", "The training takes about forty minutes."),
    ("Ngozi", "u", "I'll put the link in the weekly newsletter."),
    ("Pavel", "u", "Thanks."),
], ["legal compliance training is due by december 1st", "privacy policy changes take effect in january", "training takes about forty minutes"])

add("public", "c-p5", [
    ("Anil", "u", "Roadmap check on our wellness app. The symptom checker feature launches next quarter."),
    ("Marisol", "u", "It stores health data locally on the phone, nothing goes to our servers."),
    ("Anil", "u", "We completed the HIPAA-readiness review last month."),
    ("Jonas", "u", "The medical advisory board approved the question flow."),
    ("Marisol", "u", "App store listing needs the privacy labels updated."),
    ("Anil", "u", "I'll handle that this week."),
    ("Jonas", "u", "Beta signups are open on the website."),
    ("Marisol", "u", "We have 1,200 testers so far."),
], ["symptom checker feature launches next quarter", "completed the hipaa-readiness review last month", "1,200 testers so far"])

add("public", "c-p6", [
    ("Dmitri", "u", "Incident review. The nightly batch job fired twice and we had to terminate the stale instances."),
    ("Farah", "u", "A performance review of the query plan showed a missing index."),
    ("Dmitri", "u", "We added the index and the settlement of ledger entries now completes in nine minutes."),
    ("Callum", "u", "We should also cut the log volume, laying off the debug logging in production saves a lot."),
    ("Farah", "u", "That alone reduces storage cost by fifteen percent."),
    ("Dmitri", "u", "The confidential flag on the config endpoint is already removed."),
    ("Callum", "u", "I'll update the runbook with the termination steps."),
    ("Farah", "u", "Great, postmortem is due Friday."),
], ["settlement of ledger entries now completes in nine minutes", "reduces storage cost by fifteen percent", "postmortem is due friday"])
