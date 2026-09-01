# 15-minute client demo script

Minute by minute. Which page, which visual, what you say, and the question you
ask at the end of each section.

**The shape of it:** three minutes of framing, nine minutes across four pages,
three minutes to open the scope conversation. The ML section is the one that
wins the work, so it gets the most room and it goes last but one — never last,
because you want to end on their business, not your monitoring.

**Before you start**
- Report open on **Ops Control Room**, all slicers cleared.
- Date slicer showing the full range: 01 Jan 2025 to 31 Aug 2026.
- The three FastAPI services running (`make serve`) with
  `http://127.0.0.1:8001/docs` open in a background tab. You may not use it. It
  is there so that if someone asks "is this a real model or a picture of one",
  the answer takes fifteen seconds instead of a follow-up email.
- Have `validate.py` output in a terminal tab for the same reason.

**One rule for the whole fifteen minutes:** say "synthetic" in the first ninety
seconds and never let it be a surprise later. Being caught having implied real
data is the only way to lose this meeting badly.

---

## Minutes 0–2 — Framing

*(No screen share yet, or the title page only.)*

> "Before I show you anything, one thing up front: **this data is synthetic and
> I generated it.** There is no real Seek My Service and no real customer
> records anywhere in this.
>
> That is deliberate, and it is the point rather than a limitation. This was my
> Master's thesis, and the question was whether monitoring can catch a silent
> pipeline failure before accuracy shows it. To measure that you need a dataset
> where you know exactly when the failure happened — real data does not come
> labelled that way. So I generated one, broke it on a known date, and measured
> which signal noticed first.
>
> Everything except the rows is the real thing: source schema, transformations,
> semantic model, dashboards, the ML services, the monitoring.
>
> What is real is the structure. Twenty actual Bengaluru localities with the
> right pincodes and zones. Both monsoons, not just the south-west one. The
> festival calendar. The Indian fiscal year. UPI at 57% of payments, because
> that is what India actually looks like.
>
> When we work together, the same pipeline points at your database and
> everything you are about to see is generated from your numbers instead of
> mine.
>
> Twenty months of a marketplace like yours. Roughly 58,000 bookings, 850
> technicians, 24,000 customers, eight ML models in production. Four pages.
> I want to show you three things the data says that I did not expect, and one
> failure that took four months to become visible."

**Do not** walk through the architecture yet. They have not earned the interest
in it and you have not earned the right to spend their time on it.

---

## Minutes 2–5 — Ops Control Room

**Open on the KPI strip.** Point at **SLA Met 81.1%**. It is red, by design.

> "Service level is 81% against a 90% promise. That is the headline, and on its
> own it is not very useful — it tells you there is a problem and nothing about
> where."

**Move to visual 1.9, the scatter.** This is the most important thirty seconds
on the page. Let them look at it before you explain it.

> "Every dot here is one day. Across the bottom is how busy that day was
> compared with its own trailing 30-day average. Up the side is what proportion
> of jobs missed the arrival promise.
>
> There is your answer. Breach rate is 14% on a normal day and **32% on the
> busiest fifth of days**. Time to assign goes from 11 minutes to nearly 20.
> Average rating drops from 4.32 to 4.04 — which then goes into the reviews the
> next customer reads.
>
> This is not a technician quality problem. You will not fix it with
> performance management. It is a dispatch capacity problem on days that are
> **predictable in advance** — weekends, festival windows, and the first heavy
> rain after a dry spell."

**Drop to visual 1.10, the zone × month matrix.** Let the red cells do the work.

> "And it is not evenly spread. Every red cell is a zone-month where more than a
> quarter of jobs missed the window."

**Then 1.12, the slowest areas table.**

> "The four slowest areas to dispatch are all tier-C. Supply density there is
> about half the core. Hold that thought — it comes back on the next page."

> ### Ask: *"When a Saturday in the monsoon goes badly, how do you find out — and how long after?"*

Their answer tells you whether they have any operational feedback loop at all.
Most do not, and they will tell you so in a way that is useful later.

---

## Minutes 5–8 — Demand Intelligence

**Start with the funnel, 2.6.**

> "1.15 million searches become 327,000 leads, become 200,000 quotes, become
> 58,000 jobs. Five percent end to end."

**Move to the seasonality line, 2.8.** This is the page's charm, so slow down.

