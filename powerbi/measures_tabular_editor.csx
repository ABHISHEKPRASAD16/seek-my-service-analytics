// ==========================================================================
// Seek My Service - Tabular Editor 2 measure deployment script
//
// GENERATED FILE - edit powerbi/build_measures.py and re-run it.
//
// HOW TO RUN
//   1. Open the .pbix in Power BI Desktop with all tables loaded.
//   2. External Tools ribbon > Tabular Editor.
//   3. Advanced Scripting tab (bottom pane). Paste this whole file.
//   4. Press F5 or the play button.
//   5. File > Save (Ctrl+S) to push the changes back into Desktop.
//   6. Back in Desktop, Refresh is NOT needed - measures are metadata.
//
// Creates or updates 119 measures on 'fact_bookings', each with its
// display folder and format string. Re-running is safe: an existing
// measure of the same name is updated in place rather than duplicated.
// ==========================================================================

var home = Model.Tables["fact_bookings"];
var created = 0;
var updated = 0;

// Create-or-update helper. Keeps the script idempotent.
Action<string, string, string, string, string> upsert =
    (name, expression, format, folder, description) =>
{
    var existing = home.Measures.FirstOrDefault(m => m.Name == name);
    if (existing == null)
    {
        existing = home.AddMeasure(name);
        created++;
    }
    else
    {
        updated++;
    }
    existing.Expression = expression;
    existing.FormatString = format;
    existing.DisplayFolder = folder;
    existing.Description = description;
};


// --------------------------------------------------------------------------
// 01 Core
// --------------------------------------------------------------------------
upsert("Total Bookings",
    @"COUNTROWS ( fact_bookings )",
    "#,0", "01 Core",
    "Every booking row regardless of status. The denominator for the rate measures.");
upsert("Completed Jobs",
    @"CALCULATE (
    [Total Bookings],
    fact_bookings[BookingStatus] = ""Completed""
)",
    "#,0", "01 Core",
    "Bookings that were actually fulfilled. Only these carry money.");
upsert("Completion Rate",
    @"DIVIDE ( [Completed Jobs], [Total Bookings] )",
    "0.0%", "01 Core",
    "Share of bookings that reached a completed job.");
upsert("Cancelled Jobs",
    @"CALCULATE (
    [Total Bookings],
    fact_bookings[BookingStatus] IN { ""CancelledByCustomer"", ""CancelledByPro"" }
)",
    "#,0", "01 Core",
    "Cancellations from either side of the marketplace.");
upsert("Cancellation Rate",
    @"DIVIDE ( [Cancelled Jobs], [Total Bookings] )",
    "0.0%", "01 Core",
    "Combined cancellation rate. Rises on heavy monsoon days.");
upsert("Customer Cancellation Rate",
    @"DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = ""CancelledByCustomer"" ),
    [Total Bookings]
)",
    "0.0%", "01 Core",
    "Cancellations initiated by the customer.");
upsert("Pro Cancellation Rate",
    @"DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = ""CancelledByPro"" ),
    [Total Bookings]
)",
    "0.0%", "01 Core",
    "Cancellations initiated by the technician. A supply-reliability signal.");
upsert("No Show Rate",
    @"DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = ""NoShow"" ),
    [Total Bookings]
)",
    "0.0%", "01 Core",
    "Bookings where the technician never arrived.");
upsert("Reschedule Rate",
    @"DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[BookingStatus] = ""Rescheduled"" ),
    [Total Bookings]
)",
    "0.0%", "01 Core",
    "Bookings superseded by a rescheduled booking record.");
upsert("GMV INR",
    @"SUM ( fact_bookings[FinalAmountINR] )",
    "#,0", "01 Core",
    "Gross merchandise value: what customers paid, before the platform's cut.");
upsert("Platform Revenue INR",
    @"SUM ( fact_bookings[PlatformRevenueINR] )",
    "#,0", "01 Core",
    "The platform's commission. This is the company's actual top line.");
upsert("Take Rate Pct",
    @"DIVIDE ( [Platform Revenue INR], [GMV INR] )",
    "0.0%", "01 Core",
    "Platform revenue as a share of GMV. Mix-sensitive: painting drags it down.");
upsert("Avg Order Value",
    @"DIVIDE ( [GMV INR], [Completed Jobs] )",
    "#,0", "01 Core",
    "GMV per completed job.");
