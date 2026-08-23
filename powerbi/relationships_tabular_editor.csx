// ==========================================================================
// Seek My Service - Tabular Editor 2 relationship deployment script
//
// Creates all 19 relationships: 17 active, 2 inactive.
//
// Building these by hand means 19 drag-and-drop operations in Model view, each
// with a cardinality and a cross-filter direction to set. One wrong drop gives
// a model that still "works" and quietly returns wrong numbers. Scripting them
// makes the star schema a reviewable artefact rather than a diagram someone
// drew once.
//
// HOW TO RUN
//   1. Open the .pbix in Power BI Desktop with all 12 tables loaded.
//   2. External Tools ribbon > Tabular Editor.
//   3. Advanced Scripting tab (bottom pane). Paste this whole file.
//   4. Press F5.
//   5. File > Save (Ctrl+S) to push the changes back into Desktop.
//
// RUN THIS BEFORE the measures script: four measures reference relationships
// by name via USERELATIONSHIP and will error until they exist.
//
// Re-running is safe. Every existing relationship is removed first, so the
// result is the same whether the model arrives clean or with Power BI's
// auto-detected guesses already in place.
// ==========================================================================

// --------------------------------------------------------------------------
// 1. Clear whatever is there
//
// Power BI auto-detects relationships on load by matching column names. Some
// of its guesses are right, some are not, and one in particular is actively
// wrong here: dim_customer[AreaKey] to dim_area[AreaKey] creates a second
// filter path to fact_bookings and makes the model ambiguous. Starting from
// empty is cheaper than auditing its guesses.
// --------------------------------------------------------------------------
var existing = Model.Relationships.ToList();
foreach (var r in existing) r.Delete();

int made = 0;

// --------------------------------------------------------------------------
// Helper: many-to-one, single direction, dimension filters fact.
// --------------------------------------------------------------------------
Action<string, string, string, string, bool> link =
    (fromTable, fromColumn, toTable, toColumn, isActive) =>
{
    var rel = Model.AddRelationship();
    rel.FromColumn = Model.Tables[fromTable].Columns[fromColumn];
    rel.ToColumn = Model.Tables[toTable].Columns[toColumn];
    rel.FromCardinality = RelationshipEndCardinality.Many;
    rel.ToCardinality = RelationshipEndCardinality.One;
    rel.CrossFilteringBehavior = CrossFilteringBehavior.OneDirection;
    rel.IsActive = isActive;
    made++;
};

// --------------------------------------------------------------------------
// 2. fact_bookings - the central fact
// --------------------------------------------------------------------------
link("fact_bookings", "DateKey",     "dim_date",         "DateKey",     true);
link("fact_bookings", "ServiceKey",  "dim_service",      "ServiceKey",  true);
link("fact_bookings", "AreaKey",     "dim_area",         "AreaKey",     true);
link("fact_bookings", "ProKey",      "dim_professional", "ProKey",      true);
link("fact_bookings", "CustomerKey", "dim_customer",     "CustomerKey", true);

// --------------------------------------------------------------------------
// 3. fact_pro_capacity - the supply side
// --------------------------------------------------------------------------
link("fact_pro_capacity", "DateKey", "dim_date",         "DateKey", true);
link("fact_pro_capacity", "ProKey",  "dim_professional", "ProKey",  true);
link("fact_pro_capacity", "AreaKey", "dim_area",         "AreaKey", true);

// --------------------------------------------------------------------------
// 4. fact_leads - the funnel
// --------------------------------------------------------------------------
link("fact_leads", "DateKey",    "dim_date",    "DateKey",    true);
link("fact_leads", "AreaKey",    "dim_area",    "AreaKey",    true);
link("fact_leads", "ServiceKey", "dim_service", "ServiceKey", true);

// --------------------------------------------------------------------------
// 5. fact_model_metrics - ML telemetry
// --------------------------------------------------------------------------
link("fact_model_metrics", "DateKey",  "dim_date",  "DateKey",  true);
link("fact_model_metrics", "ModelKey", "dim_model", "ModelKey", true);

// --------------------------------------------------------------------------
// 6. fact_forecast_accuracy - joins on category TEXT, via the bridge
//
// dim_service[ServiceCategory] holds 37 rows across 8 categories, so it is not
// unique and cannot be the "one" side. dim_category exists for exactly this.
// --------------------------------------------------------------------------
link("fact_forecast_accuracy", "DateKey",         "dim_date",     "DateKey",         true);
link("fact_forecast_accuracy", "AreaKey",         "dim_area",     "AreaKey",         true);
link("fact_forecast_accuracy", "ServiceCategory", "dim_category", "ServiceCategory", true);
link("dim_service",            "ServiceCategory", "dim_category", "ServiceCategory", true);

// --------------------------------------------------------------------------
// 7. Inactive relationships, activated by USERELATIONSHIP
//
// Both dimensions already reach dim_date through a fact table. A second active
// path would be ambiguous, so these stay inactive and are switched on inside
// the two measures that specifically want to count joiners and signups rather
// than workers and bookers.
// --------------------------------------------------------------------------
link("dim_professional", "JoinDate",   "dim_date", "Date", false);   // [New Pro Onboarding Count]
link("dim_customer",     "SignupDate", "dim_date", "Date", false);   // [Customer Signups]

// --------------------------------------------------------------------------
// 8. Hide the plumbing from report view
//
// Key columns are joins, not analysis fields. A field list with 31 booking
// columns in it is hostile to anyone trying to self-serve later.
//
// dim_service[ServiceCategory] is hidden for a sharper reason: slicing from it
// filters bookings and leads but leaves fact_forecast_accuracy wide open, so a
// "forecast vs actual by category" visual would show the same forecast against
// every category. Hiding it means the only category field a report author can
// reach is the correct one on dim_category.
// --------------------------------------------------------------------------
int hidden = 0;
foreach (var table in Model.Tables)
{
    foreach (var column in table.Columns)
    {
        bool isKey = column.Name.EndsWith("Key");
        bool isServiceCategoryOnService =
            table.Name == "dim_service" && column.Name == "ServiceCategory";

        if (isKey || isServiceCategoryOnService)
        {
            if (!column.IsHidden) { column.IsHidden = true; hidden++; }
        }
    }
}

// Sort-by columns, so months and areas order correctly instead of alphabetically.
Action<string, string, string> sortBy = (table, column, by) =>
{
    Model.Tables[table].Columns[column].SortByColumn = Model.Tables[table].Columns[by];
};
sortBy("dim_date",    "MonthYear",   "MonthYearSort");
sortBy("dim_date",    "MonthName",   "MonthNo");
sortBy("dim_date",    "DayName",     "DayOfWeekNo");
sortBy("dim_area",    "AreaName",    "AreaSortOrder");
sortBy("dim_service", "ServiceName", "ServiceSortOrder");

// The sort-by columns themselves are plumbing too.
Model.Tables["dim_date"].Columns["MonthYearSort"].IsHidden = true;
Model.Tables["dim_area"].Columns["AreaSortOrder"].IsHidden = true;
Model.Tables["dim_service"].Columns["ServiceSortOrder"].IsHidden = true;

Info(
    "Relationships created: " + made + " (17 active, 2 inactive). "
    + "Hidden " + hidden + " key columns, set 5 sort-by columns.\n\n"
    + "NEXT: 1) Save here (Ctrl+S).  "
    + "2) In Power BI, mark dim_date as the date table on the Date column.  "
    + "3) Run measures_tabular_editor.csx."
);
