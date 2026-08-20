"""
Seek My Service - measure library source of truth.

This file defines every DAX measure exactly once and emits both deliverables:

    powerbi/measures.dax                    readable library, paste-ready
    powerbi/measures_tabular_editor.csx     one-click Tabular Editor 2 script

Hand-maintaining those two side by side guarantees they drift apart the first
time a measure changes. Generating both from one list means they cannot.

Run with:  python powerbi/build_measures.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

HOME_TABLE = "fact_bookings"
OUT_DIR = Path(__file__).resolve().parent

# Thresholds referenced by more than one measure, declared once.
PSI_ALERT = "0.25"
SLA_TARGET = "0.90"
FRAUD_REVIEW_THRESHOLD = "0.6"
AT_RISK_RATING = "4.0"


@dataclass
class Measure:
    name: str
    folder: str
    fmt: str
    doc: str
    dax: str

    @property
    def expression(self) -> str:
        """DAX body, trimmed and consistently indented."""
        lines = [line.rstrip() for line in self.dax.strip("\n").splitlines()]
        return "\n".join(lines)


M: List[Measure] = []


def measure(name: str, folder: str, fmt: str, doc: str, dax: str) -> None:
    M.append(Measure(name, folder, fmt, doc, dax))


# ===========================================================================
# 01 Core - volume, revenue and margin
# ===========================================================================
F = "01 Core"

measure("Total Bookings", F, "#,0",
        "Every booking row regardless of status. The denominator for the rate measures.",
        "COUNTROWS ( fact_bookings )")

measure("Completed Jobs", F, "#,0",
        "Bookings that were actually fulfilled. Only these carry money.",
        """CALCULATE (
    [Total Bookings],
    fact_bookings[BookingStatus] = "Completed"
)""")

measure("Completion Rate", F, "0.0%",
        "Share of bookings that reached a completed job.",
        "DIVIDE ( [Completed Jobs], [Total Bookings] )")

measure("Cancelled Jobs", F, "#,0",
        "Cancellations from either side of the marketplace.",
        """CALCULATE (
    [Total Bookings],
    fact_bookings[BookingStatus] IN { "CancelledByCustomer", "CancelledByPro" }
)""")

measure("Cancellation Rate", F, "0.0%",
        "Combined cancellation rate. Rises on heavy monsoon days.",
        "DIVIDE ( [Cancelled Jobs], [Total Bookings] )")

measure("Customer Cancellation Rate", F, "0.0%",
        "Cancellations initiated by the customer.",
        """DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = "CancelledByCustomer" ),
    [Total Bookings]
)""")

measure("Pro Cancellation Rate", F, "0.0%",
        "Cancellations initiated by the technician. A supply-reliability signal.",
        """DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = "CancelledByPro" ),
    [Total Bookings]
)""")

measure("No Show Rate", F, "0.0%",
        "Bookings where the technician never arrived.",
        """DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = "NoShow" ),
    [Total Bookings]
)""")

measure("Reschedule Rate", F, "0.0%",
        "Bookings superseded by a rescheduled booking record.",
        """DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = "Rescheduled" ),
    [Total Bookings]
)""")

measure("GMV INR", F, "#,0",
        "Gross merchandise value: what customers paid, before the platform's cut.",
        "SUM ( fact_bookings[FinalAmountINR] )")

measure("Platform Revenue INR", F, "#,0",
        "The platform's commission. This is the company's actual top line.",
        "SUM ( fact_bookings[PlatformRevenueINR] )")

measure("Take Rate Pct", F, "0.0%",
        "Platform revenue as a share of GMV. Mix-sensitive: painting drags it down.",
        "DIVIDE ( [Platform Revenue INR], [GMV INR] )")

measure("Avg Order Value", F, "#,0",
        "GMV per completed job.",
        "DIVIDE ( [GMV INR], [Completed Jobs] )")

measure("Material Cost INR", F, "#,0",
        "Pass-through cost of materials on completed jobs.",
        "SUM ( fact_bookings[MaterialCostINR] )")

measure("Net Revenue After Material INR", F, "#,0",
        "GMV net of materials. The real value the platform's labour creates.",
        "[GMV INR] - [Material Cost INR]")

measure("Gross Margin Pct", F, "0.0%",
        "Net-of-material revenue as a share of GMV.",
        "DIVIDE ( [Net Revenue After Material INR], [GMV INR] )")

measure("Quoted Amount INR", F, "#,0",
        "Total quoted before discounts and on-site scope changes.",
        "SUM ( fact_bookings[QuotedAmountINR] )")

measure("Discount Given INR", F, "#,0",
        "Coupon and promotional value handed out.",
        "SUM ( fact_bookings[DiscountINR] )")

measure("Discount Rate Pct", F, "0.0%",
        "Discount as a share of the quoted value.",
        "DIVIDE ( [Discount Given INR], [Quoted Amount INR] )")


# ===========================================================================
# 02 Time intelligence
# ===========================================================================
F = "02 Time Intelligence"

measure("GMV INR PM", F, "#,0",
        "GMV in the equivalent prior month.",
        "CALCULATE ( [GMV INR], DATEADD ( dim_date[Date], -1, MONTH ) )")

measure("GMV MoM Pct", F, "+0.0%;-0.0%;0.0%",
        "Month-over-month change in GMV.",
        "DIVIDE ( [GMV INR] - [GMV INR PM], [GMV INR PM] )")

measure("GMV INR PY", F, "#,0",
        "GMV in the equivalent period one year earlier.",
        "CALCULATE ( [GMV INR], DATEADD ( dim_date[Date], -12, MONTH ) )")

measure("GMV YoY Pct", F, "+0.0%;-0.0%;0.0%",
        "Year-over-year change in GMV. Blank before Jan 2026, which is correct.",
        "DIVIDE ( [GMV INR] - [GMV INR PY], [GMV INR PY] )")

measure("Bookings PM", F, "#,0",
        "Booking volume in the prior month.",
        "CALCULATE ( [Total Bookings], DATEADD ( dim_date[Date], -1, MONTH ) )")

measure("Bookings MoM Pct", F, "+0.0%;-0.0%;0.0%",
        "Month-over-month change in booking volume.",
        "DIVIDE ( [Total Bookings] - [Bookings PM], [Bookings PM] )")

measure("Bookings PY", F, "#,0",
        "Booking volume one year earlier.",
        "CALCULATE ( [Total Bookings], DATEADD ( dim_date[Date], -12, MONTH ) )")

measure("Bookings YoY Pct", F, "+0.0%;-0.0%;0.0%",
        "Year-over-year change in booking volume.",
        "DIVIDE ( [Total Bookings] - [Bookings PY], [Bookings PY] )")

measure("Platform Revenue PM", F, "#,0",
        "Commission earned in the prior month.",
        "CALCULATE ( [Platform Revenue INR], DATEADD ( dim_date[Date], -1, MONTH ) )")

measure("Platform Revenue MoM Pct", F, "+0.0%;-0.0%;0.0%",
        "Month-over-month change in platform revenue.",
        "DIVIDE ( [Platform Revenue INR] - [Platform Revenue PM], [Platform Revenue PM] )")

measure("Platform Revenue PY", F, "#,0",
        "Commission earned one year earlier.",
        "CALCULATE ( [Platform Revenue INR], DATEADD ( dim_date[Date], -12, MONTH ) )")

measure("Platform Revenue YoY Pct", F, "+0.0%;-0.0%;0.0%",
        "Year-over-year change in platform revenue.",
        "DIVIDE ( [Platform Revenue INR] - [Platform Revenue PY], [Platform Revenue PY] )")

measure("GMV Rolling 28D Avg", F, "#,0",
        "Average daily GMV over the trailing 28 days. Smooths the weekend sawtooth.",
        """DIVIDE (
    CALCULATE (
        [GMV INR],
        DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -28, DAY )
    ),
    28
)""")

measure("Bookings Rolling 28D Avg", F, "#,0",
        "Average daily booking volume over the trailing 28 days.",
        """DIVIDE (
    CALCULATE (
        [Total Bookings],
        DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -28, DAY )
    ),
    28
)""")

measure("GMV 3M Moving Avg", F, "#,0",
        "Three-month moving average of monthly GMV.",
        """DIVIDE (
    CALCULATE (
        [GMV INR],
        DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -3, MONTH )
    ),
    3
)""")

measure("GMV YTD", F, "#,0",
        "Calendar year to date.",
        "CALCULATE ( [GMV INR], DATESYTD ( dim_date[Date] ) )")

measure("GMV FYTD", F, "#,0",
        "Indian fiscal year to date, April to March. Built from the FiscalYear "
        "column rather than a year-end string, so it is immune to locale.",
        """VAR CurrentFY = MAX ( dim_date[FiscalYear] )