upsert("Material Cost INR",
    @"SUM ( fact_bookings[MaterialCostINR] )",
    "#,0", "01 Core",
    "Pass-through cost of materials on completed jobs.");
upsert("Net Revenue After Material INR",
    @"[GMV INR] - [Material Cost INR]",
    "#,0", "01 Core",
    "GMV net of materials. The real value the platform's labour creates.");
upsert("Gross Margin Pct",
    @"DIVIDE ( [Net Revenue After Material INR], [GMV INR] )",
    "0.0%", "01 Core",
    "Net-of-material revenue as a share of GMV.");
upsert("Quoted Amount INR",
    @"SUM ( fact_bookings[QuotedAmountINR] )",
    "#,0", "01 Core",
    "Total quoted before discounts and on-site scope changes.");
upsert("Discount Given INR",
    @"SUM ( fact_bookings[DiscountINR] )",
    "#,0", "01 Core",
    "Coupon and promotional value handed out.");
upsert("Discount Rate Pct",
    @"DIVIDE ( [Discount Given INR], [Quoted Amount INR] )",
    "0.0%", "01 Core",
    "Discount as a share of the quoted value.");

// --------------------------------------------------------------------------
// 02 Time Intelligence
// --------------------------------------------------------------------------
upsert("GMV INR PM",
    @"CALCULATE ( [GMV INR], DATEADD ( dim_date[Date], -1, MONTH ) )",
    "#,0", "02 Time Intelligence",
    "GMV in the equivalent prior month.");
upsert("GMV MoM Pct",
    @"DIVIDE ( [GMV INR] - [GMV INR PM], [GMV INR PM] )",
    "+0.0%;-0.0%;0.0%", "02 Time Intelligence",
    "Month-over-month change in GMV.");
upsert("GMV INR PY",
    @"CALCULATE ( [GMV INR], DATEADD ( dim_date[Date], -12, MONTH ) )",
    "#,0", "02 Time Intelligence",
    "GMV in the equivalent period one year earlier.");
upsert("GMV YoY Pct",
    @"DIVIDE ( [GMV INR] - [GMV INR PY], [GMV INR PY] )",
    "+0.0%;-0.0%;0.0%", "02 Time Intelligence",
    "Year-over-year change in GMV. Blank before Jan 2026, which is correct.");
upsert("Bookings PM",
    @"CALCULATE ( [Total Bookings], DATEADD ( dim_date[Date], -1, MONTH ) )",
    "#,0", "02 Time Intelligence",
    "Booking volume in the prior month.");
upsert("Bookings MoM Pct",
    @"DIVIDE ( [Total Bookings] - [Bookings PM], [Bookings PM] )",
    "+0.0%;-0.0%;0.0%", "02 Time Intelligence",
    "Month-over-month change in booking volume.");
upsert("Bookings PY",
    @"CALCULATE ( [Total Bookings], DATEADD ( dim_date[Date], -12, MONTH ) )",
    "#,0", "02 Time Intelligence",
    "Booking volume one year earlier.");
upsert("Bookings YoY Pct",
    @"DIVIDE ( [Total Bookings] - [Bookings PY], [Bookings PY] )",
    "+0.0%;-0.0%;0.0%", "02 Time Intelligence",
    "Year-over-year change in booking volume.");
upsert("Platform Revenue PM",
    @"CALCULATE ( [Platform Revenue INR], DATEADD ( dim_date[Date], -1, MONTH ) )",
    "#,0", "02 Time Intelligence",
    "Commission earned in the prior month.");
upsert("Platform Revenue MoM Pct",
    @"DIVIDE ( [Platform Revenue INR] - [Platform Revenue PM], [Platform Revenue PM] )",
    "+0.0%;-0.0%;0.0%", "02 Time Intelligence",
    "Month-over-month change in platform revenue.");
upsert("Platform Revenue PY",
    @"CALCULATE ( [Platform Revenue INR], DATEADD ( dim_date[Date], -12, MONTH ) )",
    "#,0", "02 Time Intelligence",
    "Commission earned one year earlier.");
upsert("Platform Revenue YoY Pct",
    @"DIVIDE ( [Platform Revenue INR] - [Platform Revenue PY], [Platform Revenue PY] )",
    "+0.0%;-0.0%;0.0%", "02 Time Intelligence",
    "Year-over-year change in platform revenue.");
