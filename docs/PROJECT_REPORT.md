# Seek My Service — Project Report

---

**Title:** Early Detection of Silent Machine Learning Pipeline Failure Through
Operational Monitoring: A Marketplace Analytics Case Study

**Student Name:** Abhishek Prasad

**Programme:** MSc Informatik

**Institution:** IU Internationale Hochschule, Berlin, Germany

**Submission Date:** *(to be completed)*

---

## Acknowledgement

I would like to express my gratitude to my supervisor for their guidance
throughout this project, and to the authors whose published work on machine
learning system reliability, dimensional modelling and forecast evaluation
provided the theoretical foundation for this study. I also thank my family and
friends for their encouragement during its completion.

---

## Abstract

Machine learning systems fail differently from conventional software. A web
service that breaks stops responding; a model that breaks continues to return
predictions, and those predictions remain plausible long after the system that
produces them has stopped being maintained. This project investigates whether
operational monitoring signals can detect such a silent failure earlier than the
accuracy metrics conventionally used to supervise deployed models.

An end-to-end analytics and machine learning platform was constructed for a
simulated home-services marketplace operating in Bengaluru, India, comprising
57,973 bookings, 24,000 customers and 850 service professionals across twenty
months. The platform includes a dimensional data warehouse of eleven tables, a
semantic layer of 119 measures, two dashboard implementations, three trained
machine learning services, and a monitoring layer covering eight models.

A pipeline failure was deliberately injected at a known date: the scheduled
retraining job for the demand forecasting model ceases to succeed on 15 March
2026. Detection performance was then measured for two classes of signal —
accuracy metrics and operational metrics — against that known ground truth.

The principal finding is that training-data age, an operational metric requiring
no model evaluation and no labelled outcomes, diverged from its normal pattern on
the day of failure, whereas the model's accuracy metric showed no degradation for
seventy-eight days. Accuracy only deteriorated when an exogenous seasonal regime
change exposed the stale model. A secondary finding concerns metric selection:
the mean absolute percentage error of the forecasting model was 10.4%, while its
weighted absolute percentage error over the same predictions was 37.2%. The
divergence is attributable to 11,004 forecast cells in which demand was predicted
and none occurred, a failure mode that MAPE is mathematically incapable of
observing.

The study concludes that model monitoring should include at least one signal that
does not depend on outcome labels, and that percentage-error metrics should not
be reported without a companion metric that accounts for zero-actual cases.

**Keywords:** machine learning operations, model monitoring, concept drift, data
drift, dimensional modelling, demand forecasting, forecast evaluation, business
intelligence, gradient boosting, marketplace analytics

---

## Table of Contents

**Chapter 1: Introduction**
1.1 Background
1.2 Problem Statement
1.3 Research Aim
1.4 Research Objectives
1.5 Research Questions
1.6 Research Gap
1.7 Structure of Research
1.8 Chapter Summary

**Chapter 2: Literature Review**
2.1 Introduction
2.2 Technical Debt in Machine Learning Systems
2.3 Concept Drift and Data Drift
2.4 Monitoring Practice for Deployed Models
2.5 Forecast Accuracy Measurement
2.6 Gradient Boosting for Tabular Prediction
2.7 Dimensional Modelling and the Semantic Layer
2.8 Synthetic Data as an Evaluation Instrument
2.9 Research Gap Identified in the Literature

**Chapter 3: Methodology**
3.1 Research Design
3.2 Data Generation
3.3 Warehouse and Semantic Layer Construction
3.4 Model Development
3.5 Failure Injection and Measurement Protocol
3.6 Validation Strategy
3.7 Ethical Considerations
3.8 Chapter Summary

**Chapter 4: Discussion and Analysis**
4.1 Introduction
4.2 Overview of the Dataset
4.3 Findings
4.4 Interpretation of Findings
4.5 Discussion of Findings
4.6 Limitations of Findings
4.7 Chapter Summary

**Chapter 5: Conclusion and Recommendations**
5.1 Introduction
5.2 Summary of Key Findings
5.3 Limitations of Study
5.4 Link to Research Questions and Objectives
5.5 Recommendations
5.6 Reflections in First Person

**References**

**Appendix 1: Declaration of Authenticity**
**Appendix 2: Artefact Inventory**
**Appendix 3: Validation Output**

---

## List of Figures

| Figure | Title |
|---|---|
| Figure 1 | Star schema of the analytical model |
| Figure 2 | Operations dashboard: service level against capacity strain |
| Figure 3 | Capacity strain versus SLA breach, daily observations |
| Figure 4 | Seasonal demand by service category |
| Figure 5 | Technician utilisation by trade and season |
| Figure 6 | Model health dashboard: the four-beat failure sequence |
| Figure 7 | Training-data age, showing divergence from 15 March 2026 |
| Figure 8 | Forecast error: MAPE against WAPE |

## List of Abbreviations

| Term | Expansion |
|---|---|
| API | Application Programming Interface |
| AUC | Area Under the Receiver Operating Characteristic Curve |
| CSV | Comma-Separated Values |
| DAX | Data Analysis Expressions |
| ETL / ELT | Extract-Transform-Load / Extract-Load-Transform |
| GBDT | Gradient Boosted Decision Trees |
| GMV | Gross Merchandise Value |
| MAE | Mean Absolute Error |
| MAPE | Mean Absolute Percentage Error |
| ML | Machine Learning |
| MLOps | Machine Learning Operations |
| NDCG | Normalised Discounted Cumulative Gain |
| OLTP | Online Transaction Processing |
| PSI | Population Stability Index |
| RLS | Row-Level Security |
| SLA | Service Level Agreement |
| UPI | Unified Payments Interface |
| WAPE | Weighted Absolute Percentage Error |

---

# Chapter 1: Introduction

## 1.1 Background

The operational deployment of machine learning has outpaced the discipline of
maintaining it. Organisations that have successfully moved models from
experimentation into production frequently discover that the harder problem is
not building the model but knowing, at any given moment, whether it is still
working.

This difficulty is structural rather than incidental. Conventional software
communicates its own failure. A service that cannot reach its database returns an
error; a process that exhausts memory terminates; a malformed request produces a
status code that monitoring systems are designed to notice. Machine learning
systems do not behave this way. A model whose training data has become
unrepresentative of current conditions continues to accept requests, continues to
execute, and continues to return outputs of the correct type and plausible
magnitude. Nothing in the serving path distinguishes a well-calibrated prediction
from a badly calibrated one.

Sculley et al. (2015) characterised this property as a form of technical debt
particular to machine learning, noting that ML systems possess "all of the
maintenance problems of traditional code plus an additional set of ML-specific
issues," and that these issues are frequently invisible at the level of the
system boundary. Subsequent work by Breck et al. (2017) proposed a production
readiness rubric in which monitoring occupies a central position, and Paleyes et
al. (2022), surveying deployment case studies across industries, found monitoring
and maintenance to be among the most consistently underdeveloped stages of the
machine learning lifecycle.