VAR LastDate = MAX ( dim_date[Date] )
RETURN
    CALCULATE (
        [GMV INR],
        REMOVEFILTERS ( dim_date ),
        dim_date[FiscalYear] = CurrentFY,
        dim_date[Date] <= LastDate
    )""")

measure("Platform Revenue FYTD", F, "#,0",
        "Indian fiscal year to date commission.",
        """VAR CurrentFY = MAX ( dim_date[FiscalYear] )
VAR LastDate = MAX ( dim_date[Date] )
RETURN
    CALCULATE (
        [Platform Revenue INR],
        REMOVEFILTERS ( dim_date ),
        dim_date[FiscalYear] = CurrentFY,
        dim_date[Date] <= LastDate
    )""")


# ===========================================================================
# 03 Operations
# ===========================================================================
F = "03 Operations"

measure("Avg Time To Assign", F, "0.0",
        "Minutes from booking created to a technician accepting it.",
        "AVERAGE ( fact_bookings[TimeToAssignMins] )")

measure("Avg Response Time", F, "0.0",
        "Minutes from assignment to the technician confirming.",
        "AVERAGE ( fact_bookings[ResponseTimeMins] )")

measure("SLA Met Pct", F, "0.0%",
        "Share of completed jobs where the technician arrived inside the promised window.",
        "AVERAGE ( fact_bookings[SLAMetFlag] )")

measure("SLA Breach Count", F, "#,0",
        "Completed jobs that missed the arrival promise.",
        """CALCULATE (
    [Completed Jobs],
    fact_bookings[SLAMetFlag] = 0
)""")

measure("SLA Breach Pct", F, "0.0%",
        "The complement of SLA Met Pct, for when a chart reads better upside down.",
        "1 - [SLA Met Pct]")

measure("Avg Job Duration", F, "0.0",
        "Average on-site minutes for completed jobs.",
        "AVERAGE ( fact_bookings[JobDurationMins] )")

measure("First Time Fix Pct", F, "0.0%",
        "Share of completed jobs resolved without a return visit.",
        "AVERAGE ( fact_bookings[IsFirstTimeFix] )")

measure("Reopen Rate", F, "0.0%",
        "Completed jobs reopened within seven days. The quality tail.",
        "AVERAGE ( fact_bookings[ReopenedWithin7Days] )")

measure("Avg Actual ETA", F, "0.0",
        "Average realised arrival time in minutes.",
        "AVERAGE ( fact_bookings[ActualETAMins] )")

measure("Capacity Strain Index", F, "0.00",
        "Average daily volume in context divided by the trailing 30-day daily average. "
        "Above 1.0 means the day is running hotter than the recent norm, and SLA "
        "breaches track it closely.",
        """VAR DaysInContext = COUNTROWS ( VALUES ( dim_date[Date] ) )