upsert("GMV Rolling 28D Avg",
    @"DIVIDE (
    CALCULATE (
        [GMV INR],
        DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -28, DAY )
    ),
    28
)",
    "#,0", "02 Time Intelligence",
    "Average daily GMV over the trailing 28 days. Smooths the weekend sawtooth.");
upsert("Bookings Rolling 28D Avg",
    @"DIVIDE (
    CALCULATE (
        [Total Bookings],
        DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -28, DAY )
    ),
    28
)",
    "#,0", "02 Time Intelligence",
    "Average daily booking volume over the trailing 28 days.");
upsert("GMV 3M Moving Avg",
    @"DIVIDE (
    CALCULATE (
        [GMV INR],
        DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -3, MONTH )
    ),
    3
)",
    "#,0", "02 Time Intelligence",
    "Three-month moving average of monthly GMV.");
upsert("GMV YTD",
    @"CALCULATE ( [GMV INR], DATESYTD ( dim_date[Date] ) )",
    "#,0", "02 Time Intelligence",
    "Calendar year to date.");
upsert("GMV FYTD",
    @"VAR CurrentFY = MAX ( dim_date[FiscalYear] )
VAR LastDate = MAX ( dim_date[Date] )
RETURN
    CALCULATE (
        [GMV INR],
        REMOVEFILTERS ( dim_date ),
        dim_date[FiscalYear] = CurrentFY,
        dim_date[Date] <= LastDate
    )",
    "#,0", "02 Time Intelligence",
    "Indian fiscal year to date, April to March. Built from the FiscalYear column rather than a year-end string, so it is immune to locale.");
upsert("Platform Revenue FYTD",
    @"VAR CurrentFY = MAX ( dim_date[FiscalYear] )
VAR LastDate = MAX ( dim_date[Date] )
RETURN
    CALCULATE (
        [Platform Revenue INR],
        REMOVEFILTERS ( dim_date ),
        dim_date[FiscalYear] = CurrentFY,
        dim_date[Date] <= LastDate
    )",
    "#,0", "02 Time Intelligence",
    "Indian fiscal year to date commission.");

// --------------------------------------------------------------------------
// 03 Operations
// --------------------------------------------------------------------------
upsert("Avg Time To Assign",
    @"AVERAGE ( fact_bookings[TimeToAssignMins] )",
    "0.0", "03 Operations",
    "Minutes from booking created to a technician accepting it.");
upsert("Avg Response Time",
    @"AVERAGE ( fact_bookings[ResponseTimeMins] )",
    "0.0", "03 Operations",
    "Minutes from assignment to the technician confirming.");
upsert("SLA Met Pct",
    @"AVERAGE ( fact_bookings[SLAMetFlag] )",
    "0.0%", "03 Operations",
    "Share of completed jobs where the technician arrived inside the promised window.");
upsert("SLA Breach Count",
    @"CALCULATE (
    [Completed Jobs],
    fact_bookings[SLAMetFlag] = 0
)",
    "#,0", "03 Operations",
    "Completed jobs that missed the arrival promise.");
upsert("SLA Breach Pct",
    @"1 - [SLA Met Pct]",
    "0.0%", "03 Operations",
    "The complement of SLA Met Pct, for when a chart reads better upside down.");
upsert("Avg Job Duration",
    @"AVERAGE ( fact_bookings[JobDurationMins] )",
    "0.0", "03 Operations",
    "Average on-site minutes for completed jobs.");
upsert("First Time Fix Pct",
    @"AVERAGE ( fact_bookings[IsFirstTimeFix] )",
    "0.0%", "03 Operations",
    "Share of completed jobs resolved without a return visit.");
upsert("Reopen Rate",
    @"AVERAGE ( fact_bookings[ReopenedWithin7Days] )",
    "0.0%", "03 Operations",
    "Completed jobs reopened within seven days. The quality tail.");
upsert("Avg Actual ETA",
    @"AVERAGE ( fact_bookings[ActualETAMins] )",
    "0.0", "03 Operations",
    "Average realised arrival time in minutes.");
upsert("Capacity Strain Index",
    @"VAR DaysInContext = COUNTROWS ( VALUES ( dim_date[Date] ) )
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
    DIVIDE ( CurrentDaily, TrailingDaily )",
    "0.00", "03 Operations",
    "Average daily volume in context divided by the trailing 30-day daily average. Above 1.0 means the day is running hotter than the recent norm, and SLA breaches track it closely.");