> "This is Bengaluru weather as a demand driver. AC servicing goes from 335 jobs
> in February to 1,254 in April — nearly four times. Plumbing goes from 471 in
> May to 1,026 in August, when the monsoon breaks.
>
> And watch painting. It goes *down*, 209 to 142, because nobody paints an
> exterior in July. Then look at October — painting and deep cleaning both spike
> for Diwali.
>
> Here is the number I would take into a planning meeting. The 25-day Diwali
> window does **+40% bookings and +150% GMV** against the 25 days before it.
> ₹85 lakh against ₹34 lakh. It is your single biggest revenue window of the
> year and, as far as the data shows, it is staffed like an ordinary October."

**Then the conversion matrix, 2.9.**

> "This is where the money leaks. Tier-A areas convert search to booking at
> 5.9%. Tier C converts at 3.2%. The interest is there — the searches happen —
> it just does not turn into a job. Closing half that gap is about 2,300
> bookings over this period."

**Finish on 2.10, the acquisition chart.** This is the slide most likely to
change a decision this quarter, so land it cleanly.

> "A referred customer rebooks 79% of the time and is worth ₹7,793 over their
> life. A Meta Ads customer rebooks 40% of the time and is worth ₹3,506.
>
> Meta Ads is your second-largest source of new customers. On cost per first
> booking it probably looks like your best channel. On cost per rupee of
> lifetime value it is your worst."

> ### Ask: *"Does anyone currently look at acquisition channel and repeat rate on the same screen?"*

The answer is almost always no, and it is almost always the moment they lean in.

---

## Minutes 8–11 — Supply Health

**KPI strip. Point at utilisation: 17.0%.**

> "Seventeen percent. Your first instinct is that you have three times the
> technicians you need. That is not quite what is happening."

**Go to the scatter, 3.7.**

> "833 technicians who did at least one job. The **top 10% take 43% of all
> jobs**. The bottom half take 11%. Eleven people on the roster never got a
> single job.
>
> Platinum technicians run at 25% utilisation, Bronze at 10%. The ranker
> concentrates work on proven people — which is right for the customer, and
> means most of the supply you recruited is barely working."

**Now the point that pays for the engagement. Go to 3.8, the area gap matrix**,
and talk over it.

> "Split utilisation by trade and season and it stops being an oversupply story
> and becomes an allocation story.
>
> In the monsoon, plumbers go from 15.6% to **24.5%**. Pest control jumps 59%.
> Electricians 38%. Meanwhile painters drop to 11.4% and AC technicians to
> 14.9%.
>
> So during the four months when your plumbers are stretched and your service
> level is worst, you have painters and AC technicians sitting idle. You do not
> have a supply shortage. **You have idle capacity wearing the wrong tool belt.**
>
> Cross-training some of the painting roster in basic leak and drainage work
> costs a training programme. Recruiting plumbers costs a recruitment pipeline,
> every year, forever."

> ### Ask: *"What does it currently cost you to onboard one new technician, all in?"*

Whatever they say, cross-training is cheaper, and now they have said the number
out loud themselves.

---

## Minutes 11–14 — ML Model Health

This is the section that separates you from a dashboard contractor. It has a
beginning, a middle and an end, and you should tell it as a story with four
beats, in order.

**Open on the scorecard, 4.6.**

> "Eight models in production. Each one against its own goal, in its own units.
> Green, amber, red."

**Move to 4.7, the MAPE line. Do not explain it yet — let them read it.**

> "This is the demand forecaster. Flat at 9% for over a year. Then in June it
> roughly doubles. Then in late July it comes straight back down.
>
> Something happened. Let me show you what, in the order it actually happened —
> which is not the order you would guess."

**Beat 1 — go to 4.9, the training data age chart.** This is the reveal.

> "This is how old the data behind the live model was, day by day. That sawtooth
> is the weekly retrain doing its job — climbs to seven days, resets, climbs
> again. Perfectly healthy.
>
> Now look at the **15th of March**. The sawtooth stops and it just climbs. The
> scheduled retrain job stopped succeeding, and **nothing alerted**, because the
> model kept returning predictions the entire time. It looked completely
> healthy. Accuracy stayed at 9%.
>
> It got to **126 days** old."

**Beat 2 — back to 4.7.**

> "It stayed invisible until June, when the monsoon arrived and the demand
> pattern changed. Plumbing nearly doubled, painting collapsed. And a model
> fitted on three-month-old relationships could not cope. Accuracy went from 9%
> to 19%."

**Beat 3 — 4.8, the PSI chart.**

> "This is the drift monitor. It sits around 0.05 for fifteen months, then
> crosses the 0.25 alert threshold in mid-June and stays there. That is the
> alarm that finally fired."

**Beat 4 — back to 4.7 and 4.9 together.**