VAR CurrentDaily = DIVIDE ( [Total Bookings], DaysInContext )
VAR TrailingDaily =
    DIVIDE (
        CALCULATE (
            [Total Bookings],
            DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -30, DAY )
        ),
        30
    )
RETURN
    DIVIDE ( CurrentDaily, TrailingDaily )""")

measure("Emergency Job Pct", F, "0.0%",
        "Share of bookings for services flagged as emergency call-outs.",
        """DIVIDE (
    CALCULATE ( [Total Bookings], dim_service[IsEmergency] = 1 ),
    [Total Bookings]
)""")


# ===========================================================================
# 04 Funnel and demand
# ===========================================================================
F = "04 Funnel and Demand"

measure("Search Volume", F, "#,0",
        "Searches performed, at day x area x service grain.",
        "SUM ( fact_leads[Searches] )")

measure("Lead Volume", F, "#,0",
        "Searches that turned into an identified lead.",
        "SUM ( fact_leads[Leads] )")

measure("Quotes Sent", F, "#,0",
        "Leads that received at least one quote.",
        "SUM ( fact_leads[QuotesSent] )")

measure("Funnel Bookings", F, "#,0",
        "Bookings as counted inside the funnel fact. Reconciles exactly to Total Bookings.",
        "SUM ( fact_leads[Bookings] )")

measure("Search to Lead Pct", F, "0.0%",
        "First funnel step.",
        "DIVIDE ( [Lead Volume], [Search Volume] )")

measure("Lead to Quote Pct", F, "0.0%",
        "Second funnel step. Weak values here mean a supply coverage problem.",
        "DIVIDE ( [Quotes Sent], [Lead Volume] )")

measure("Quote to Booking Pct", F, "0.0%",
        "Third funnel step. Structurally weaker in low demand-tier areas.",
        "DIVIDE ( [Funnel Bookings], [Quotes Sent] )")

measure("Search to Booking Pct", F, "0.0%",
        "End-to-end conversion. The single number the growth team lives on.",
        "DIVIDE ( [Funnel Bookings], [Search Volume] )")

measure("Avg Lead Quality", F, "0.000",
        "Mean lead_quality_scorer output for the cell.",
        "AVERAGE ( fact_leads[AvgLeadQualityScore] )")

measure("Unconverted Searches", F, "#,0",
        "Search interest that produced no booking at all. Where the money is leaking.",
        "[Search Volume] - [Funnel Bookings]")

measure("Demand Coverage Pct", F, "0.0%",
        "Share of searched cells that produced at least one booking.",
        """VAR TotalCells = COUNTROWS ( fact_leads )
