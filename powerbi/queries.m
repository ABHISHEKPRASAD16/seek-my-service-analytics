// ============================================================================
// Seek My Service - Power Query M
//
// One query per table, with every column typed explicitly. Nothing is left to
// type inference, because inference is what silently turns a pincode into a
// number and drops the leading zero, or reads a blank integer column as text
// on Tuesday and as a number on Wednesday.
//
// HOW TO USE
//   1. Create the parameter first (see PARAMETER below). Name it exactly
//      DataFolder - every query references it by that name.
//   2. For each table: Home > Get data > Blank query > Advanced Editor,
//      paste the block, and rename the query to the table name.
//   3. Close & Apply.
//
// Repointing the whole model at a new folder is then a single parameter edit
// (Home > Transform data > Manage Parameters), not eleven query edits.
//
// A note on culture. Every Table.TransformColumnTypes call passes "en-US"
// explicitly. The CSVs use ISO YYYY-MM-DD dates and "." as the decimal
// separator, which is what en-US expects. Without the explicit culture these
// queries would behave differently on a machine set to a dd/MM locale, which
// is a genuinely nasty class of bug to chase in a client's environment.
//
// Encoding 65001 is UTF-8. The generator writes UTF-8 without a BOM.
// ============================================================================


// ============================================================================
// PARAMETER: DataFolder
// ----------------------------------------------------------------------------
// Home > Transform data > Manage Parameters > New Parameter
//     Name:            DataFolder
//     Type:            Text
//     Suggested values: Any value
//     Current value:   D:\Seek_My_Services\data
//
// Or paste the single line below into a Blank Query named DataFolder.
// Do not include a trailing backslash - each query adds its own separator.
// ============================================================================

"D:\Seek_My_Services\data" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]