upsert("Emergency Job Pct",
    @"DIVIDE (
    CALCULATE ( [Total Bookings], dim_service[IsEmergency] = 1 ),
    [Total Bookings]
)",
    "0.0%", "03 Operations",
    "Share of bookings for services flagged as emergency call-outs.");

// --------------------------------------------------------------------------
// 04 Funnel and Demand
// --------------------------------------------------------------------------
upsert("Search Volume",
    @"SUM ( fact_leads[Searches] )",
    "#,0", "04 Funnel and Demand",
    "Searches performed, at day x area x service grain.");
upsert("Lead Volume",
    @"SUM ( fact_leads[Leads] )",
    "#,0", "04 Funnel and Demand",
    "Searches that turned into an identified lead.");
upsert("Quotes Sent",
    @"SUM ( fact_leads[QuotesSent] )",
    "#,0", "04 Funnel and Demand",
    "Leads that received at least one quote.");
upsert("Funnel Bookings",
    @"SUM ( fact_leads[Bookings] )",
    "#,0", "04 Funnel and Demand",
    "Bookings as counted inside the funnel fact. Reconciles exactly to Total Bookings.");
upsert("Search to Lead Pct",
    @"DIVIDE ( [Lead Volume], [Search Volume] )",
    "0.0%", "04 Funnel and Demand",
    "First funnel step.");
upsert("Lead to Quote Pct",
    @"DIVIDE ( [Quotes Sent], [Lead Volume] )",
    "0.0%", "04 Funnel and Demand",
    "Second funnel step. Weak values here mean a supply coverage problem.");
upsert("Quote to Booking Pct",
    @"DIVIDE ( [Funnel Bookings], [Quotes Sent] )",
    "0.0%", "04 Funnel and Demand",
    "Third funnel step. Structurally weaker in low demand-tier areas.");
upsert("Search to Booking Pct",
    @"DIVIDE ( [Funnel Bookings], [Search Volume] )",
    "0.0%", "04 Funnel and Demand",
    "End-to-end conversion. The single number the growth team lives on.");
upsert("Avg Lead Quality",
    @"AVERAGE ( fact_leads[AvgLeadQualityScore] )",
    "0.000", "04 Funnel and Demand",
    "Mean lead_quality_scorer output for the cell.");
upsert("Unconverted Searches",
    @"[Search Volume] - [Funnel Bookings]",
    "#,0", "04 Funnel and Demand",
    "Search interest that produced no booking at all. Where the money is leaking.");
upsert("Demand Coverage Pct",
    @"VAR TotalCells = COUNTROWS ( fact_leads )
VAR ConvertedCells = CALCULATE ( COUNTROWS ( fact_leads ), fact_leads[Bookings] > 0 )
RETURN
    DIVIDE ( ConvertedCells, TotalCells )",
    "0.0%", "04 Funnel and Demand",
    "Share of searched cells that produced at least one booking.");

// --------------------------------------------------------------------------
// 05 Customer
// --------------------------------------------------------------------------
upsert("Total Customers",
    @"DISTINCTCOUNT ( fact_bookings[CustomerKey] )",
    "#,0", "05 Customer",
    "Distinct customers who booked in the current filter context.");
upsert("New Customers",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    fact_bookings[IsRepeatCustomer] = 0
)",
    "#,0", "05 Customer",
    "Customers placing their first ever booking in the period.");
upsert("Repeat Customers",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    fact_bookings[IsRepeatCustomer] = 1
)",
    "#,0", "05 Customer",
    "Customers booking again, having booked before.");
upsert("Repeat Rate",
    @"DIVIDE (
    CALCULATE ( [Total Bookings], fact_bookings[IsRepeatCustomer] = 1 ),
    [Total Bookings]
)",
    "0.0%", "05 Customer",
    "Share of bookings placed by returning customers.");
upsert("Customer Signups",
    @"CALCULATE (
    COUNTROWS ( dim_customer ),
    USERELATIONSHIP ( dim_customer[SignupDate], dim_date[Date] )
)",
    "#,0", "05 Customer",
    "Accounts created in the period, via the inactive SignupDate relationship. Signups lead first bookings, so this and New Customers differ by design.");