VAR ConvertedCells = CALCULATE ( COUNTROWS ( fact_leads ), fact_leads[Bookings] > 0 )
RETURN
    DIVIDE ( ConvertedCells, TotalCells )""")


# ===========================================================================
# 05 Customer
# ===========================================================================
F = "05 Customer"

measure("Total Customers", F, "#,0",
        "Distinct customers who booked in the current filter context.",
        "DISTINCTCOUNT ( fact_bookings[CustomerKey] )")

measure("New Customers", F, "#,0",
        "Customers placing their first ever booking in the period.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    fact_bookings[IsRepeatCustomer] = 0
)""")

measure("Repeat Customers", F, "#,0",
        "Customers booking again, having booked before.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    fact_bookings[IsRepeatCustomer] = 1
)""")

measure("Repeat Rate", F, "0.0%",
        "Share of bookings placed by returning customers.",
        """DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[IsRepeatCustomer] = 1 ),
    [Total Bookings]
)""")

measure("Customer Signups", F, "#,0",
        "Accounts created in the period, via the inactive SignupDate relationship. "
        "Signups lead first bookings, so this and New Customers differ by design.",
        """CALCULATE (
    COUNTROWS ( dim_customer ),
    USERELATIONSHIP ( dim_customer[SignupDate], dim_date[Date] )
)""")

measure("Active Customers 90D", F, "#,0",
        "Distinct customers with a booking in the trailing 90 days.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -90, DAY )
)""")

measure("Rated Jobs", F, "#,0",
        "Completed jobs that received a star rating.",
        """CALCULATE (
    COUNTROWS ( fact_bookings ),
    fact_bookings[CustomerRating] IN { 1, 2, 3, 4, 5 }
)""")

measure("Rated Job Pct", F, "0.0%",
        "Response rate on the rating prompt. Roughly 62% by design.",
        "DIVIDE ( [Rated Jobs], [Completed Jobs] )")

measure("Avg CSAT", F, "0.00",
        "Mean customer star rating, 1 to 5.",
        "AVERAGE ( fact_bookings[CustomerRating] )")

measure("NPS Proxy", F, "0",
        "Net promoter proxy from stars: 5 promotes, 4 is passive, 3 and below detracts. "
        "Explicit value lists keep blank ratings out of the detractor bucket.",
        """VAR Promoters = CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[CustomerRating] = 5 )
VAR Detractors = CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[CustomerRating] IN { 1, 2, 3 } )
RETURN
    DIVIDE ( Promoters - Detractors, [Rated Jobs] ) * 100""")

measure("Negative Review Pct", F, "0.0%",
        "Share of rated jobs whose sentiment came back negative.",
        """DIVIDE (
    CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[ReviewSentiment] = "Negative" ),
    [Rated Jobs]
)""")

measure("Avg LTV INR", F, "#,0",
        "Mean lifetime value across customers in context.",
        "AVERAGE ( dim_customer[LifetimeValueINR] )")

measure("Customer Acquisition Mix Pct", F, "0.0%",
        "Each acquisition channel's share of new customers. Put this on a bar chart "
        "beside Repeat Rate and the paid-social quality gap is impossible to miss.",
        """DIVIDE (
    [New Customers],
    CALCULATE ( [New Customers], REMOVEFILTERS ( dim_customer[AcquisitionChannel] ) )
)""")

measure("Bookings per Customer", F, "0.00",
        "Average bookings per distinct customer in context.",
        "DIVIDE ( [Total Bookings], [Total Customers] )")


# ===========================================================================
# 06 Professional supply
# ===========================================================================
F = "06 Professional Supply"

measure("Active Pros", F, "#,0",
        "Technicians who worked at least one job in the period.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_pro_capacity[ProKey] ),
    fact_pro_capacity[SlotsBooked] > 0
)""")

measure("Pros Online", F, "#,0",
        "Technicians who opened a calendar at all, whether or not they got work.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_pro_capacity[ProKey] ),
    fact_pro_capacity[IsOnline] = 1
)""")

measure("Roster Size", F, "#,0",
        "Technicians on the books, active or churned.",
        "COUNTROWS ( dim_professional )")

measure("Slots Available", F, "#,0",
        "Capacity the roster actually opened.",
        "SUM ( fact_pro_capacity[SlotsAvailable] )")

measure("Slots Booked", F, "#,0",
        "Capacity consumed by real bookings.",
        "SUM ( fact_pro_capacity[SlotsBooked] )")

measure("Pro Utilization Pct", F, "0.0%",
        "Booked slots over available slots. Low in aggregate and brutally unequal "
        "across the roster, which is the point worth showing.",
        "DIVIDE ( [Slots Booked], [Slots Available] )")

measure("Jobs per Active Pro", F, "0.0",
        "Completed jobs divided by technicians who worked.",
        "DIVIDE ( [Completed Jobs], [Active Pros] )")

measure("Pro Acceptance Rate", F, "0.0%",
        "Offers accepted over offers received.",
        """DIVIDE (
    SUM ( fact_pro_capacity[AcceptedJobs] ),
    SUM ( fact_pro_capacity[AcceptedJobs] ) + SUM ( fact_pro_capacity[RejectedJobs] )
)""")