// ============================================================================
// dim_date          608 rows, 20 columns
// The date table. Mark this as the model's date table on the Date column.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_date.csv"),
        [Delimiter = ",", Columns = 20, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"DateKey", Int64.Type},
            {"Date", type date},
            {"Year", Int64.Type},
            {"Quarter", type text},
            {"MonthNo", Int64.Type},
            {"MonthName", type text},
            {"MonthYear", type text},
            {"MonthYearSort", Int64.Type},
            {"WeekNo", Int64.Type},
            {"DayName", type text},
            {"DayOfWeekNo", Int64.Type},
            {"IsWeekend", Int64.Type},
            {"IsMonsoon", Int64.Type},
            {"IsFestivalWindow", Int64.Type},
            {"FestivalName", type text},
            {"IsMonthEnd", Int64.Type},
            {"FiscalYear", type text},
            {"FiscalQuarter", type text},
            {"IsHoliday", Int64.Type},
            {"DaysFromToday", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// dim_service       37 rows, 10 columns
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_service.csv"),
        [Delimiter = ",", Columns = 10, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"ServiceKey", Int64.Type},
            {"ServiceCategory", type text},
            {"ServiceName", type text},
            {"BasePriceINR", Int64.Type},
            {"AvgDurationMins", Int64.Type},
            {"IsEmergency", Int64.Type},
            {"SkillTier", type text},
            {"MaterialCostPct", type number},
            {"CommissionPct", type number},
            {"ServiceSortOrder", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// dim_area          20 rows, 9 columns
// Pincode stays TEXT on purpose. Bengaluru pincodes happen not to start with a
// zero, but treating a postal code as a number is a habit that breaks the
// moment this model meets a Chennai or Delhi dataset.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_area.csv"),
        [Delimiter = ",", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"AreaKey", Int64.Type},
            {"AreaName", type text},
            {"Zone", type text},
            {"Pincode", type text},
            {"Latitude", type number},
            {"Longitude", type number},
            {"DemandTier", type text},
            {"IncomeBand", type text},
            {"AreaSortOrder", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// dim_professional  850 rows, 13 columns
// ChurnedDate is blank for active technicians and becomes null when typed.
// JoinDate must be a real date type: an inactive relationship runs from it to
// dim_date[Date] to drive [New Pro Onboarding Count].
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_professional.csv"),
        [Delimiter = ",", Columns = 13, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"ProKey", Int64.Type},
            {"ProName", type text},
            {"PrimaryServiceCategory", type text},
            {"HomeAreaKey", Int64.Type},
            {"JoinDate", type date},
            {"SkillTier", type text},
            {"IsBackgroundVerified", Int64.Type},
            {"IsActive", Int64.Type},
            {"AvgRating", type number},
            {"LifetimeJobs", Int64.Type},
            {"LanguagesSpoken", type text},
            {"OnboardingChannel", type text},
            {"ChurnedDate", type date}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// dim_customer      24,000 rows, 11 columns
// SignupDate carries an inactive relationship to dim_date[Date] for the
// [Customer Signups] measure.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_customer.csv"),
        [Delimiter = ",", Columns = 11, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"CustomerKey", Int64.Type},
            {"SignupDate", type date},
            {"AreaKey", Int64.Type},
            {"AcquisitionChannel", type text},
            {"Segment", type text},
            {"IsAppUser", Int64.Type},
            {"PreferredLanguage", type text},
            {"LifetimeValueINR", type number},
            {"FirstBookingDate", type date},
            {"LastBookingDate", type date},
            {"TotalBookings", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// dim_model         8 rows, 14 columns
// MetricGoal is a plain number in each model's own units: 12.0 is 12 percent
// MAPE for the forecaster, 0.82 is an NDCG for the ranker, 14.0 is minutes for
// the ETA model. Never aggregate this column across models.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_model.csv"),
        [Delimiter = ",", Columns = 14, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"ModelKey", Int64.Type},
            {"ModelName", type text},
            {"ModelType", type text},
            {"BusinessPurpose", type text},
            {"Framework", type text},
            {"Algorithm", type text},
            {"PrimaryMetric", type text},
            {"MetricGoal", type number},
            {"GoalDirection", type text},
            {"DeployedDate", type date},
            {"Version", type text},
            {"RefreshCadence", type text},
            {"OwnerTeam", type text},
            {"IsBusinessCritical", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// fact_bookings     ~58,000 rows, 31 columns
// The grain is one row per booking.
//
// Several columns are deliberately blank on non-completed bookings and become
// null here: JobDurationMins, SLAMetFlag, ActualETAMins, IsFirstTimeFix,
// ReopenedWithin7Days. CustomerRating and ReviewSentiment are additionally
// blank on the ~38% of completed jobs nobody rated. Leave them null - do NOT
// replace with zero, or every average in the model silently shifts.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_bookings.csv"),
        [Delimiter = ",", Columns = 31, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"BookingID", type text},
            {"DateKey", Int64.Type},
            {"BookingTimestamp", type datetime},
            {"CustomerKey", Int64.Type},
            {"ProKey", Int64.Type},
            {"ServiceKey", Int64.Type},
            {"AreaKey", Int64.Type},
            {"Channel", type text},
            {"BookingStatus", type text},
            {"QuotedAmountINR", Currency.Type},
            {"FinalAmountINR", Currency.Type},
            {"DiscountINR", Currency.Type},
            {"CommissionPct", type number},
            {"PlatformRevenueINR", Currency.Type},
            {"MaterialCostINR", Currency.Type},
            {"PaymentMode", type text},
            {"TimeToAssignMins", Int64.Type},
            {"ResponseTimeMins", Int64.Type},
            {"JobDurationMins", Int64.Type},
            {"SLAMetFlag", Int64.Type},
            {"CustomerRating", Int64.Type},
            {"ReviewSentiment", type text},
            {"IsRepeatCustomer", Int64.Type},
            {"PredictedPriceINR", Int64.Type},
            {"PredictedETAMins", Int64.Type},
            {"ActualETAMins", Int64.Type},
            {"MatchScore", type number},
            {"FraudScore", type number},
            {"ChurnRiskScore", type number},
            {"IsFirstTimeFix", Int64.Type},
            {"ReopenedWithin7Days", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// fact_pro_capacity ~324,000 rows, 9 columns
// The grain is one row per technician per day they were on the roster.
// This is the table that makes utilisation and the supply-demand gap real
// measures rather than proxies.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_pro_capacity.csv"),
        [Delimiter = ",", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"DateKey", Int64.Type},
            {"ProKey", Int64.Type},
            {"AreaKey", Int64.Type},
            {"SlotsAvailable", Int64.Type},
            {"SlotsBooked", Int64.Type},
            {"IsOnline", Int64.Type},
            {"HoursLoggedMins", Int64.Type},
            {"AcceptedJobs", Int64.Type},
            {"RejectedJobs", Int64.Type}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// fact_leads        ~74,000 rows, 8 columns
// The grain is day x area x service. Only cells with at least one search are
// emitted. Searches >= Leads >= QuotesSent >= Bookings holds on every row.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_leads.csv"),
        [Delimiter = ",", Columns = 8, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"DateKey", Int64.Type},
            {"AreaKey", Int64.Type},
            {"ServiceKey", Int64.Type},
            {"Searches", Int64.Type},
            {"Leads", Int64.Type},
            {"QuotesSent", Int64.Type},
            {"Bookings", Int64.Type},
            {"AvgLeadQualityScore", type number}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// fact_model_metrics ~3,500 rows, 12 columns
// The grain is day x model, starting at each model's DeployedDate.
// MetricValue is in the model's own units - see the dim_model note above.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_model_metrics.csv"),
        [Delimiter = ",", Columns = 12, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"DateKey", Int64.Type},
            {"ModelKey", Int64.Type},
            {"MetricName", type text},
            {"MetricValue", type number},
            {"MetricGoal", type number},
            {"IsBreach", Int64.Type},
            {"PSIDriftScore", type number},
            {"PredictionVolume", Int64.Type},
            {"P95LatencyMs", Int64.Type},
            {"FeatureNullPct", type number},
            {"TrainingDataAgeDays", Int64.Type},
            {"ModelVersion", type text}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// fact_forecast_accuracy ~47,000 rows, 7 columns
// The grain is day x area x service category.
//
// APE is a FRACTION (0.0923 means 9.23%), so a "0.0%" format string in Power
// BI displays it correctly with no arithmetic in the measure. It is blank
// wherever ActualJobs is 0, because dividing by zero is not an error worth
// inventing a number for.
//
// ServiceCategory is a text key joining to dim_service[ServiceCategory]. See
// RELATIONSHIPS.md - this needs a bridge, not a direct relationship, because
// ServiceCategory is not unique in dim_service.
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_forecast_accuracy.csv"),
        [Delimiter = ",", Columns = 7, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(
        Promoted,
        {
            {"DateKey", Int64.Type},
            {"AreaKey", Int64.Type},
            {"ServiceCategory", type text},
            {"ForecastedJobs", type number},
            {"ActualJobs", Int64.Type},
            {"AbsError", type number},
            {"APE", type number}
        },
        "en-US"
    )
in
    Typed


// ============================================================================
// dim_category      8 rows, 1 column - DERIVED, no CSV behind it
//
// fact_forecast_accuracy joins on ServiceCategory, which is not unique in
// dim_service (37 services share 8 categories), so it cannot be the one side
// of a relationship. This one-column bridge fixes that without inventing a
// surrogate key the source system does not have.
//
// Wire it as: dim_category[ServiceCategory] 1 -> * fact_forecast_accuracy
//             dim_category[ServiceCategory] 1 -> * dim_service
// ============================================================================
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_service.csv"),
        [Delimiter = ",", Columns = 10, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Categories = Table.Distinct(Table.SelectColumns(Promoted, {"ServiceCategory"})),
    Typed = Table.TransformColumnTypes(Categories, {{"ServiceCategory", type text}}, "en-US"),
    Sorted = Table.Sort(Typed, {{"ServiceCategory", Order.Ascending}})
in
    Sorted