upsert("Active Customers 90D",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -90, DAY )
)",
    "#,0", "05 Customer",
    "Distinct customers with a booking in the trailing 90 days.");
upsert("Rated Jobs",
    @"CALCULATE (
    COUNTROWS ( fact_bookings ),
    fact_bookings[CustomerRating] IN { 1, 2, 3, 4, 5 }
)",
    "#,0", "05 Customer",
    "Completed jobs that received a star rating.");
upsert("Rated Job Pct",
    @"DIVIDE ( [Rated Jobs], [Completed Jobs] )",
    "0.0%", "05 Customer",
    "Response rate on the rating prompt. Roughly 62% by design.");
upsert("Avg CSAT",
    @"AVERAGE ( fact_bookings[CustomerRating] )",
    "0.00", "05 Customer",
    "Mean customer star rating, 1 to 5.");
upsert("NPS Proxy",
    @"VAR Promoters = CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[CustomerRating] = 5 )
VAR Detractors = CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[CustomerRating] IN { 1, 2, 3 } )
RETURN
    DIVIDE ( Promoters - Detractors, [Rated Jobs] ) * 100",
    "0", "05 Customer",
    "Net promoter proxy from stars: 5 promotes, 4 is passive, 3 and below detracts. Explicit value lists keep blank ratings out of the detractor bucket.");
upsert("Negative Review Pct",
    @"DIVIDE (
    CALCULATE ( COUNTROWS ( fact_bookings ), fact_bookings[ReviewSentiment] = ""Negative"" ),
    [Rated Jobs]
)",
    "0.0%", "05 Customer",
    "Share of rated jobs whose sentiment came back negative.");
upsert("Avg LTV INR",
    @"AVERAGE ( dim_customer[LifetimeValueINR] )",
    "#,0", "05 Customer",
    "Mean lifetime value across customers in context.");
upsert("Customer Acquisition Mix Pct",
    @"DIVIDE (
    [New Customers],
    CALCULATE ( [New Customers], REMOVEFILTERS ( dim_customer[AcquisitionChannel] ) )
)",
    "0.0%", "05 Customer",
    "Each acquisition channel's share of new customers. Put this on a bar chart beside Repeat Rate and the paid-social quality gap is impossible to miss.");
upsert("Bookings per Customer",
    @"DIVIDE ( [Total Bookings], [Total Customers] )",
    "0.00", "05 Customer",
    "Average bookings per distinct customer in context.");

// --------------------------------------------------------------------------
// 06 Professional Supply
// --------------------------------------------------------------------------
upsert("Active Pros",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_pro_capacity[ProKey] ),
    fact_pro_capacity[SlotsBooked] > 0
)",
    "#,0", "06 Professional Supply",
    "Technicians who worked at least one job in the period.");
upsert("Pros Online",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_pro_capacity[ProKey] ),
    fact_pro_capacity[IsOnline] = 1
)",
    "#,0", "06 Professional Supply",
    "Technicians who opened a calendar at all, whether or not they got work.");
upsert("Roster Size",
    @"COUNTROWS ( dim_professional )",
    "#,0", "06 Professional Supply",
    "Technicians on the books, active or churned.");
upsert("Slots Available",
    @"SUM ( fact_pro_capacity[SlotsAvailable] )",
    "#,0", "06 Professional Supply",
    "Capacity the roster actually opened.");
upsert("Slots Booked",
    @"SUM ( fact_pro_capacity[SlotsBooked] )",
    "#,0", "06 Professional Supply",
    "Capacity consumed by real bookings.");
upsert("Pro Utilization Pct",
    @"DIVIDE ( [Slots Booked], [Slots Available] )",
    "0.0%", "06 Professional Supply",
    "Booked slots over available slots. Low in aggregate and brutally unequal across the roster, which is the point worth showing.");
upsert("Jobs per Active Pro",
    @"DIVIDE ( [Completed Jobs], [Active Pros] )",
    "0.0", "06 Professional Supply",
    "Completed jobs divided by technicians who worked.");
upsert("Pro Acceptance Rate",
    @"DIVIDE (
    SUM ( fact_pro_capacity[AcceptedJobs] ),
    SUM ( fact_pro_capacity[AcceptedJobs] ) + SUM ( fact_pro_capacity[RejectedJobs] )
)",
    "0.0%", "06 Professional Supply",
    "Offers accepted over offers received.");