measure("Hours Logged", F, "#,0",
        "Total technician hours on the platform, converted from logged minutes.",
        "DIVIDE ( SUM ( fact_pro_capacity[HoursLoggedMins] ), 60 )")

measure("Pros At Risk", F, "#,0",
        f"Active technicians whose shrunk rating sits below {AT_RISK_RATING}. "
        "Ratings are shrunk towards a tier prior, so a low score here means "
        "sustained poor performance rather than one bad week.",
        f"""CALCULATE (
    COUNTROWS ( dim_professional ),
    dim_professional[IsActive] = 1,
    dim_professional[AvgRating] < {AT_RISK_RATING}
)""")

measure("Avg Pro Rating", F, "0.00",
        "Mean shrunk rating across technicians in context.",
        "AVERAGE ( dim_professional[AvgRating] )")

measure("New Pro Onboarding Count", F, "#,0",
        "Technicians who joined in the period, via the inactive JoinDate relationship.",
        """CALCULATE (
    COUNTROWS ( dim_professional ),
    USERELATIONSHIP ( dim_professional[JoinDate], dim_date[Date] )
)""")

measure("Churned Pros", F, "#,0",
        "Technicians who have left the platform.",
        """CALCULATE (
    COUNTROWS ( dim_professional ),
    dim_professional[IsActive] = 0
)""")

measure("Supply Demand Gap", F, "#,0",
        "Demand signal minus opened capacity. Positive means more interest than the "
        "roster can serve. VALID BY AREA AND DATE ONLY: fact_pro_capacity carries no "
        "service key, so slicing this by service or category leaves the capacity half "
        "unfiltered and the number becomes nonsense. Use it on the area map and the "
        "area-by-month matrix, nowhere else.",
        "[Lead Volume] - [Slots Available]")

measure("Verified Pro Pct", F, "0.0%",
        "Share of the roster that has passed background verification.",
        """DIVIDE (
    CALCULATE ( COUNTROWS ( dim_professional ), dim_professional[IsBackgroundVerified] = 1 ),
    [Roster Size]
)""")


# ===========================================================================
# 07 ML health
# ===========================================================================
F = "07 ML Health"

measure("Metric Value Avg", F, "0.000",
        "Mean of whatever primary metric the model in context reports. Units differ "
        "by model, so only ever show this filtered to a single model.",
        "AVERAGE ( fact_model_metrics[MetricValue] )")

measure("Metric Goal Avg", F, "0.000",
        "The model's target for its primary metric.",
        "AVERAGE ( fact_model_metrics[MetricGoal] )")