The commercial context in which this project is situated is the online
home-services marketplace: a platform that connects customers requiring domestic
work with independent tradespeople able to perform it. Such platforms are
operationally demanding. They must forecast demand in order to position supply,
rank available workers against incoming jobs, and price work whose true cost is
not known until the worker arrives. Each of these is a machine learning problem,
and each is executed continuously and at volume.

Bengaluru, the setting for this study, presents a demand environment with unusual
and pronounced structure. The city experiences two distinct monsoon seasons — the
south-west monsoon from June to September and the north-east monsoon from
mid-October to late November — and the seasonal calendar includes major festivals
that materially alter consumption. These produce demand patterns that are
predictable in aggregate but that shift the relationship between predictor
variables and outcomes several times a year. A city with two monsoons is,
consequently, a natural laboratory for studying model drift.

## 1.2 Problem Statement

The problem addressed by this project can be stated precisely.

Deployed machine learning models are conventionally monitored through accuracy
metrics: error rates, classification scores, ranking measures. These metrics
share a dependency that is rarely made explicit — they require ground truth.
Computing the error of a demand forecast requires knowing what demand actually
occurred, which is available only after the forecast horizon has elapsed. In
practice this means accuracy monitoring is retrospective, and the interval
between a system's failure and the observability of that failure is bounded below
by the horizon of the prediction.

More seriously, accuracy metrics only move when the model's outputs become wrong.
A model may be broken in the sense that it is no longer being maintained, no
longer being retrained, and no longer receiving current data — and yet remain
accurate, provided the relationship it learned continues to hold. Its accuracy
communicates the stability of the environment, not the health of the pipeline.
The two coincide only until the environment changes.

The consequence is a detection gap: the interval between the moment a pipeline
ceases to function correctly and the moment any monitored metric reflects it.
During that interval the organisation believes it is operating a maintained
model. This project sets out to measure that gap under controlled conditions and
to determine whether it can be closed.

## 1.3 Research Aim

To determine whether operational monitoring signals that do not depend on ground
truth can detect a silent machine learning pipeline failure earlier than
conventional accuracy metrics, and to quantify the difference in detection
latency.

## 1.4 Research Objectives

1. To construct an end-to-end analytics and machine learning platform of
   sufficient realism that monitoring behaviour observed within it is
   generalisable to production systems.
2. To develop and evaluate three machine learning services representative of
   marketplace operations: demand forecasting, worker ranking, and dynamic
   pricing.
3. To implement a monitoring layer capturing both accuracy metrics and
   operational metrics for eight deployed models.
4. To inject a pipeline failure at a known date and measure the detection latency
   of each class of monitoring signal.
5. To evaluate whether the accuracy metric conventionally applied to demand
   forecasting adequately represents the model's operational performance.
6. To derive practical monitoring recommendations from the observed results.

## 1.5 Research Questions

**RQ1.** Can an operational monitoring signal that requires no ground truth
detect a silent pipeline failure earlier than an accuracy metric, and by what
margin?

**RQ2.** Under what conditions does a stale model continue to perform acceptably,
and what causes that performance to deteriorate?

**RQ3.** Does mean absolute percentage error, the conventional accuracy metric
for demand forecasting, adequately characterise forecast quality in a setting
containing zero-demand observations?

**RQ4.** What monitoring configuration would have detected the injected failure
at the earliest opportunity, and what does it cost to implement?

## 1.6 Research Gap

The literature establishes clearly that monitoring is necessary. Sculley et al.
(2015) identify its absence as a source of technical debt; Breck et al. (2017)
include it in a production readiness rubric; Gama et al. (2014) provide a
comprehensive treatment of drift detection methods. Commercial and open-source
tooling for drift monitoring is mature and widely available.

Three gaps remain, and this project addresses them.

**First, detection latency is asserted rather than measured.** The literature
argues that monitoring detects problems earlier than the alternative, but rarely
quantifies the interval. This is a consequence of the evidence base: production
case studies report incidents after the fact, when the moment of failure is
inferred rather than known. Without a known failure time, latency cannot be
computed.

**Second, the distinction between outcome-dependent and outcome-independent
signals is under-examined.** Drift detection literature concentrates on
distributional comparison of inputs or outputs. Pipeline health signals —
whether the retraining job succeeded, how old the training data is, whether the
feature pipeline is delivering complete records — are treated as infrastructure
concerns rather than model monitoring, despite being available at zero
evaluation cost and with zero delay.

**Third, forecast evaluation practice in operational settings is inherited rather
than examined.** MAPE is the default reporting metric for demand forecasting.
Hyndman and Koehler (2006) demonstrated two decades ago that percentage errors
are undefined when the actual value is zero and are asymmetric in their treatment
of over- and under-prediction, yet the metric remains standard. Its behaviour in
sparse operational settings, where zero-demand observations are common rather
than exceptional, warrants direct measurement.

## 1.7 Structure of Research

**Chapter 2** reviews the literature on machine learning technical debt, concept
drift, monitoring practice, forecast evaluation, gradient boosting on tabular
data, and dimensional modelling, concluding with the identified gap.

**Chapter 3** describes the methodology: the design rationale for a synthetic
data instrument, the construction of the dataset and warehouse, the development
of three machine learning services, the failure injection protocol, and the
validation strategy.

**Chapter 4** presents and interprets the findings across five themes, discusses
them in relation to the literature, and states their limitations.

**Chapter 5** summarises the conclusions, links them explicitly to the research
questions, offers recommendations, and reflects on the process.

## 1.8 Chapter Summary

This chapter has established that machine learning systems fail silently, that
this property creates a measurable interval between failure and detection, and
that the interval has not been directly quantified in the existing literature
because production incidents do not come with known failure times. The research
aim, objectives and questions have been stated, and the gap the project addresses
has been specified in three parts: unmeasured detection latency, the neglect of
outcome-independent monitoring signals, and unexamined forecast evaluation
practice.

---

# Chapter 2: Literature Review

## 2.1 Introduction

This chapter reviews the theoretical and empirical foundations of the study. It
proceeds from the general characterisation of machine learning systems as
maintenance liabilities, through the specific mechanisms by which deployed models
degrade, to the practices proposed for detecting that degradation. It then
examines forecast evaluation metrics, the modelling techniques appropriate to
tabular operational data, and the dimensional modelling tradition on which the
analytical layer of the artefact is founded. It concludes by locating the gap
addressed by this project.

## 2.2 Technical Debt in Machine Learning Systems

The foundational treatment of maintenance burden in machine learning systems is
Sculley et al. (2015), who applied the software engineering metaphor of technical
debt to production machine learning. Their central argument is that machine
learning systems accumulate a distinct class of liability arising from the
entanglement of code, data and model, and that this liability is difficult to
observe through the interfaces by which conventional software is monitored.