upsert("Hours Logged",
    @"DIVIDE ( SUM ( fact_pro_capacity[HoursLoggedMins] ), 60 )",
    "#,0", "06 Professional Supply",
    "Total technician hours on the platform, converted from logged minutes.");
upsert("Pros At Risk",
    @"CALCULATE (
    COUNTROWS ( dim_professional ),
    dim_professional[IsActive] = 1,
    dim_professional[AvgRating] < 4.0
)",
    "#,0", "06 Professional Supply",
    "Active technicians whose shrunk rating sits below 4.0. Ratings are shrunk towards a tier prior, so a low score here means sustained poor performance rather than one bad week.");
upsert("Avg Pro Rating",
    @"AVERAGE ( dim_professional[AvgRating] )",
    "0.00", "06 Professional Supply",
    "Mean shrunk rating across technicians in context.");
upsert("New Pro Onboarding Count",
    @"CALCULATE (
    COUNTROWS ( dim_professional ),
    USERELATIONSHIP ( dim_professional[JoinDate], dim_date[Date] )
)",
    "#,0", "06 Professional Supply",
    "Technicians who joined in the period, via the inactive JoinDate relationship.");
upsert("Churned Pros",
    @"CALCULATE (
    COUNTROWS ( dim_professional ),
    dim_professional[IsActive] = 0
)",
    "#,0", "06 Professional Supply",
    "Technicians who have left the platform.");
upsert("Supply Demand Gap",
    @"[Lead Volume] - [Slots Available]",
    "#,0", "06 Professional Supply",
    "Demand signal minus opened capacity. Positive means more interest than the roster can serve. VALID BY AREA AND DATE ONLY: fact_pro_capacity carries no service key, so slicing this by service or category leaves the capacity half unfiltered and the number becomes nonsense. Use it on the area map and the area-by-month matrix, nowhere else.");
upsert("Verified Pro Pct",
    @"DIVIDE (
    CALCULATE ( COUNTROWS ( dim_professional ), dim_professional[IsBackgroundVerified] = 1 ),
    [Roster Size]
)",
    "0.0%", "06 Professional Supply",
    "Share of the roster that has passed background verification.");

// --------------------------------------------------------------------------
// 07 ML Health
// --------------------------------------------------------------------------
upsert("Metric Value Avg",
    @"AVERAGE ( fact_model_metrics[MetricValue] )",
    "0.000", "07 ML Health",
    "Mean of whatever primary metric the model in context reports. Units differ by model, so only ever show this filtered to a single model.");
upsert("Metric Goal Avg",
    @"AVERAGE ( fact_model_metrics[MetricGoal] )",
    "0.000", "07 ML Health",
    "The model's target for its primary metric.");
upsert("Models In Breach",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_model_metrics[ModelKey] ),
    fact_model_metrics[IsBreach] = 1
)",
    "#,0", "07 ML Health",
    "Distinct models missing their goal in the period.");
upsert("Breach Day Pct",
    @"AVERAGE ( fact_model_metrics[IsBreach] )",
    "0.0%", "07 ML Health",
    "Share of model-days spent in breach.");
upsert("Avg PSI Drift",
    @"AVERAGE ( fact_model_metrics[PSIDriftScore] )",
    "0.000", "07 ML Health",
    "Mean population stability index across models in context.");
upsert("Models Drifting",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_model_metrics[ModelKey] ),
    fact_model_metrics[PSIDriftScore] > 0.25
)",
    "#,0", "07 ML Health",
    "Distinct models whose PSI has crossed the 0.25 alert threshold.");
upsert("Model Freshness Days",
    @"AVERAGE ( fact_model_metrics[TrainingDataAgeDays] )",
    "0", "07 ML Health",
    "Mean age of the training data behind live predictions. The measure that would have caught the silent retrain failure in March 2026.");
upsert("Max Training Data Age",
    @"MAX ( fact_model_metrics[TrainingDataAgeDays] )",
    "0", "07 ML Health",
    "Worst training-data age in context. Climbs from 15 March 2026 to 126 days.");
upsert("P95 Latency Ms",
    @"MAX ( fact_model_metrics[P95LatencyMs] )",
    "0", "07 ML Health",
    "Worst daily p95 serving latency in context.");