measure("Models In Breach", F, "#,0",
        "Distinct models missing their goal in the period.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_model_metrics[ModelKey] ),
    fact_model_metrics[IsBreach] = 1
)""")

measure("Breach Day Pct", F, "0.0%",
        "Share of model-days spent in breach.",
        "AVERAGE ( fact_model_metrics[IsBreach] )")

measure("Avg PSI Drift", F, "0.000",
        "Mean population stability index across models in context.",
        "AVERAGE ( fact_model_metrics[PSIDriftScore] )")

measure("Models Drifting", F, "#,0",
        f"Distinct models whose PSI has crossed the {PSI_ALERT} alert threshold.",
        f"""CALCULATE (
    DISTINCTCOUNT ( fact_model_metrics[ModelKey] ),
    fact_model_metrics[PSIDriftScore] > {PSI_ALERT}
)""")

measure("Model Freshness Days", F, "0",
        "Mean age of the training data behind live predictions. The measure that "
        "would have caught the silent retrain failure in March 2026.",
        "AVERAGE ( fact_model_metrics[TrainingDataAgeDays] )")

measure("Max Training Data Age", F, "0",
        "Worst training-data age in context. Climbs from 15 March 2026 to 126 days.",
        "MAX ( fact_model_metrics[TrainingDataAgeDays] )")

measure("P95 Latency Ms", F, "0",
        "Worst daily p95 serving latency in context.",
        "MAX ( fact_model_metrics[P95LatencyMs] )")

measure("Total Prediction Volume", F, "#,0",
        "Predictions served.",
        "SUM ( fact_model_metrics[PredictionVolume] )")

measure("Avg Feature Null Pct", F, "0.00",
        "Mean share of null feature values entering the models.",
        "AVERAGE ( fact_model_metrics[FeatureNullPct] )")

measure("Forecast MAPE", F, "0.0%",
        "Mean absolute percentage error of the demand forecaster. APE is stored as "
        "a fraction so percent formatting works natively.",
        "AVERAGE ( fact_forecast_accuracy[APE] )")

measure("Forecast WAPE", F, "0.0%",
        "Volume-weighted absolute percentage error. More honest than MAPE when many "
        "cells carry only one or two jobs.",
        """DIVIDE (
    SUM ( fact_forecast_accuracy[AbsError] ),
    SUM ( fact_forecast_accuracy[ActualJobs] )
)""")

measure("Forecast Bias Pct", F, "+0.0%;-0.0%;0.0%",
        "Signed error. Positive means the model forecasts more demand than turns up.",
        """DIVIDE (
    SUM ( fact_forecast_accuracy[ForecastedJobs] ) - SUM ( fact_forecast_accuracy[ActualJobs] ),
    SUM ( fact_forecast_accuracy[ActualJobs] )
)""")

measure("Forecasted Jobs", F, "#,0",
        "Total jobs the forecaster expected.",
        "SUM ( fact_forecast_accuracy[ForecastedJobs] )")

measure("Actual Jobs", F, "#,0",
        "Total jobs that actually happened, on the forecast grain.",
        "SUM ( fact_forecast_accuracy[ActualJobs] )")

measure("Phantom Demand Cells", F, "#,0",
        "Cells where the model forecast work that never arrived. The failure mode "
        "worth staring at, because it is what pre-positions supply into empty streets.",
        """CALCULATE (
    COUNTROWS ( fact_forecast_accuracy ),
    fact_forecast_accuracy[ActualJobs] = 0
)""")

measure("Price Prediction MAE", F, "#,0",
        "Mean absolute rupee error of the price engine against the final amount.",
        """CALCULATE (
    AVERAGEX (
        fact_bookings,
        ABS ( fact_bookings[PredictedPriceINR] - fact_bookings[FinalAmountINR] )
    ),
    fact_bookings[BookingStatus] = "Completed"
)""")

measure("Price MAPE", F, "0.0%",
        "Price engine error as a share of the amount actually charged.",
        """CALCULATE (
    AVERAGEX (
        fact_bookings,
        DIVIDE (
            ABS ( fact_bookings[PredictedPriceINR] - fact_bookings[FinalAmountINR] ),
            fact_bookings[FinalAmountINR]
        )
    ),
    fact_bookings[BookingStatus] = "Completed"
)""")

measure("ETA RMSE", F, "0.0",
        "Root mean squared error in minutes of the arrival-time predictor.",
        """SQRT (
    CALCULATE (
        AVERAGEX (
            fact_bookings,
            ( fact_bookings[PredictedETAMins] - fact_bookings[ActualETAMins] ) ^ 2
        ),
        fact_bookings[BookingStatus] = "Completed"
    )
)""")

measure("Match Score Avg", F, "0.000",
        "Mean ranker confidence in the technician it chose.",
        "AVERAGE ( fact_bookings[MatchScore] )")

measure("Fraud Caught Value INR", F, "#,0",
        f"Quoted value of bookings the detector flagged above {FRAUD_REVIEW_THRESHOLD}. "
        "Not all of it is genuine fraud, which is exactly why precision is the goal metric.",
        f"""CALCULATE (
    SUM ( fact_bookings[QuotedAmountINR] ),
    fact_bookings[FraudScore] > {FRAUD_REVIEW_THRESHOLD}
)""")

measure("High Churn Risk Customers", F, "#,0",
        "Distinct customers whose latest churn score exceeds 0.7.",
        """CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    fact_bookings[ChurnRiskScore] > 0.7
)""")


# ===========================================================================
# 08 Utility
# ===========================================================================
F = "08 Utility"

measure("Model KPI Status", F, "@",
        "Traffic light for the model in context, honouring GoalDirection so a lower "
        "MAPE and a higher AUC both read as good.",
        """VAR Value = [Metric Value Avg]
VAR Goal = [Metric Goal Avg]
VAR Direction = SELECTEDVALUE ( dim_model[GoalDirection], "HigherIsBetter" )
VAR Ratio = DIVIDE ( Value, Goal )
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Value ), "No Data",
        Direction = "LowerIsBetter" && Ratio <= 0.90, "On Target",
        Direction = "LowerIsBetter" && Ratio <= 1.00, "Watch",
        Direction = "LowerIsBetter", "Breach",
        Ratio >= 1.05, "On Target",
        Ratio >= 1.00, "Watch",
        "Breach"
    )""")

measure("SLA KPI Status", F, "@",
        f"Traffic light for service level against the {SLA_TARGET} promise.",
        f"""VAR Value = [SLA Met Pct]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Value ), "No Data",
        Value >= {SLA_TARGET}, "On Target",
        Value >= {SLA_TARGET} - 0.05, "Watch",
        "Breach"
    )""")

measure("KPI Status Colour", F, "@",
        "Hex colour to drive conditional formatting by field value. Matches THEME.json.",
        """SWITCH (
    [SLA KPI Status],
    "On Target", "#1B9E77",
    "Watch", "#E6A700",
    "Breach", "#D6455D",
    "#8A8F98"
)""")

measure("Ops Page Title", F, "@",
        "Dynamic page header reflecting the active area and date slicers.",
        """VAR AreaLabel =
    IF (
        ISFILTERED ( dim_area[AreaName] ),
        CONCATENATEX ( VALUES ( dim_area[AreaName] ), dim_area[AreaName], ", " ),
        "All Bengaluru"
    )