Several of their identified anti-patterns bear directly on this project.
*Entanglement* describes the property that changing any input feature changes the
significance of all others, so that no component can be reasoned about in
isolation. *Pipeline jungles* describe accreted data preparation chains whose
failure modes are poorly understood. Most relevant here is their observation that
machine learning systems frequently lack the plumbing that conventional systems
take for granted — that the absence of straightforward monitoring is not an
oversight in any particular system but a systematic characteristic of the field.

Breck et al. (2017) developed this into a practical instrument, proposing
twenty-eight specific tests across data, model, infrastructure and monitoring.
Their monitoring section explicitly includes tests for training data staleness
and for the invariance of serving and training feature distributions, which
supports the position taken in this project that pipeline health belongs within
model monitoring rather than adjacent to it.

Paleyes et al. (2022) surveyed published deployment case studies and reported
that monitoring and maintenance were among the least developed lifecycle stages
in practice, with organisations frequently discovering degradation through
downstream business impact rather than through instrumentation.

## 2.3 Concept Drift and Data Drift

The mechanism by which a deployed model loses accuracy without any change to its
own parameters is described in the literature as drift. Gama et al. (2014)
provide the standard taxonomy, distinguishing between changes in the input
distribution and changes in the relationship between inputs and target.

The distinction matters for monitoring design. Input distribution change is
observable immediately and without labels, by comparing the distribution of
current inputs against the training distribution. Change in the input-output
relationship is observable only through outcomes, and therefore only after those
outcomes are known.

Gama et al. further distinguish drift by temporal profile — sudden, gradual,
incremental and recurring. The seasonal structure examined in this project is
best characterised as recurring drift: the monsoon arrives annually and shifts
the demand regime in a manner that is predictable in timing though not
necessarily in magnitude. Recurring drift is significant for the present study
because it establishes that the exposure of a stale model is itself scheduled: if
a model degrades when the regime changes, and the regime changes seasonally, then
the consequences of a maintenance lapse are deferred to a date that can be
anticipated in advance.

The population stability index is widely used in applied settings, particularly
in credit risk, as a summary measure of distributional shift, with thresholds
around 0.1 and 0.25 conventionally taken to indicate moderate and significant
change respectively. These thresholds are heuristic rather than derived, a point
returned to in Chapter 4.

## 2.4 Monitoring Practice for Deployed Models

Monitoring practice for deployed models divides into three broad categories.

**Performance monitoring** tracks the model's accuracy against ground truth. It
is the most direct measure of whether the model is doing its job and the most
delayed, since it requires outcomes to be observed.

**Data monitoring** tracks the statistical properties of inputs and outputs
without reference to outcomes. It is available immediately and detects a
necessary but not sufficient condition for degradation: inputs may shift without
accuracy suffering, and accuracy may suffer without inputs shifting.

**Operational monitoring** tracks the system that produces predictions —
latency, throughput, error rates, and the state of the training pipeline. This
category is conventionally treated as infrastructure monitoring rather than model
monitoring, and it is the category this project argues is under-used.

The distinction relevant to this study is not between these three categories as
such, but between signals that require ground truth and those that do not.
Training-data age falls into the operational category and requires nothing but a
timestamp comparison; it is available continuously, at no computational cost, and
with no delay. Its neglect in monitoring practice appears to be a matter of
convention rather than of technical limitation.

## 2.5 Forecast Accuracy Measurement

The measurement of forecast accuracy has an extensive literature, and the
limitations of percentage-based error metrics are long established.

Hyndman and Koehler (2006) provide the standard critique. They identify that MAPE
is undefined when the actual value is zero, that it is asymmetric — penalising
over-forecasting more heavily than under-forecasting of equivalent absolute
magnitude — and that it can favour models that systematically under-predict. They
propose the mean absolute scaled error as an alternative that remains defined
across zero observations.

Despite this critique being two decades old, MAPE remains the default reporting
metric in operational demand forecasting, appearing in service level agreements,
vendor benchmarks and internal targets. The weighted absolute percentage error,
which divides total absolute error by total actual volume, is sometimes reported
alongside it and has the property of remaining defined when individual actuals are
zero, since only the aggregate denominator must be non-zero.

The behaviour of these metrics diverges most sharply in sparse settings. Where
demand is forecast at a fine grain — a single product in a single location on a
single day — zero-demand observations are common. Under MAPE these observations
are excluded from the average, since they cannot be computed. Under WAPE they
contribute their absolute error to the numerator while contributing nothing to
the denominator. The two metrics therefore answer different questions, and the
difference between them is informative in a way that is examined directly in
Chapter 4.

Hyndman and Athanasopoulos (2021) provide the standard contemporary treatment of
forecasting practice, including the observation that forecast evaluation should
be conducted at the grain at which decisions are made, a principle applied in the
evaluation protocol of this project.

## 2.6 Gradient Boosting for Tabular Prediction

The choice of model family for the three services was informed by the empirical
literature on tabular prediction.

Gradient boosted decision trees, formalised in the implementations of Chen and
Guestrin (2016) and Ke et al. (2017), remain the dominant approach for structured
tabular data. Grinsztajn et al. (2022) examined the persistence of this dominance
directly, finding that tree-based models continue to outperform neural
architectures on typical tabular datasets, attributing this to the tendency of
neural networks toward overly smooth decision boundaries, their sensitivity to
uninformative features, and the rotational invariance that discards the meaning
carried by individual columns.

For ranking problems, the LambdaMART family described by Burges (2010) provides
the standard approach, optimising a ranking objective directly rather than
optimising a pointwise prediction and sorting the results.

For prediction intervals rather than point estimates, quantile regression as
introduced by Koenker and Bassett (1978) provides an approach that makes no
distributional assumption, estimating specified quantiles of the conditional
distribution directly.

One limitation of tree-based models is directly relevant to this project: a
decision tree can only predict values present in its training data, and therefore
cannot extrapolate a trend. Where a target grows monotonically over time, a tree
model trained on earlier data will systematically under-predict later data. The
standard remedy, adopted here, is to model a ratio to a known baseline rather
than an absolute level.

## 2.7 Dimensional Modelling and the Semantic Layer

The analytical layer of the artefact follows the dimensional modelling tradition
established by Kimball and Ross (2013). The star schema — a central fact table at
a defined grain surrounded by denormalised dimension tables — is adopted for its
query performance characteristics and, more importantly for this project, for its
comprehensibility to non-specialist users.

Two Kimball principles are load-bearing in the present artefact. The first is
that fact table grain must be declared before any other design decision, since
every subsequent choice depends on it. The second is that of conformed
dimensions: where multiple fact tables share a dimension, that dimension must be
identical across them, permitting facts to be compared without direct
relationships between fact tables.

The semantic layer — the collection of named, reusable calculations defined over
the dimensional model — is the mechanism by which business definitions are
centralised. Where a definition such as "active customer" is expressed once in a
semantic layer rather than repeatedly in individual reports, divergence between
reports is prevented structurally rather than by convention.