upsert("Total Prediction Volume",
    @"SUM ( fact_model_metrics[PredictionVolume] )",
    "#,0", "07 ML Health",
    "Predictions served.");
upsert("Avg Feature Null Pct",
    @"AVERAGE ( fact_model_metrics[FeatureNullPct] )",
    "0.00", "07 ML Health",
    "Mean share of null feature values entering the models.");
upsert("Forecast MAPE",
    @"AVERAGE ( fact_forecast_accuracy[APE] )",
    "0.0%", "07 ML Health",
    "Mean absolute percentage error of the demand forecaster. APE is stored as a fraction so percent formatting works natively.");
upsert("Forecast WAPE",
    @"DIVIDE (
    SUM ( fact_forecast_accuracy[AbsError] ),
    SUM ( fact_forecast_accuracy[ActualJobs] )
)",
    "0.0%", "07 ML Health",
    "Volume-weighted absolute percentage error. More honest than MAPE when many cells carry only one or two jobs.");
upsert("Forecast Bias Pct",
    @"DIVIDE (
    SUM ( fact_forecast_accuracy[ForecastedJobs] ) - SUM ( fact_forecast_accuracy[ActualJobs] ),
    SUM ( fact_forecast_accuracy[ActualJobs] )
)",
    "+0.0%;-0.0%;0.0%", "07 ML Health",
    "Signed error. Positive means the model forecasts more demand than turns up.");
upsert("Forecasted Jobs",
    @"SUM ( fact_forecast_accuracy[ForecastedJobs] )",
    "#,0", "07 ML Health",
    "Total jobs the forecaster expected.");
upsert("Actual Jobs",
    @"SUM ( fact_forecast_accuracy[ActualJobs] )",
    "#,0", "07 ML Health",
    "Total jobs that actually happened, on the forecast grain.");
upsert("Phantom Demand Cells",
    @"CALCULATE (
    COUNTROWS ( fact_forecast_accuracy ),
    fact_forecast_accuracy[ActualJobs] = 0
)",
    "#,0", "07 ML Health",
    "Cells where the model forecast work that never arrived. The failure mode worth staring at, because it is what pre-positions supply into empty streets.");
upsert("Price Prediction MAE",
    @"CALCULATE (
    AVERAGEX (
        fact_bookings,
        ABS ( fact_bookings[PredictedPriceINR] - fact_bookings[FinalAmountINR] )
    ),
    fact_bookings[BookingStatus] = ""Completed""
)",
    "#,0", "07 ML Health",
    "Mean absolute rupee error of the price engine against the final amount.");
upsert("Price MAPE",
    @"CALCULATE (
    AVERAGEX (
        fact_bookings,
        DIVIDE (
            ABS ( fact_bookings[PredictedPriceINR] - fact_bookings[FinalAmountINR] ),
            fact_bookings[FinalAmountINR]
        )
    ),
    fact_bookings[BookingStatus] = ""Completed""
)",
    "0.0%", "07 ML Health",
    "Price engine error as a share of the amount actually charged.");
upsert("ETA RMSE",
    @"SQRT (
    CALCULATE (
        AVERAGEX (
            fact_bookings,
            ( fact_bookings[PredictedETAMins] - fact_bookings[ActualETAMins] ) ^ 2
        ),
        fact_bookings[BookingStatus] = ""Completed""
    )
)",
    "0.0", "07 ML Health",
    "Root mean squared error in minutes of the arrival-time predictor.");
upsert("Match Score Avg",
    @"AVERAGE ( fact_bookings[MatchScore] )",
    "0.000", "07 ML Health",
    "Mean ranker confidence in the technician it chose.");
upsert("Fraud Caught Value INR",
    @"CALCULATE (
    SUM ( fact_bookings[QuotedAmountINR] ),
    fact_bookings[FraudScore] > 0.6
)",
    "#,0", "07 ML Health",
    "Quoted value of bookings the detector flagged above 0.6. Not all of it is genuine fraud, which is exactly why precision is the goal metric.");
upsert("High Churn Risk Customers",
    @"CALCULATE (
    DISTINCTCOUNT ( fact_bookings[CustomerKey] ),
    fact_bookings[ChurnRiskScore] > 0.7
)",
    "#,0", "07 ML Health",
    "Distinct customers whose latest churn score exceeds 0.7.");