> "Retrain lands on the 20th of July. Version goes 2.3.0 to 2.4.0, the age
> counter resets to zero, and accuracy is back to 10% within four days.
>
> Silent pipeline failure. Latent risk. Regime change exposes it. Drift
> monitoring catches it. Retrain. Recovery.
>
> **The gap that matters is March to June.** It was broken for four months and
> only looked broken for six weeks. And the metric that would have caught it in
> March is not sophisticated — it is *how old is the training data*. One column.
> Costs nothing to compute. Almost nobody monitors it."

**If you have thirty seconds left, this is the best one you have.** Point at the
two KPI tiles side by side: MAPE 10.4%, WAPE 37.2%.

> "One more. This model's MAPE is 10.4%, which looks fine. Its WAPE is 37.2%.
> Both are correct.
>
> The difference is **11,004 cells where the model forecast demand and nothing
> arrived at all** — about 14,800 phantom jobs against 55,600 real ones. MAPE
> literally cannot see them, because a cell with zero actual jobs has nothing to
> divide by, so it gets dropped from the average.
>
> Every one of those is a van sent to an empty street. If you only ever report
> MAPE, this model looks healthy — for the entire twenty months."

**What it would have cost.** Keep this proportionate; do not invent a number.

> "I am not going to put a rupee figure on it, because that needs your cost base
> and not my guesses. But the shape is: four months of supply pre-positioned
> against forecasts that were quietly degrading, in the busiest season of the
> year, on your most business-critical model. Whatever your cost per misallocated
> technician-day is, multiply it by four months."

---

## Minutes 14–15 — Close

Stop sharing. Look at them.

> "Three things the data said. Your monsoon problem is allocation, not headcount.
> Your best-performing acquisition channel by volume is your worst by value.
> And your service level failures are concentrated on days you could have seen
> coming.
>
> All three came out of the same model, and none of them needed new data
> collection — they needed the data you already have, joined properly."

### The three questions that open the scope conversation

Ask these in this order. Each one is designed so that the honest answer creates
the next piece of work.

1. **"Which of those three would you want to be true first — and how would you
   know if it were?"**
   Makes them pick a priority and, more usefully, forces them to describe the
   metric they would need. That metric is the first deliverable.

2. **"Who in your team would open this on a Monday morning, and what would they
   need it to answer in the first thirty seconds?"**
   Separates "a dashboard exists" from "a dashboard is used". The answer defines
   the landing page and tells you whether this is one engagement or a retainer.

3. **"Of your eight models, how would you find out today if one of them had
   stopped being retrained?"**
   You already know the answer is that they would not. Ask it anyway, and ask it
   last. It is the question that turns a reporting project into an ML platform
   project, and it is far more persuasive when they say it than when you do.

---

## If they ask hard questions

**"So is this real, or did you make it up?"**
Both, and be precise about which is which. The *data* is generated — say that
plainly, you have already said it once in minute one. The *architecture,* the
modelling decisions, the measure library and the monitoring approach are the
real thing. The data is generated because the thesis needed a known failure date
to measure detection against — you cannot prove a monitor caught something early
if you do not know when it started. Say that plainly; it is a stronger answer
than an apology, and it shows you designed an experiment rather than assembled a
demo.

**"Is this a real model or a picture of a model?"**
Switch to the browser tab. `http://127.0.0.1:8001/docs`. Run a live prediction
against Whitefield plumbing. Fifteen seconds. Then say: "Held-out MAPE is 13.7%
at the grain a planner actually acts on. I can show you the training code."

**"How do I know the data is right?"**
Terminal tab. `python validate.py`. Sixteen checks: foreign keys, date
continuity, money rules, chronology, funnel monotonicity, capacity
reconciliation. Then be honest: "It caught a real bug while I was building this
— six technicians taking jobs after their churn date. That is what the checks
are for."

**"Can we get Copilot in Power BI?"**
Not on this setup. Copilot needs paid Fabric F2 or higher, or Premium P1
capacity. Premium Per User alone does not unlock it. Everything I have shown you
is built by hand and needs Pro licences for viewers only. If Fabric capacity is
something you want, that is a separate conversation with a real monthly cost
attached, and I would not recommend it before the fundamentals are in place.

**"How long to point this at our database?"**
Honest answer: the transformation layer is two to three weeks against a real
schema, because real schemas are messier than this one and the surprises are
always in the joins. The semantic model and report move over in days, because
they are already written down. See `SOW_AND_PRICING.md`.

**"Your matching model scores 0.95. Is that not too good?"**
Yes, and I say so in the model card. The generator assigns jobs using a known
function of the same features the model sees, so it is recovering a process
rather than learning a messy human one. On your data expect materially worse.
I would rather tell you that now than have you find it in month three.