## 2.8 Synthetic Data as an Evaluation Instrument

The use of synthetic data in this study is methodological rather than
substitutive, and the distinction requires justification.

Synthetic data is commonly employed where real data is unavailable, restricted by
privacy regulation, or insufficient in volume. In such applications the synthetic
dataset is a proxy, and its value depends on its fidelity to the real
distribution it replaces.

The use here is different. The research question concerns detection latency: the
interval between a failure occurring and a monitoring signal responding to it.
Measuring an interval requires both endpoints to be known. In production data the
second endpoint is observable but the first is not — incident post-mortems infer
the moment of failure, frequently incorrectly, and always after the fact.

A synthetic instrument permits the first endpoint to be specified rather than
inferred. The failure is placed at a chosen date; detection is then measured
against it exactly. This is the same logic by which a fault is injected into a
system under test rather than waited for. The validity of the resulting
measurement depends not on the dataset resembling any particular real
marketplace, but on the failure mechanism and the monitoring signals behaving as
they would in a real system.

## 2.9 Research Gap Identified in the Literature

The review supports the gap stated in Section 1.6. Monitoring is established as
necessary and its methods are well developed, but detection latency is asserted
rather than measured, because the evidence base consists of production incidents
whose failure times are unknown. Outcome-independent pipeline signals are
recognised in production readiness rubrics yet are not treated as first-class
monitoring instruments. Forecast evaluation practice continues to rely on a
metric whose limitations were documented two decades ago, without direct
measurement of the consequences in sparse operational settings.

---

# Chapter 3: Methodology

## 3.1 Research Design

The study adopts a **design science** approach, in which knowledge is produced
through the construction and evaluation of an artefact. The artefact is a
complete analytics and machine learning platform; the evaluation is a controlled
experiment conducted within it.

The design is quantitative and experimental. A failure is injected at a known
time and detection latency is measured for two classes of monitoring signal. The
independent variable is the class of signal; the dependent variable is the
interval between failure injection and signal divergence.

The requirement for a known failure time determines the choice of a synthetic
data instrument, for the reasons set out in Section 2.8.

Determinism was treated as a design requirement rather than a convenience. The
entire dataset is generated from a single fixed pseudo-random seed, so that
regeneration produces a byte-identical result. Every figure reported in Chapter 4
is therefore reproducible, and any reader may verify it by executing the
generation and validation programs.

## 3.2 Data Generation

A dataset was generated representing twenty months of operation — 1 January 2025
to 31 August 2026, 608 consecutive days — of a home-services marketplace in
Bengaluru offering 37 services across eight trade categories in 20 localities.

### 3.2.1 Structural realism

Certain elements were taken from reality rather than generated. The 20 localities
are actual Bengaluru neighbourhoods with correct postal codes, administrative
zones and approximate coordinates. Both monsoon seasons are modelled. The
festival calendar and the Indian fiscal year, running April to March, are
represented. Price points were benchmarked against prevailing rates in the city,
and the payment mix reflects the dominance of the Unified Payments Interface in
Indian consumer transactions.

### 3.2.2 Behavioural modelling

Relationships in the data were generated as causal chains rather than sampled
correlations. Rainfall suppresses exterior painting and increases plumbing
demand. Heavy-rain days raise cancellation rates, which reduce completion rates,
which reduce revenue. Daily volume above the trailing thirty-day mean lengthens
time-to-assignment, which increases service level breaches, which reduces
customer ratings.

Seasonal multipliers are declared as configuration and composed multiplicatively
where windows overlap. Exterior painting during the overlap of the Diwali
festival window and the north-east monsoon therefore carries a multiplier of
2.4 × 0.65 = 1.56: demand rises for the festival but rain continues to restrain
it. This value is asserted by a unit test rather than by a comment.

### 3.2.3 Consistency by construction

Two design decisions eliminate categories of inconsistency that synthetic
datasets commonly exhibit.

Bookings are assigned to technicians by consuming actual capacity slots from a
capacity calendar generated in advance. The daily capacity fact therefore
reconciles exactly to the booking fact, rather than approximately.

The conversion funnel is constructed backwards from realised bookings. Quotes are
derived from bookings, leads from quotes, and searches from leads, each with
tier-dependent conversion rates. Monotonicity of the funnel holds by construction
and cannot be violated.

## 3.3 Warehouse and Semantic Layer Construction

A dimensional model of eleven tables was constructed: six dimensions and five
facts, arranged as a star schema with conformed date, area and service
dimensions. No relationships exist between fact tables.

A source-system schema was specified in PostgreSQL representing the transactional
database from which such data would originate, including an append-only booking
event log and a prediction store. A staging layer performs renaming, typing and
flattening; a mart layer holds business definitions. Business logic is expressed
once, in the mart layer.

A semantic layer of 119 measures was implemented in DAX, organised into eight
display folders, each measure carrying an explicit format string. The measures
were generated from a single declarative source specification, so that the
human-readable library and the deployment script cannot diverge.

Two dashboard implementations were produced over the same semantic definitions: a
Power BI report and a Streamlit web application. Producing both permitted a
practical comparison of the two approaches and provided a cross-check on the
measure definitions, since divergence between the two implementations indicates
an error in one of them. One such divergence was detected and is reported in
Section 4.3.

## 3.4 Model Development

Three services were developed, trained and evaluated.

### 3.4.1 Demand forecasting

The forecasting model predicts total job volume over the following seven days for
each area and service category. The training data comprises a dense daily panel
of 97,280 observations.

Features comprise lagged volumes at 1, 2, 3, 7, 14, 21 and 28 days; rolling means
and maxima over 7, 14 and 28 days; a momentum ratio; calendar features; and the
configured seasonal multiplier both for the observation date and averaged across
the forecast horizon. All lag and rolling features are shifted by one day to
prevent leakage.

Evaluation used a strictly forward temporal split, training on observations prior
to 1 May 2026 and validating on subsequent observations.

An initial specification predicting absolute volume produced a bias of −39.6%.
The cause was diagnosed as the inability of tree ensembles to extrapolate: demand
grows approximately 4.5-fold across the study window, and validation volumes
consequently exceeded any value present in training. The specification was
revised to a Poisson objective with a logarithmic exposure offset equal to seven
times the trailing daily mean, so that the model predicts a multiplier on a known
baseline. Bias fell to −6.8%.

### 3.4.2 Technician ranking

The ranking model orders available technicians for an incoming job. Since the
fact table records only the technician selected, negative examples were
constructed by sampling from technicians who were genuinely available on the same
day. A LambdaMART objective was trained over 14,000 query groups of eight
candidates each. Splitting was performed by query group rather than by row, since
splitting within a group would place a job's selected technician in training and
its rejected candidates in validation, rendering the task trivial.

### 3.4.3 Dynamic pricing