// --------------------------------------------------------------------------
// 08 Utility
// --------------------------------------------------------------------------
upsert("Model KPI Status",
    @"VAR Value = [Metric Value Avg]
VAR Goal = [Metric Goal Avg]
VAR Direction = SELECTEDVALUE ( dim_model[GoalDirection], ""HigherIsBetter"" )
VAR Ratio = DIVIDE ( Value, Goal )
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Value ), ""No Data"",
        Direction = ""LowerIsBetter"" && Ratio <= 0.90, ""On Target"",
        Direction = ""LowerIsBetter"" && Ratio <= 1.00, ""Watch"",
        Direction = ""LowerIsBetter"", ""Breach"",
        Ratio >= 1.05, ""On Target"",
        Ratio >= 1.00, ""Watch"",
        ""Breach""
    )",
    "@", "08 Utility",
    "Traffic light for the model in context, honouring GoalDirection so a lower MAPE and a higher AUC both read as good.");
upsert("SLA KPI Status",
    @"VAR Value = [SLA Met Pct]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Value ), ""No Data"",
        Value >= 0.90, ""On Target"",
        Value >= 0.90 - 0.05, ""Watch"",
        ""Breach""
    )",
    "@", "08 Utility",
    "Traffic light for service level against the 0.90 promise.");
upsert("KPI Status Colour",
    @"SWITCH (
    [SLA KPI Status],
    ""On Target"", ""#1B9E77"",
    ""Watch"", ""#E6A700"",
    ""Breach"", ""#D6455D"",
    ""#8A8F98""
)",
    "@", "08 Utility",
    "Hex colour to drive conditional formatting by field value. Matches THEME.json.");
upsert("Ops Page Title",
    @"VAR AreaLabel =
    IF (
        ISFILTERED ( dim_area[AreaName] ),
        CONCATENATEX ( VALUES ( dim_area[AreaName] ), dim_area[AreaName], "", "" ),
        ""All Bengaluru""
    )
RETURN
    ""Ops Control Room  |  "" & AreaLabel & ""  |  ""
        & FORMAT ( MIN ( dim_date[Date] ), ""dd MMM yyyy"" ) & "" to ""
        & FORMAT ( MAX ( dim_date[Date] ), ""dd MMM yyyy"" )",
    "@", "08 Utility",
    "Dynamic page header reflecting the active area and date slicers.");
upsert("Demand Page Title",
    @"VAR CategoryLabel =
    IF (
        ISFILTERED ( dim_service[ServiceCategory] ),
        CONCATENATEX ( VALUES ( dim_service[ServiceCategory] ), dim_service[ServiceCategory], "", "" ),
        ""All categories""
    )
RETURN
    ""Demand Intelligence  |  "" & CategoryLabel & ""  |  ""
        & FORMAT ( [Search to Booking Pct], ""0.0%"" ) & "" search to booking""",
    "@", "08 Utility",
    "Dynamic page header for the Demand Intelligence page.");
upsert("Supply Page Title",
    @"""Supply Health  |  "" & FORMAT ( [Active Pros], ""#,0"" ) & "" active of ""
    & FORMAT ( [Roster Size], ""#,0"" ) & "" on roster  |  ""
    & FORMAT ( [Pro Utilization Pct], ""0.0%"" ) & "" utilisation""",
    "@", "08 Utility",
    "Dynamic page header for the Supply Health page.");
upsert("ML Page Title",
    @"VAR Breached = [Models In Breach]
RETURN
    ""ML Model Health  |  ""
        & IF ( Breached = 0, ""all models on target"", FORMAT ( Breached, ""#,0"" ) & "" model(s) in breach"" )
        & ""  |  "" & FORMAT ( MAX ( dim_date[Date] ), ""dd MMM yyyy"" )",
    "@", "08 Utility",
    "Dynamic page header for the ML Model Health page.");
upsert("Selected Date Range Label",
    @"FORMAT ( MIN ( dim_date[Date] ), ""dd MMM yyyy"" ) & ""  to  ""
    & FORMAT ( MAX ( dim_date[Date] ), ""dd MMM yyyy"" )",
    "@", "08 Utility",
    "Human-readable label for the active date slicer.");

// --------------------------------------------------------------------------
Info(
    "Seek My Service measures deployed. Created: " + created
    + ", updated: " + updated
    + ". Remember to Save (Ctrl+S) to push them into Power BI Desktop."
);