RETURN
    "Ops Control Room  |  " & AreaLabel & "  |  "
        & FORMAT ( MIN ( dim_date[Date] ), "dd MMM yyyy" ) & " to "
        & FORMAT ( MAX ( dim_date[Date] ), "dd MMM yyyy" )""")

measure("Demand Page Title", F, "@",
        "Dynamic page header for the Demand Intelligence page.",
        """VAR CategoryLabel =
    IF (
        ISFILTERED ( dim_service[ServiceCategory] ),
        CONCATENATEX ( VALUES ( dim_service[ServiceCategory] ), dim_service[ServiceCategory], ", " ),
        "All categories"
    )
RETURN
    "Demand Intelligence  |  " & CategoryLabel & "  |  "
        & FORMAT ( [Search to Booking Pct], "0.0%" ) & " search to booking\"""")

measure("Supply Page Title", F, "@",
        "Dynamic page header for the Supply Health page.",
        """"Supply Health  |  " & FORMAT ( [Active Pros], "#,0" ) & " active of "
    & FORMAT ( [Roster Size], "#,0" ) & " on roster  |  "
    & FORMAT ( [Pro Utilization Pct], "0.0%" ) & " utilisation\"""")

measure("ML Page Title", F, "@",
        "Dynamic page header for the ML Model Health page.",
        """VAR Breached = [Models In Breach]
RETURN
    "ML Model Health  |  "
        & IF ( Breached = 0, "all models on target", FORMAT ( Breached, "#,0" ) & " model(s) in breach" )
        & "  |  " & FORMAT ( MAX ( dim_date[Date] ), "dd MMM yyyy" )""")

measure("Selected Date Range Label", F, "@",
        "Human-readable label for the active date slicer.",
        """FORMAT ( MIN ( dim_date[Date] ), "dd MMM yyyy" ) & "  to  "
    & FORMAT ( MAX ( dim_date[Date] ), "dd MMM yyyy" )""")


# ===========================================================================
# Emit measures.dax
# ===========================================================================
def build_dax() -> str:
    numeric = [m for m in M if m.fmt != "@"]
    lines: List[str] = []
    lines.append("// " + "=" * 74)
    lines.append("// Seek My Service - DAX measure library")
    lines.append(f"// {len(M)} measures ({len(numeric)} numeric, {len(M) - len(numeric)} text),")
    lines.append("// every one with an explicit FORMAT_STRING.")
    lines.append("//")
    lines.append("// GENERATED FILE - edit powerbi/build_measures.py and re-run it, so that")
    lines.append("// this file and measures_tabular_editor.csx can never disagree.")
    lines.append("//")
    lines.append("// Three ways to get these into a model, fastest first:")
    lines.append("//")
    lines.append("//   1. Tabular Editor 2. External Tools > Tabular Editor > Advanced")
    lines.append("//      Scripting, paste measures_tabular_editor.csx, run, then Save.")
    lines.append("//      All measures land at once with folders and format strings.")
    lines.append("//")
    lines.append("//   2. DAX query view, no external tool needed. Paste this whole file")
    lines.append("//      into a DAX query, then use the 'Update model: Add new measure'")
    lines.append("//      CodeLens link above each measure.")
    lines.append("//")
    lines.append("//   3. By hand. Copy the body of a measure into the formula bar and set")
    lines.append("//      the format string from the ribbon. Slow, identical result.")
    lines.append("//")
    lines.append(f"// All measures are hosted on the {HOME_TABLE} table and organised by")
    lines.append("// display folder. Note the deliberate style: DIVIDE everywhere instead of")
    lines.append("// the '/' operator, and CALCULATE only where filter context genuinely")
    lines.append("// needs modifying.")
    lines.append("// " + "=" * 74)
    lines.append("")
    lines.append("DEFINE")

    current_folder = None
    for m in M:
        if m.folder != current_folder:
            current_folder = m.folder
            lines.append("")
            lines.append("// " + "-" * 74)
            lines.append(f"// {current_folder}")
            lines.append("// " + "-" * 74)
        lines.append("")
        for doc_line in _wrap(m.doc, 72):
            lines.append(f"// {doc_line}")
        lines.append(f"MEASURE {HOME_TABLE}[{m.name}] =")
        for body_line in m.expression.splitlines():
            lines.append(f"    {body_line}")
        lines.append(f"    FORMAT_STRING = \"{m.fmt}\"")

    lines.append("")
    lines.append("// " + "-" * 74)
    lines.append("// A DAX query must end in an EVALUATE. This one is a harmless receipt.")
    lines.append("// " + "-" * 74)
    lines.append("EVALUATE")
    lines.append(f'ROW ( "Measures in library", {len(M)} )')
    lines.append("")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> List[str]:
    words = text.split()
    out: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            out.append(current)
            current = word
        else:
            current = candidate
    if current:
        out.append(current)
    return out or [""]