The pricing model comprises three quantile regressors at the 10th, 50th and 90th
percentiles, producing a price band rather than a point estimate, together with a
binary classifier estimating acceptance probability. The quoted amount is
excluded from the band model's features, since predicting the final price from
the quote would be circular.

## 3.5 Failure Injection and Measurement Protocol

The experimental manipulation is the injection of a pipeline failure at a known
date, together with an exogenous regime change at a second known date.

| Date | Event |
|---|---|
| 15 March 2026 | The scheduled weekly retraining job ceases to succeed. No alert is raised; the model continues to serve predictions from its existing version. |
| 1 June 2026 | The south-west monsoon begins. Plumbing demand approximately doubles; exterior painting demand falls. |
| 15 June 2026 | Population stability index crosses the conventional 0.25 alert threshold. |
| 18 June 2026 | Forecast error reaches a degraded plateau. |
| 20 July 2026 | Retraining is restored. Model version increments; training-data age resets. |

Two signal classes were monitored daily throughout:

**Operational signals**, requiring no ground truth: training-data age, feature
null rate, prediction volume, serving latency.

**Accuracy signals**, requiring ground truth: mean absolute percentage error,
weighted absolute percentage error, forecast bias.

Detection latency for each signal is defined as the interval between 15 March
2026 and the first date on which the signal departs materially from its
pre-failure behaviour.

## 3.6 Validation Strategy

Three independent layers of verification were implemented.

**Data integrity.** Sixteen automated checks verify referential integrity across
every fact and dimension, contiguity of the date dimension, money rules including
the identity between platform revenue and commission applied to the final amount,
the confinement of completion-only columns to completed bookings, chronological
consistency, funnel monotonicity, and capacity reconciliation. The build fails if
any check fails.

**Unit and integration testing.** 109 automated tests cover the seasonality
window logic, the feature builders including explicit temporal leakage checks,
the service contracts, and the dashboard pages.

**Cross-implementation comparison.** Headline figures produced by the Streamlit
application were compared against those produced by the validation programme
directly from the source files.

Each layer detected defects that the others did not, and these are reported in
Section 4.3 as a finding in their own right.

## 3.7 Ethical Considerations

No human participants were involved and no personal data was processed. All
records are synthetic, generated from a fixed seed, and no real individual,
organisation or transaction is represented. The fictional nature of the dataset
is stated prominently in the artefact's documentation and in its user interface,
so that no reader may mistake generated figures for empirical observations of a
real business.

The source-system schema was designed to exclude personally identifying
attributes from the analytical layer, demonstrating the data minimisation
principle: the warehouse receives a customer key and behavioural attributes, and
no name, telephone number or email address.

Reporting honesty was treated as an ethical requirement rather than a stylistic
preference. Two of the three models produced results that do not support
deployment, and both are reported with the measured figure, the diagnosis and the
recommended remedy rather than being omitted or tuned until presentable.

## 3.8 Chapter Summary

This chapter has described a design science study in which a complete analytics
and machine learning platform was constructed as the instrument for a controlled
experiment. The synthetic data instrument was justified by the requirement for a
known failure time. The dataset, warehouse, semantic layer and three machine
learning services have been described, together with the failure injection
protocol, the measurement definitions, the three-layer validation strategy and
the ethical position.

---

# Chapter 4: Discussion and Analysis

## 4.1 Introduction

This chapter presents the results. Section 4.2 describes the dataset produced.
Section 4.3 reports findings across five themes. Section 4.4 interprets them,
Section 4.5 discusses them in relation to the literature, and Section 4.6 states
their limitations.

## 4.2 Overview of the Dataset

| Table | Rows | Grain |
|---|---:|---|
| `dim_date` | 608 | One day |
| `dim_service` | 37 | One service |
| `dim_area` | 20 | One locality |
| `dim_professional` | 850 | One technician |
| `dim_customer` | 24,000 | One customer |
| `dim_model` | 8 | One deployed model |
| `fact_bookings` | 57,973 | One booking |
| `fact_pro_capacity` | 324,435 | One technician-day |
| `fact_leads` | 74,286 | Day × area × service |
| `fact_model_metrics` | 3,481 | Day × model |
| `fact_forecast_accuracy` | 47,117 | Day × area × category |

Of 57,973 bookings, 46,394 were completed, a rate of 80.0%. Gross merchandise
value totals ₹124,526,480 with platform revenue of ₹22,536,667, a blended take
rate of 18.1% and an average order value of ₹2,684. Monthly completed volume grows
from 910 in January 2025 to 4,134 in August 2026.

All sixteen integrity checks pass, as do 109 automated tests.

## 4.3 Findings

### Theme 1: Detection latency differs by two and a half months between signal classes

This is the study's principal result and the direct answer to RQ1.

| Signal | Requires ground truth | First divergence | Latency |
|---|---|---|---|
| Training-data age | No | 16 March 2026 | **1 day** |
| Feature null rate | No | 1 June 2026 | 78 days |
| Population stability index | No | 15 June 2026 | 92 days |
| Mean absolute percentage error | Yes | 18 June 2026 | **95 days** |

Training-data age follows a seven-day sawtooth under normal weekly retraining,
rising to seven and resetting. From 16 March 2026 the reset does not occur and
the value climbs monotonically, reaching a maximum of 126 days before retraining
is restored on 20 July 2026. The departure from normal behaviour is unambiguous
on the first day it occurs.

Forecast error remains statistically indistinguishable from its pre-failure level
throughout March, April and May. The pre-incident mean is 8.93%; the model
remained within its 12% target for the entire period during which it was
unmaintained.

**The detection gap is therefore 94 days.**

### Theme 2: A stale model degrades only when the environment changes

The interval between failure and accuracy degradation is explained by the absence
of environmental change during it.

Between March and June the relationship between the seasonal features and demand
remained stable. A model fitted in March described June's conditions adequately
because June's conditions resembled March's. Accuracy was measuring the stability
of the environment, not the health of the pipeline.

The south-west monsoon on 1 June altered the relationship. Plumbing volume rose
from 471 jobs in May 2026 to 1,026 in August; exterior painting fell from 209 to
142. Forecast error rose to a plateau of 19.31%, against a pre-incident baseline
of 8.93%. Following restoration of retraining on 20 July, error recovered to
10.00% within four days.

The staleness was the cause; the monsoon was only the trigger.

### Theme 3: MAPE conceals a failure mode it cannot represent

The forecasting model's mean absolute percentage error across the full period is
**10.4%**. Its weighted absolute percentage error over the same predictions is
**37.2%**.

Decomposition attributes the entire divergence to a single population.

| Cell type | Cells | Absolute error | Actual jobs |
|---|---:|---:|---:|
| Actual demand present | 36,113 | 5,871 | 55,654 |
| **Actual demand absent** | **11,004** | **14,806** | **0** |