# ===========================================================================
# Emit measures_tabular_editor.csx
# ===========================================================================
def build_csx() -> str:
    lines: List[str] = []
    lines.append("// " + "=" * 74)
    lines.append("// Seek My Service - Tabular Editor 2 measure deployment script")
    lines.append("//")
    lines.append("// GENERATED FILE - edit powerbi/build_measures.py and re-run it.")
    lines.append("//")
    lines.append("// HOW TO RUN")
    lines.append("//   1. Open the .pbix in Power BI Desktop with all tables loaded.")
    lines.append("//   2. External Tools ribbon > Tabular Editor.")
    lines.append("//   3. Advanced Scripting tab (bottom pane). Paste this whole file.")
    lines.append("//   4. Press F5 or the play button.")
    lines.append("//   5. File > Save (Ctrl+S) to push the changes back into Desktop.")
    lines.append("//   6. Back in Desktop, Refresh is NOT needed - measures are metadata.")
    lines.append("//")
    lines.append(f"// Creates or updates {len(M)} measures on '{HOME_TABLE}', each with its")
    lines.append("// display folder and format string. Re-running is safe: an existing")
    lines.append("// measure of the same name is updated in place rather than duplicated.")
    lines.append("// " + "=" * 74)
    lines.append("")
    lines.append(f'var home = Model.Tables["{HOME_TABLE}"];')
    lines.append("var created = 0;")
    lines.append("var updated = 0;")
    lines.append("")
    lines.append("// Create-or-update helper. Keeps the script idempotent.")
    lines.append("Action<string, string, string, string, string> upsert =")
    lines.append("    (name, expression, format, folder, description) =>")
    lines.append("{")
    lines.append("    var existing = home.Measures.FirstOrDefault(m => m.Name == name);")
    lines.append("    if (existing == null)")
    lines.append("    {")
    lines.append("        existing = home.AddMeasure(name);")
    lines.append("        created++;")
    lines.append("    }")
    lines.append("    else")
    lines.append("    {")
    lines.append("        updated++;")
    lines.append("    }")
    lines.append("    existing.Expression = expression;")
    lines.append("    existing.FormatString = format;")
    lines.append("    existing.DisplayFolder = folder;")
    lines.append("    existing.Description = description;")
    lines.append("};")
    lines.append("")

    current_folder = None
    for m in M:
        if m.folder != current_folder:
            current_folder = m.folder
            lines.append("")
            lines.append("// " + "-" * 74)
            lines.append(f"// {current_folder}")
            lines.append("// " + "-" * 74)
        expr = _csharp_verbatim(m.expression)
        lines.append(f'upsert("{m.name}",')
        lines.append(f"    {expr},")
        lines.append(f'    "{m.fmt}", "{m.folder}",')
        lines.append(f'    "{_csharp_plain(m.doc)}");')

    lines.append("")
    lines.append("// " + "-" * 74)
    lines.append("Info(")
    lines.append('    "Seek My Service measures deployed. Created: " + created')
    lines.append('    + ", updated: " + updated')
    lines.append('    + ". Remember to Save (Ctrl+S) to push them into Power BI Desktop."')
    lines.append(");")
    lines.append("")
    return "\n".join(lines)


def _csharp_verbatim(text: str) -> str:
    """Render a multi-line DAX body as a C# verbatim string literal."""
    escaped = text.replace('"', '""')
    return '@"' + escaped + '"'


def _csharp_plain(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


# ===========================================================================
# Entry point
# ===========================================================================
def main() -> int:
    names = [m.name for m in M]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        print(f"ERROR duplicate measure names: {sorted(duplicates)}")
        return 1
    missing_format = [m.name for m in M if not m.fmt]
    if missing_format:
        print(f"ERROR measures without a FORMAT_STRING: {missing_format}")
        return 1

    (OUT_DIR / "measures.dax").write_text(build_dax(), encoding="utf-8")
    (OUT_DIR / "measures_tabular_editor.csx").write_text(build_csx(), encoding="utf-8")

    folders: dict = {}
    for m in M:
        folders[m.folder] = folders.get(m.folder, 0) + 1

    print(f"measures defined: {len(M)}")
    for folder in sorted(folders):
        print(f"  {folder:<28}{folders[folder]:>4}")
    print()
    print(f"wrote {OUT_DIR / 'measures.dax'}")
    print(f"wrote {OUT_DIR / 'measures_tabular_editor.csx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