11,004 forecast cells contain a prediction of demand where none occurred, and
these cells carry 14,806 jobs of predicted volume — 26.6% of total realised
volume. Excluding them, WAPE is 10.5%, in close agreement with MAPE.

MAPE cannot represent these cells. Percentage error requires division by the
actual value; where the actual is zero the quantity is undefined and the
observation is excluded from the average. The metric is not merely insensitive to
this failure mode but mathematically incapable of expressing it.

The operational interpretation is direct: each such cell represents supply
potentially positioned against demand that did not materialise.

### Theme 4: Model quality assessed honestly, including where it is poor

**Demand forecasting.** At the cell grain, held-out MAPE is 47.7%. A parametric
bootstrap in which actuals are simulated from a perfectly calibrated model
establishes an irreducible noise floor of 44.2%, since the mean target at that
grain is approximately seven jobs and small counts are dominated by Poisson
variance. The model sits 3.5 percentage points above a bound no model can beat.
At the grain at which supply decisions are made — an area, or a category across
the city — held-out MAPE is 13.7% and 14.7% respectively.

**Technician ranking.** NDCG@5 is 0.954 against a target of 0.82. **This result is
optimistic and is not evidence of a well-performing ranker.** The data generator
assigns jobs using a known deterministic function of tier, distance and category
match — the same features the model receives. The model recovers a specified
process rather than learning a human one. Recall@5 of 1.000 across eight
candidates is close to uninformative; NDCG@1 of 0.883 is the more meaningful
figure and remains flattered.

**Dynamic pricing.** The price band is sound: the 10th-to-90th percentile interval
contains 78.2% of realised amounts against a nominal 80%, with no quantile
crossings, and median absolute error of ₹361 on ticket sizes spanning ₹450 to
₹45,000.

The acceptance classifier achieves AUC 0.527 against a base rate of 79.4%, and
**is not fit for deployment.** Operational load features were added specifically
to improve it; AUC moved from 0.530 to 0.527. The diagnosis is that booking
completion in this dataset is driven principally by a per-day rainfall variable
absent from the feature set, and no available feature proxies it adequately. The
remedy is a weather data feed, not further tuning.

### Theme 5: Automated verification detected defects that review did not

Six defects were detected by automated checks rather than by inspection.

| Detected by | Defect |
|---|---|
| Integrity checks | Six technicians assigned work after their recorded departure date, caused by the same tenure calculation being implemented twice with differing edge-case handling |
| Service tests | Training-serving skew: a feature added to the training frame but not to the single-row inference frame |
| Dashboard tests | A join collision in which a column present on both fact and dimension was silently renamed, causing every downstream reference to fail |
| Cross-implementation comparison | A threshold computed across bookings in one implementation and across days in the other, producing 34.8% where the reference produced 32.5% |
| Profiling | Peak memory of 603 MB against a 1 GB deployment ceiling, of which 141 MB was low-cardinality text stored per row |
| Bias measurement | Systematic −39.6% forecast bias from tree extrapolation failure |

The training-serving skew is notable: training completed successfully and
reported valid metrics while the inference path raised an exception. No review of
the training code would have revealed it.

### Supplementary findings

Three findings emerged that were not sought by the research questions.

**Seasonal demand is a reallocation problem.** Technician utilisation during
monsoon rises for pest control (+59%), plumbing (+57%) and electrical work (+38%)
while falling for painting (−12%) and air-conditioning (−25%). Aggregate
utilisation is 17.0%. Idle capacity exists concurrently with strained capacity in
the same months.

**Acquisition channel predicts value more strongly than volume.** Referred
customers repeat at 79.0% with mean lifetime value ₹7,793; paid-social customers
repeat at 39.9% with mean lifetime value ₹3,506 — a 2.2-fold difference — while
the latter channel supplies the second-largest customer count.

**Service level failure concentrates on predictable days.** Partitioning completed
jobs by whether daily volume exceeded its trailing thirty-day mean, breach rates
are 32.5% on the busiest quintile against 14.1% otherwise; mean time to
assignment rises from 11.4 to 19.7 minutes and mean rating falls from 4.32 to
4.04.

## 4.4 Interpretation of Findings

### 4.4.1 The significance of outcome independence

The 94-day gap is not explained by the sophistication of either signal. Training-
data age is arithmetically trivial — a subtraction of two dates. Its advantage is
structural: it observes the pipeline rather than the predictions, and the pipeline
broke first.

This suggests monitoring signals should be classified by what they observe rather
than by how they are computed. A signal observing the process can respond when the
process fails. A signal observing outputs can respond only when outputs become
wrong, which may be considerably later or, if the environment remains stable,
never.

### 4.4.2 Accuracy as a lagging indicator

Theme 2 indicates that accuracy metrics measure the conjunction of two
conditions: that the model was appropriately fitted, and that the environment has
not since changed. A stable accuracy reading is consistent with a well-maintained
model in a stable environment, and equally consistent with an abandoned model in
a stable environment. The reading alone does not distinguish them.

This has a practical consequence for recurring drift. If the environment changes
seasonally and a maintenance lapse occurs during a stable period, the consequence
is deferred to the next regime change. The organisation experiences a sudden
degradation whose proximate cause — the monsoon — is visible, and whose actual
cause — a maintenance failure three months earlier — is not.

### 4.4.3 Metric selection as a design decision

Theme 3 shows a single model receiving assessments of 10.4% and 37.2% error
depending on metric choice. Both computations are correct.

The relevant property is which failure modes each metric can express. MAPE cannot
express prediction into zero-demand cells. Reporting it alone renders a
substantial failure mode structurally invisible, irrespective of how carefully the
number is monitored.

### 4.4.4 Honest reporting as a methodological requirement

Theme 4 includes two results that do not support deployment. Reporting them is
methodologically necessary rather than merely commendable.

The ranking result is the more instructive. A model scoring 0.954 against a target
of 0.82 would ordinarily be reported as a success. It is an artefact of the
evaluation instrument: the generator specifies assignment as a function of the
features the model receives, so high performance measures the recoverability of a
specified process. Reporting the figure without that caveat would misrepresent the
model's expected production behaviour.

### 4.4.5 Verification layers as independent instruments

Theme 5 indicates that each verification layer detected a distinct defect class,
and that no layer would have detected the full set. This supports a layered
verification strategy over reliance on any single method.

## 4.5 Discussion of Findings

### 4.5.1 Relation to the technical debt literature

The results provide direct empirical support for Sculley et al. (2015). The
injected failure is precisely the class of liability they describe: invisible at
the system boundary, accumulating without symptom, and surfacing later through a
mechanism apparently unrelated to its cause.

The finding extends their argument by quantifying the interval. Their treatment
establishes that such debt exists; this study measures 94 days of it under
controlled conditions.

### 4.5.2 Relation to drift detection literature

The results complement Gama et al. (2014) while suggesting a boundary to the
drift framing. In this study drift detection performed as the literature
predicts: population stability index crossed its threshold and identified the
degradation. But it did so 92 days after the failure and only 3 days before the
accuracy metric, because drift detection also observes data rather than pipeline.

The implication is not that drift detection is inadequate but that it addresses a
different failure class. Drift detection identifies environmental change; pipeline
monitoring identifies maintenance failure. A system experiencing both requires
both.

The conventional 0.25 threshold performed adequately here, though the value is
heuristic. Its adequacy in this instance should not be generalised.

### 4.5.3 Relation to forecast evaluation literature

Theme 3 provides a contemporary operational illustration of the critique advanced
by Hyndman and Koehler (2006). Their argument that percentage errors are
undefined at zero actuals is not novel; what this study adds is a measurement of
the magnitude at stake in a realistic sparse setting — 26.6% of total volume
forecast into cells where nothing occurred, entirely invisible to the reported
metric.

The persistence of MAPE two decades after its documented limitations suggests the
obstacle is conventional rather than technical.

### 4.5.4 Implications for practice

Three implications follow.

**Monitor the pipeline, not only the predictions.** At least one signal should be
independent of ground truth. Training-data age is the cheapest available and would
have detected the failure on the day it occurred.

**Report a companion metric to any percentage error.** WAPE, MASE or an explicit
count of zero-actual cells. The divergence between metrics is itself diagnostic.

**Assume degradation is deferred, not absent.** A model that has not degraded may
be unmaintained in a stable environment. Where the environment changes on a known
seasonal cycle, the cost of a maintenance lapse is incurred at the next cycle.

## 4.6 Limitations of Findings

### 4.6.1 Synthetic data

The failure mechanism was specified by the researcher. The finding that
training-data age responds on the day of failure is partly definitional: the
signal was constructed to reflect the pipeline state that was altered. What is not
definitional, and constitutes the finding, is the 94-day interval before accuracy
responded, which follows from the interaction between the injected failure and the
independently specified seasonal structure.

Absolute values are properties of this dataset. The 94-day interval would differ
under a different seasonal calendar or a different failure date.

### 4.6.2 Single failure mode

One failure mode was examined: cessation of retraining. Other modes — schema
change, upstream data corruption, feature computation error, label delay — were
not, and may exhibit different detection profiles.

### 4.6.3 Model evaluation constraints

The ranking evaluation is compromised by the recoverability of the generative
process, as reported. The pricing acceptance classifier is limited by the absence
of the driving variable from the feature set. Both are stated rather than
concealed, but both limit what may be concluded about model quality as distinct
from monitoring behaviour.

### 4.6.4 Single-domain scope

One domain in one city was examined. The seasonal structure of Bengaluru is
unusually pronounced, and may accentuate the divergence between pipeline and
accuracy signals relative to a more stable environment.

## 4.7 Chapter Summary

This chapter reported five themes. Detection latency differed by 94 days between
outcome-independent and outcome-dependent signals. A stale model degraded only on
environmental change. MAPE of 10.4% concealed WAPE of 37.2%, attributable entirely
to 11,004 zero-actual cells. Model quality was reported including two results that
do not support deployment. Automated verification detected six defects that review
did not. Findings were interpreted, discussed against the literature, and their
limitations stated.

---

# Chapter 5: Conclusion and Recommendations

## 5.1 Introduction

This chapter summarises the conclusions, links them to the research questions,
states the study's limitations, offers recommendations for practice and further
research, and reflects on the process.

## 5.2 Summary of Key Findings

**Operational monitoring detects pipeline failure 94 days earlier than accuracy
monitoring.** Training-data age diverged one day after the injected failure;
forecast error diverged 95 days after it.

**Stable accuracy does not indicate a healthy pipeline.** It indicates that the
model was appropriately fitted and that the environment has not since changed. A
maintenance lapse during a stable period defers its cost to the next regime
change.

**Percentage error metrics conceal failure modes they cannot express.** MAPE of
10.4% and WAPE of 37.2% described the same predictions; the divergence was
entirely attributable to 11,004 cells forecasting 14,806 jobs where none
occurred, 26.6% of realised volume.

**Layered automated verification detects defects that review does not.** Six
defects were found by six different mechanisms, including training-serving skew
invisible to inspection of the training code.

## 5.3 Limitations of Study

The findings derive from a synthetic instrument with a researcher-specified
failure. Absolute intervals are properties of this dataset. One failure mode was
examined. Two of three models carry evaluation constraints that are reported but
that limit conclusions about model quality. The study covers one domain in one
city with an atypically pronounced seasonal structure.

## 5.4 Link to Research Questions and Objectives

**RQ1 — Can an outcome-independent signal detect silent failure earlier, and by
what margin?** Answered affirmatively. Training-data age detected the failure at
one day; MAPE at 95 days. The margin is 94 days.

**RQ2 — Under what conditions does a stale model continue to perform, and what
causes deterioration?** Answered in Theme 2. A stale model performs while the
learned relationship holds. Deterioration was caused by the seasonal regime
change of 1 June 2026, which the staleness rendered the model unable to
accommodate.

**RQ3 — Does MAPE adequately characterise forecast quality where zero-demand
observations occur?** Answered negatively. MAPE excluded 11,004 of 47,117 cells
by mathematical necessity, concealing 26.6% of realised volume in phantom
predictions.

**RQ4 — What configuration would have detected the failure earliest, and what does
it cost?** A threshold alert on training-data age exceeding twice the retraining
cadence. It requires one timestamp comparison, no ground truth and no model
evaluation, and would have fired on 16 March 2026.

All six objectives stated in Section 1.4 were met. The artefact was constructed
and validated; three services were developed and evaluated; monitoring was
implemented across eight models; the failure was injected and latency measured;
forecast metric adequacy was examined; and recommendations were derived.

## 5.5 Recommendations

### 5.5.1 For practice

1. **Alert on training-data age for every deployed model**, at a threshold of
   approximately twice the intended retraining cadence. This is the study's
   principal recommendation. It is arithmetically trivial and would have detected
   the failure on the day it occurred.
2. **Alert on the absence of retraining success, not the presence of failure.** A
   job that stops running emits no error. Monitoring should treat silence as a
   signal.
3. **Report a companion metric alongside any percentage error**, and count
   zero-actual cells explicitly.
4. **Evaluate forecasts at the grain of the decision.** Cell-grain error was 47.7%
   against a noise floor of 44.2%; area-grain error was 13.7%. Only the latter
   informs a staffing decision.
5. **Treat pipeline health as model monitoring**, not as infrastructure
   monitoring. The signals belong on the same dashboard as the accuracy metrics.

### 5.5.2 For further research

1. **Extend the protocol to additional failure modes** — schema change, upstream
   corruption, feature computation error, label delay — to determine whether the
   latency advantage generalises.
2. **Vary the interval between failure and regime change** systematically, to
   characterise the relationship between environmental stability and detection
   delay.
3. **Replicate against production data** where a failure time is independently
   known from deployment logs, providing external validation.
4. **Examine threshold selection empirically.** The 0.25 population stability
   index threshold is heuristic; its false positive and negative rates in
   operational settings are not well established.

## 5.6 Reflections in First Person

The most useful thing I learned in this project came from a result I did not
expect and initially assumed was a mistake.

When I first computed the forecasting model's error I obtained 10.4% by one
metric and 37.2% by another over identical predictions. My first assumption was a
bug in my own code. It took some time to accept that both figures were correct and
that the difference was the finding rather than an obstacle to it. That MAPE
excludes zero-actual observations is elementary and I knew it; I had not
appreciated that in a sparse operational setting this exclusion could hide a
quarter of total volume.

The second thing I learned concerns verification. I wrote sixteen integrity
checks expecting them to confirm work I had already done correctly. They found six
technicians assigned jobs after their departure dates, caused by my having
implemented the same tenure calculation twice with different edge-case handling.
Later, service tests found a feature I had added to training and forgotten to add
to inference — a defect no reading of the training code would have revealed.

I also had to decide how to report two models that did not work. The ranker scored
well above target for reasons that made the score meaningless, and the pricing
acceptance classifier performed at approximately chance. The straightforward
option was to report the good number and omit the caveat. I concluded that a
result reported without its caveat is not a result, and that a model card
containing only favourable outcomes serves no purpose. I found the discipline of
writing "this component is not fit to ship" harder than expected and more valuable
than the components that worked.

Finally, building the same dashboard twice — once in Power BI and once in
Streamlit — was not planned as a verification method but became one. The two
implementations disagreed about one figure, and the disagreement was a genuine
error in one of them. Redundancy proved more effective at finding mistakes than
care.

---

# References

> **Note for submission:** every reference below should be verified against the
> original publication before submission, and the citation style adjusted to the
> convention required by the programme.

Breck, E., Cai, S., Nielsen, E., Salib, M. and Sculley, D. (2017) 'The ML Test
Score: A Rubric for ML Production Readiness and Technical Debt Reduction',
*Proceedings of the IEEE International Conference on Big Data*, pp. 1123–1132.

Burges, C.J.C. (2010) *From RankNet to LambdaRank to LambdaMART: An Overview*.
Microsoft Research Technical Report MSR-TR-2010-82.

Chen, T. and Guestrin, C. (2016) 'XGBoost: A Scalable Tree Boosting System',
*Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge
Discovery and Data Mining*, pp. 785–794.

Gama, J., Žliobaitė, I., Bifet, A., Pechenizkiy, M. and Bouchachia, A. (2014) 'A
Survey on Concept Drift Adaptation', *ACM Computing Surveys*, 46(4), pp. 1–37.

Grinsztajn, L., Oyallon, E. and Varoquaux, G. (2022) 'Why do tree-based models
still outperform deep learning on typical tabular data?', *Advances in Neural
Information Processing Systems 35*.

Hyndman, R.J. and Athanasopoulos, G. (2021) *Forecasting: Principles and
Practice*. 3rd edn. Melbourne: OTexts.

Hyndman, R.J. and Koehler, A.B. (2006) 'Another look at measures of forecast
accuracy', *International Journal of Forecasting*, 22(4), pp. 679–688.

Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q. and Liu, T.-Y.
(2017) 'LightGBM: A Highly Efficient Gradient Boosting Decision Tree', *Advances
in Neural Information Processing Systems 30*, pp. 3146–3154.

Khanuja, S., Bansal, D., Mehtani, S. et al. (2021) *MuRIL: Multilingual
Representations for Indian Languages*. arXiv preprint arXiv:2103.10730.

Kimball, R. and Ross, M. (2013) *The Data Warehouse Toolkit: The Definitive Guide
to Dimensional Modeling*. 3rd edn. Indianapolis: Wiley.

Koenker, R. and Bassett, G. (1978) 'Regression Quantiles', *Econometrica*, 46(1),
pp. 33–50.

Paleyes, A., Urma, R.-G. and Lawrence, N.D. (2022) 'Challenges in Deploying
Machine Learning: A Survey of Case Studies', *ACM Computing Surveys*, 55(6), pp.
1–29.

Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D.,
Chaudhary, V., Young, M., Crespo, J.-F. and Dennison, D. (2015) 'Hidden Technical
Debt in Machine Learning Systems', *Advances in Neural Information Processing
Systems 28*, pp. 2503–2511.

---

# Appendix 1: Declaration of Authenticity

I declare that this work is my own, that all sources have been acknowledged, and
that the artefact described was constructed by me for the purpose of this study.
The dataset analysed is synthetic and was generated by the programs included in
the accompanying repository; it does not represent any real organisation,
individual or transaction, and this is stated in the artefact's documentation and
user interface.

*Signed:* ______________________  *Date:* ______________

---

# Appendix 2: Artefact Inventory

Repository: `github.com/ABHISHEKPRASAD16/seek-my-service-analytics`
Deployed application: `seek-my-service-analytics.streamlit.app`

| Component | Location | Description |
|---|---|---|
| Data generator | `generator/` | Configuration, seasonality logic, generation program |
| Generated dataset | `data/` | Eleven CSV files, deterministic from seed 20260819 |
| Validation | `validate.py` | Sixteen integrity checks |
| Source schema | `sql/01_source_schema.sql` | PostgreSQL OLTP schema |
| Staging layer | `sql/02_staging_views.sql` | Renaming, typing, flattening |
| Dimensional build | `sql/03_star_schema.sql` | Mart layer with business definitions |
| Semantic layer | `powerbi/measures.dax` | 119 DAX measures |
| Deployment scripts | `powerbi/*.csx` | Tabular Editor automation |
| ML services | `ml/` | Three FastAPI services, shared features, training |
| Dashboard | `app/`, `streamlit_app.py` | Five-page web application |
| Tests | `tests/` | 109 automated tests |
| Documentation | `docs/` | Data dictionary, model cards, architecture |

# Appendix 3: Validation Output

All sixteen checks pass on the submitted dataset.

| # | Check |
|---|---|
| 1 | Referential integrity across every fact and dimension |
| 2 | Date dimension contiguous across the full range |
| 3 | No negative amounts; final amount within quoted plus discount |
| 4 | Completion-only columns populated only for completed bookings |
| 5 | Signup precedes first booking; join date precedes first job |
| 6 | Rating and sentiment blank together, populated together |
| 7 | Funnel monotonic and reconciling to the booking fact |
| 8 | Capacity reconciling to bookings per technician per day |
| 9 | Row counts per table |
| 10 | Monthly booking counts showing the growth curve |
| 11 | Monsoon, summer and festival signatures present |
| 12 | Drift incident and recovery visible in the error series |
| 13 | Service level breach worse on high-strain days |
| 14 | Referral and organic acquisition out-repeating paid social |
| 15 | Payment mix dominated by UPI |
| 16 | Total gross merchandise value and platform revenue |
