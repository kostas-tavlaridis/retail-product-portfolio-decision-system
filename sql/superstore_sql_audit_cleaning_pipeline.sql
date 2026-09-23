# ==================================================================================================
# SUPERSTORE SQL DATA AUDIT
#
# AUDIT FLOW
# 1) Source ingestion and source-to-database reconciliation
# 2) Grain and entity-cardinality validation
# 3) Entity consistency and functional-dependency validation
# 4) Technical/business key investigation and duplicate-candidate analysis
# 5) Individual field-validity controls
# 6) Cross-field business-rule controls
#
# IMPORTANT:
# This script is an AUDIT script. At this stage we identify, quantify and investigate issues.
# We do NOT yet modify the raw source values.
# Cleaning decisions and transformations are applied only after the audit is complete.
# ==================================================================================================


# ==================================================================================================
# 1) SOURCE INGESTION + BASELINE RECONCILIATION
#
# Objective:
# - Preserve the raw source structure without forcing datatypes during ingestion.
# - Load the CSV explicitly.
# - Reconcile important source-level control totals before any analytical work begins.
# ==================================================================================================

USE superstore_project;

DROP TABLE IF EXISTS raw_superstore;

CREATE TABLE raw_superstore (`Row ID` TEXT, `Order ID` TEXT, `Order Date` TEXT, `Ship Date` TEXT, `Ship Mode` TEXT, `Customer ID` TEXT, `Customer Name` TEXT, `Segment` TEXT, `Country` TEXT, `City` TEXT, `State` TEXT, `Postal Code` TEXT, `Region` TEXT, `Product ID` TEXT, `Category` TEXT, `Sub-Category` TEXT, `Product Name` TEXT, `Sales` TEXT, `Quantity` TEXT, `Discount` TEXT, `Profit` TEXT) DEFAULT CHARACTER SET utf8mb4;

# Confirm that the newly created raw table is empty before ingestion.
SELECT COUNT(*) AS current_rows FROM raw_superstore;

# Enable LOAD DATA LOCAL INFILE on the MySQL server for the current ingestion workflow.
SET GLOBAL local_infile = 1;

# Confirm that local_infile has been enabled.
SHOW GLOBAL VARIABLES LIKE 'local_infile';

# Replace the placeholder below with the local path of the downloaded Kaggle CSV.
# Load the source CSV while preserving all source fields as TEXT.
LOAD DATA LOCAL INFILE '/path/to/Sample - Superstore.csv' INTO TABLE raw_superstore CHARACTER SET latin1 FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' LINES TERMINATED BY '\r\n' IGNORE 1 LINES;

# Visual ingestion sanity check.
SELECT * FROM raw_superstore LIMIT 10;

# Baseline reconciliation:
# Establish control totals that will later be compared with the cleaned dataset.
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT `Order ID`) AS total_orders, COUNT(DISTINCT `Customer ID`) AS total_customers, COUNT(DISTINCT `Product ID`) AS total_products, SUM(CAST(TRIM(`Sales`) AS DECIMAL(18,4))) AS total_sales, SUM(CAST(TRIM(`Profit`) AS DECIMAL(18,4))) AS total_profit FROM raw_superstore;


# ==================================================================================================
# 2) GRAIN + CARDINALITY VALIDATION
#
# Objective:
# - Determine what one raw row represents.
# - Validate the main entity relationships observed in the source.
#
# Working grain hypothesis:
# One raw row represents a transaction/order line that belongs to an Order.
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 2.1 CUSTOMER 1:N ORDER
#
# Check both sides of the relationship:
# - Each Order ID should map to one Customer ID.
# - A Customer ID may map to one or more distinct Order IDs.
# --------------------------------------------------------------------------------------------------

SELECT `Order ID`, COUNT(DISTINCT `Customer ID`) AS customers_per_order FROM raw_superstore GROUP BY `Order ID`;

SELECT `Customer ID`, COUNT(DISTINCT `Order ID`) AS orders_per_customer FROM raw_superstore GROUP BY `Customer ID`;


# --------------------------------------------------------------------------------------------------
# 2.2 ORDER 1:N TRANSACTION LINE + RAW GRAIN
#
# Aggregate the raw data to Order level and compare:
# - number of raw rows per Order
# - number of distinct Products per Order
# - number of distinct Order Dates per Order
#
# This helps verify that one Order can span multiple raw rows and that these rows generally
# represent line-level product content rather than complete Orders.
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS order_checking;

CREATE TEMPORARY TABLE order_checking AS SELECT `Order ID`, COUNT(`Row ID`) AS number_of_rows, COUNT(DISTINCT `Product ID`) AS number_of_products, COUNT(DISTINCT `Order Date`) AS number_of_order_dates FROM raw_superstore GROUP BY `Order ID`;

# Identify Orders where the number of raw rows exceeds the number of distinct Products.
# These are useful collision cases for later business-key / duplicate investigation.
SELECT `Order ID`, number_of_rows, number_of_products FROM order_checking WHERE number_of_rows != number_of_products;

# Validate Order ID -> Order Date consistency.
SELECT `Order ID`, number_of_rows, number_of_order_dates FROM order_checking WHERE number_of_order_dates > 1;


# ==================================================================================================
# 3) ENTITY CONSISTENCY + FUNCTIONAL DEPENDENCIES
#
# Objective:
# Test whether attributes that should describe the same entity remain consistent every time
# that entity appears in the raw transaction-line table.
#
# Functional dependency A -> B means:
# For each value of A, only one consistent value of B should be observed.
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 3.1 ORDER ENTITY
#
# Already validated:
# Order ID -> Customer ID
# Order ID -> Order Date
#
# Additional hypotheses:
# Order ID -> Ship Date
# Order ID -> Ship Mode
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS dates_checking;

CREATE TEMPORARY TABLE dates_checking AS SELECT `Order ID`, COUNT(`Row ID`) AS number_of_rows, COUNT(DISTINCT `Product ID`) AS number_of_products, COUNT(DISTINCT `Ship Date`) AS number_of_ship_dates, COUNT(DISTINCT `Ship Mode`) AS number_of_ship_modes FROM raw_superstore GROUP BY `Order ID`;

# Return only Order IDs that have inconsistent Ship Date or Ship Mode values.
SELECT `Order ID`, number_of_rows, number_of_products, number_of_ship_dates, number_of_ship_modes FROM dates_checking WHERE number_of_ship_dates > 1 OR number_of_ship_modes > 1;


# --------------------------------------------------------------------------------------------------
# 3.2 CUSTOMER ENTITY
#
# Test:
# Customer ID -> Customer Name
# Customer ID -> Segment
#
# A returned row would mean that the same Customer ID is associated with multiple names or segments.
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS cx_checking;

CREATE TEMPORARY TABLE cx_checking AS SELECT `Customer ID`, COUNT(`Row ID`) AS number_of_rows, COUNT(DISTINCT `Customer Name`) AS number_of_names, COUNT(DISTINCT `Segment`) AS number_of_segments FROM raw_superstore GROUP BY `Customer ID`;

SELECT `Customer ID`, number_of_rows, number_of_names, number_of_segments FROM cx_checking WHERE number_of_names > 1 OR number_of_segments > 1;


# --------------------------------------------------------------------------------------------------
# 3.3 PRODUCT ENTITY
#
# Test:
# Product ID -> Product Name ?
# Product ID -> Category ?
# Product ID -> Sub-Category ?
#
# Any Product ID associated with multiple values is isolated for further investigation.
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS product_checking;

CREATE TEMPORARY TABLE product_checking AS SELECT `Product ID`, COUNT(`Row ID`) AS number_of_rows, COUNT(DISTINCT `Product Name`) AS number_of_product_names, COUNT(DISTINCT `Category`) AS number_of_categories, COUNT(DISTINCT `Sub-Category`) AS number_of_subcategories FROM raw_superstore GROUP BY `Product ID`;

DROP TEMPORARY TABLE IF EXISTS product_investigate;

CREATE TEMPORARY TABLE product_investigate AS SELECT `Product ID`, number_of_rows, number_of_product_names, number_of_categories, number_of_subcategories FROM product_checking WHERE number_of_product_names > 1 OR number_of_categories > 1 OR number_of_subcategories > 1;

# Review the Product IDs that violate at least one expected product-level dependency.
SELECT * FROM product_investigate;

# Join the violating Product IDs back to the raw rows so the actual Product Name / classification combinations can be inspected.
DROP TEMPORARY TABLE IF EXISTS joined_products;

CREATE TEMPORARY TABLE joined_products SELECT R.`Product ID`, R.`Product Name`, R.`Category`, R.`Sub-Category` FROM raw_superstore AS R JOIN product_investigate AS P ON P.`Product ID` = R.`Product ID`;

SELECT * FROM joined_products;

# Summarise how frequently each Product ID + Product Name + Category + Sub-Category combination occurs.
SELECT `Product ID`, `Product Name`, `Category`, `Sub-Category`, COUNT(*) AS occurrences FROM joined_products GROUP BY `Product ID`, `Product Name`, `Category`, `Sub-Category`;


# --------------------------------------------------------------------------------------------------
# 3.4 PRODUCT HIERARCHY
#
# Test:
# Sub-Category -> Category
#
# Each Sub-Category should consistently belong to one Category.
# --------------------------------------------------------------------------------------------------

SELECT `Sub-Category`, COUNT(DISTINCT `Category`) AS categories_per_subcategory FROM raw_superstore GROUP BY `Sub-Category`;


# --------------------------------------------------------------------------------------------------
# 3.5 GEOGRAPHY CONSISTENCY
#
# Test:
# State -> Region
# State -> Country
#
# Each State should consistently map to one Region and one Country in this dataset.
# --------------------------------------------------------------------------------------------------

SELECT `State`, COUNT(DISTINCT `Region`) AS regions_per_state, COUNT(DISTINCT `Country`) AS countries_per_state FROM raw_superstore GROUP BY `State`;


# ==================================================================================================
# 4) KEY INVESTIGATION + DUPLICATE CANDIDATES
#
# Objective:
# - Validate the technical row identifier.
# - Test a business/natural key candidate for the transaction-line grain.
# - Investigate collisions instead of automatically deleting them.
#
# Technical key candidate:
# Row ID
#
# Business line-key candidate:
# Order ID + Product ID + Product Name
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 4.1 TECHNICAL KEY
#
# A technical key must uniquely identify every raw row.
# Compare total row count with distinct Row ID count.
# --------------------------------------------------------------------------------------------------

SELECT COUNT(*) AS total_rows, COUNT(DISTINCT `Row ID`) AS total_unique_row_ids FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 4.2 BUSINESS KEY CANDIDATE
#
# Count how many times every Order ID + Product ID + Product Name combination appears.
# occurrence > 1 means the candidate business key does not uniquely identify a raw line.
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS bkey1;

CREATE TEMPORARY TABLE bkey1 AS SELECT `Order ID`, `Product ID`, `Product Name`, COUNT(*) AS occurrences FROM raw_superstore GROUP BY `Order ID`, `Product ID`, `Product Name`;


# --------------------------------------------------------------------------------------------------
# 4.3 BUSINESS-KEY COLLISIONS / DUPLICATE CANDIDATES
#
# Keep only combinations appearing at least twice.
# These are duplicate candidates, not automatically confirmed duplicates.
# Their actual raw rows must be inspected to determine whether measures differ.
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS bkey2;

CREATE TEMPORARY TABLE bkey2 AS SELECT * FROM bkey1 WHERE occurrences > 1;

SELECT * FROM bkey2;

# Join using the full candidate business key so only the colliding raw lines are returned.
SELECT * FROM raw_superstore AS R JOIN bkey2 AS P ON P.`Order ID` = R.`Order ID` AND P.`Product ID` = R.`Product ID` AND P.`Product Name` = R.`Product Name`;


# ==================================================================================================
# 5) FIELD VALIDITY CONTROLS
#
# Objective:
# Evaluate each field independently before any cleaning transformation.
#
# Main families:
# a) Technical ID
# b) Business IDs
# c) Dates
# d) Categories
# e) Free text
# f) Postal Code
# g) Monetary numeric
# h) Integer numeric
# i) Ratio numeric
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 5.a TECHNICAL ID
#
# Field: Row ID
# Checks:
# - uniqueness
# - NULL
# - blank
# - integer-looking format
# - positive numeric value
# --------------------------------------------------------------------------------------------------

SELECT COUNT(DISTINCT `Row ID`) AS unique_rows, COUNT(CASE WHEN TRIM(`Row ID`) = '' THEN 1 END) AS blank_rows, COUNT(CASE WHEN `Row ID` IS NULL THEN 1 END) AS null_rows, COUNT(CASE WHEN TRIM(`Row ID`) REGEXP '^[0-9]+$' THEN 1 END) AS integer_rows, COUNT(CASE WHEN TRIM(`Row ID`) REGEXP '^[0-9]+$' AND CAST(TRIM(`Row ID`) AS UNSIGNED) > 0 THEN 1 END) AS positive_rows FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 5.b BUSINESS IDs
#
# Fields:
# Order ID, Customer ID, Product ID
#
# Checks:
# - NULL values
# - blank / whitespace-only values
# - leading/trailing whitespace
# - expected ID structure using REGEXP
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Order ID` IS NULL THEN 1 END) AS order_null_rows, COUNT(CASE WHEN `Customer ID` IS NULL THEN 1 END) AS customer_null_rows, COUNT(CASE WHEN `Product ID` IS NULL THEN 1 END) AS product_null_rows, COUNT(CASE WHEN TRIM(`Order ID`) = '' THEN 1 END) AS order_blank_rows, COUNT(CASE WHEN TRIM(`Customer ID`) = '' THEN 1 END) AS customer_blank_rows, COUNT(CASE WHEN TRIM(`Product ID`) = '' THEN 1 END) AS product_blank_rows, COUNT(CASE WHEN `Order ID` <> TRIM(`Order ID`) THEN 1 END) AS order_trim_issues, COUNT(CASE WHEN `Customer ID` <> TRIM(`Customer ID`) THEN 1 END) AS customer_trim_issues, COUNT(CASE WHEN `Product ID` <> TRIM(`Product ID`) THEN 1 END) AS product_trim_issues, COUNT(CASE WHEN TRIM(`Order ID`) REGEXP '^[A-Z]{2}-[0-9]{4}-[0-9]{6}$' THEN 1 END) AS order_correct_format_rows, COUNT(CASE WHEN TRIM(`Customer ID`) REGEXP '^[A-Z]{2}-[0-9]{5}$' THEN 1 END) AS customer_correct_format_rows, COUNT(CASE WHEN TRIM(`Product ID`) REGEXP '^[A-Z]{3}-[A-Z]{2}-[0-9]{8}$' THEN 1 END) AS product_correct_format_rows FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 5.c DATES
#
# Fields:
# Order Date, Ship Date
#
# Checks:
# - NULL / blank
# - parseability from raw TEXT into DATE
# - observed minimum / maximum dates
#
# STR_TO_DATE converts the raw MM/DD/YYYY text into a real DATE value.
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Order Date` IS NULL THEN 1 END) AS order_date_null_rows, COUNT(CASE WHEN `Ship Date` IS NULL THEN 1 END) AS ship_date_null_rows, COUNT(CASE WHEN TRIM(`Order Date`) = '' THEN 1 END) AS order_date_blank_rows, COUNT(CASE WHEN TRIM(`Ship Date`) = '' THEN 1 END) AS ship_date_blank_rows, COUNT(CASE WHEN STR_TO_DATE(TRIM(`Order Date`), '%m/%d/%Y') IS NOT NULL THEN 1 END) AS valid_order_date_rows, COUNT(CASE WHEN STR_TO_DATE(TRIM(`Ship Date`), '%m/%d/%Y') IS NOT NULL THEN 1 END) AS valid_ship_date_rows, MIN(STR_TO_DATE(TRIM(`Order Date`), '%m/%d/%Y')) AS min_order_date, MAX(STR_TO_DATE(TRIM(`Order Date`), '%m/%d/%Y')) AS max_order_date, MIN(STR_TO_DATE(TRIM(`Ship Date`), '%m/%d/%Y')) AS min_ship_date, MAX(STR_TO_DATE(TRIM(`Ship Date`), '%m/%d/%Y')) AS max_ship_date FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 5.d CATEGORICAL FIELDS
#
# Fields:
# Ship Mode, Segment, Country, Region, Category, Sub-Category
#
# Checks:
# 1) NULL / blank / leading-trailing whitespace
# 2) distinct values + frequencies
# 3) expected domain
# --------------------------------------------------------------------------------------------------


# 5.d.1 NULL / BLANK / WHITESPACE
SELECT COUNT(CASE WHEN `Ship Mode` IS NULL THEN 1 END) AS ship_mode_null, COUNT(CASE WHEN TRIM(`Ship Mode`) = '' THEN 1 END) AS ship_mode_blank, COUNT(CASE WHEN `Ship Mode` <> TRIM(`Ship Mode`) THEN 1 END) AS ship_mode_trim_issues, COUNT(CASE WHEN `Segment` IS NULL THEN 1 END) AS segment_null, COUNT(CASE WHEN TRIM(`Segment`) = '' THEN 1 END) AS segment_blank, COUNT(CASE WHEN `Segment` <> TRIM(`Segment`) THEN 1 END) AS segment_trim_issues, COUNT(CASE WHEN `Country` IS NULL THEN 1 END) AS country_null, COUNT(CASE WHEN TRIM(`Country`) = '' THEN 1 END) AS country_blank, COUNT(CASE WHEN `Country` <> TRIM(`Country`) THEN 1 END) AS country_trim_issues, COUNT(CASE WHEN `Region` IS NULL THEN 1 END) AS region_null, COUNT(CASE WHEN TRIM(`Region`) = '' THEN 1 END) AS region_blank, COUNT(CASE WHEN `Region` <> TRIM(`Region`) THEN 1 END) AS region_trim_issues, COUNT(CASE WHEN `Category` IS NULL THEN 1 END) AS category_null, COUNT(CASE WHEN TRIM(`Category`) = '' THEN 1 END) AS category_blank, COUNT(CASE WHEN `Category` <> TRIM(`Category`) THEN 1 END) AS category_trim_issues, COUNT(CASE WHEN `Sub-Category` IS NULL THEN 1 END) AS subcategory_null, COUNT(CASE WHEN TRIM(`Sub-Category`) = '' THEN 1 END) AS subcategory_blank, COUNT(CASE WHEN `Sub-Category` <> TRIM(`Sub-Category`) THEN 1 END) AS subcategory_trim_issues FROM raw_superstore;


# 5.d.2 DISTINCT VALUES + FREQUENCIES
# Each query returns one row per categorical value and the number of raw rows containing it.

SELECT `Ship Mode`, COUNT(*) AS frequency FROM raw_superstore GROUP BY `Ship Mode` ORDER BY frequency DESC;

SELECT `Segment`, COUNT(*) AS frequency FROM raw_superstore GROUP BY `Segment` ORDER BY frequency DESC;

SELECT `Country`, COUNT(*) AS frequency FROM raw_superstore GROUP BY `Country` ORDER BY frequency DESC;

SELECT `Region`, COUNT(*) AS frequency FROM raw_superstore GROUP BY `Region` ORDER BY frequency DESC;

SELECT `Category`, COUNT(*) AS frequency FROM raw_superstore GROUP BY `Category` ORDER BY frequency DESC;

SELECT `Sub-Category`, COUNT(*) AS frequency FROM raw_superstore GROUP BY `Sub-Category` ORDER BY frequency DESC;


# 5.d.3 DOMAIN CHECKS
# Return only categorical values outside the expected source/business domain.

SELECT DISTINCT `Ship Mode` FROM raw_superstore WHERE TRIM(`Ship Mode`) NOT IN ('Standard Class', 'Second Class', 'First Class', 'Same Day');

SELECT DISTINCT `Segment` FROM raw_superstore WHERE TRIM(`Segment`) NOT IN ('Consumer', 'Corporate', 'Home Office');

SELECT DISTINCT `Country` FROM raw_superstore WHERE TRIM(`Country`) NOT IN ('United States');

SELECT DISTINCT `Region` FROM raw_superstore WHERE TRIM(`Region`) NOT IN ('Central', 'East', 'South', 'West');

SELECT DISTINCT `Category` FROM raw_superstore WHERE TRIM(`Category`) NOT IN ('Furniture', 'Office Supplies', 'Technology');

SELECT DISTINCT `Sub-Category` FROM raw_superstore WHERE TRIM(`Sub-Category`) NOT IN ('Accessories', 'Appliances', 'Art', 'Binders', 'Bookcases', 'Chairs', 'Copiers', 'Envelopes', 'Fasteners', 'Furnishings', 'Labels', 'Machines', 'Paper', 'Phones', 'Storage', 'Supplies', 'Tables');


# --------------------------------------------------------------------------------------------------
# 5.e FREE-TEXT FIELDS
#
# Fields:
# Customer Name, Product Name, City, State
#
# Checks:
# - NULL / blank
# - leading/trailing whitespace
# - repeated internal whitespace
# - control characters
# - observed string-length range
#
# No strict character pattern is imposed because legitimate free text may contain spaces,
# numbers, punctuation, apostrophes, commas, etc.
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Customer Name` IS NULL THEN 1 END) AS customer_name_null, COUNT(CASE WHEN TRIM(`Customer Name`) = '' THEN 1 END) AS customer_name_blank, COUNT(CASE WHEN `Customer Name` <> TRIM(`Customer Name`) THEN 1 END) AS customer_name_trim_issues, COUNT(CASE WHEN `Customer Name` REGEXP '[[:space:]]{2,}' THEN 1 END) AS customer_name_internal_whitespace_issues, COUNT(CASE WHEN `Customer Name` REGEXP '[[:cntrl:]]' THEN 1 END) AS customer_name_control_char_issues, MIN(CHAR_LENGTH(TRIM(`Customer Name`))) AS min_customer_name_length, MAX(CHAR_LENGTH(TRIM(`Customer Name`))) AS max_customer_name_length, COUNT(CASE WHEN `Product Name` IS NULL THEN 1 END) AS product_name_null, COUNT(CASE WHEN TRIM(`Product Name`) = '' THEN 1 END) AS product_name_blank, COUNT(CASE WHEN `Product Name` <> TRIM(`Product Name`) THEN 1 END) AS product_name_trim_issues, COUNT(CASE WHEN `Product Name` REGEXP '[[:space:]]{2,}' THEN 1 END) AS product_name_internal_whitespace_issues, COUNT(CASE WHEN `Product Name` REGEXP '[[:cntrl:]]' THEN 1 END) AS product_name_control_char_issues, MIN(CHAR_LENGTH(TRIM(`Product Name`))) AS min_product_name_length, MAX(CHAR_LENGTH(TRIM(`Product Name`))) AS max_product_name_length, COUNT(CASE WHEN `City` IS NULL THEN 1 END) AS city_null, COUNT(CASE WHEN TRIM(`City`) = '' THEN 1 END) AS city_blank, COUNT(CASE WHEN `City` <> TRIM(`City`) THEN 1 END) AS city_trim_issues, COUNT(CASE WHEN `City` REGEXP '[[:space:]]{2,}' THEN 1 END) AS city_internal_whitespace_issues, COUNT(CASE WHEN `City` REGEXP '[[:cntrl:]]' THEN 1 END) AS city_control_char_issues, MIN(CHAR_LENGTH(TRIM(`City`))) AS min_city_name_length, MAX(CHAR_LENGTH(TRIM(`City`))) AS max_city_name_length, COUNT(CASE WHEN `State` IS NULL THEN 1 END) AS state_null, COUNT(CASE WHEN TRIM(`State`) = '' THEN 1 END) AS state_blank, COUNT(CASE WHEN `State` <> TRIM(`State`) THEN 1 END) AS state_trim_issues, COUNT(CASE WHEN `State` REGEXP '[[:space:]]{2,}' THEN 1 END) AS state_internal_whitespace_issues, COUNT(CASE WHEN `State` REGEXP '[[:cntrl:]]' THEN 1 END) AS state_control_char_issues, MIN(CHAR_LENGTH(TRIM(`State`))) AS min_state_name_length, MAX(CHAR_LENGTH(TRIM(`State`))) AS max_state_name_length FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 5.f POSTAL CODE
#
# Postal Code is treated as a CODE / IDENTIFIER, not as a numeric measure.
#
# Checks:
# - NULL / blank
# - leading/trailing whitespace
# - digits-only representation
# - observed character-length range
#
# Important modelling decision:
# The clean field should remain TEXT/VARCHAR so leading zeros are preserved.
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Postal Code` IS NULL THEN 1 END) AS postal_code_null_rows, COUNT(CASE WHEN TRIM(`Postal Code`) = '' THEN 1 END) AS postal_code_blank_rows, COUNT(CASE WHEN `Postal Code` <> TRIM(`Postal Code`) THEN 1 END) AS postal_code_trim_issues, COUNT(CASE WHEN TRIM(`Postal Code`) REGEXP '^[0-9]+$' THEN 1 END) AS postal_code_valid_format_rows, MIN(CHAR_LENGTH(TRIM(`Postal Code`))) AS min_postal_code_length, MAX(CHAR_LENGTH(TRIM(`Postal Code`))) AS max_postal_code_length FROM raw_superstore;

# Investigation:
# Four-character ZIP codes were identified.
# Inspect their City/State context to determine whether a leading zero was lost upstream.
SELECT `Postal Code`, `City`, `State`, COUNT(*) AS occurrences FROM raw_superstore WHERE CHAR_LENGTH(TRIM(`Postal Code`)) = 4 GROUP BY `Postal Code`, `City`, `State` ORDER BY `State`, `City`;


# --------------------------------------------------------------------------------------------------
# 5.g MONETARY NUMERIC FIELDS
#
# Fields:
# Sales, Profit
#
# Checks:
# - NULL / blank
# - valid numeric-string representation
# - observed numeric range
#
# REGEXP validates the raw TEXT representation.
# CAST converts validated text into a true numeric value for numeric calculations.
#
# DECIMAL(18,4):
# - maximum 18 total digits
# - maximum 4 digits after the decimal point
# - preferred to DOUBLE for monetary values because decimal values are stored exactly
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Sales` IS NULL THEN 1 END) AS sales_null_rows, COUNT(CASE WHEN TRIM(`Sales`) = '' THEN 1 END) AS sales_blank_rows, COUNT(CASE WHEN `Profit` IS NULL THEN 1 END) AS profit_null_rows, COUNT(CASE WHEN TRIM(`Profit`) = '' THEN 1 END) AS profit_blank_rows, COUNT(CASE WHEN TRIM(`Sales`) REGEXP '^[0-9]+([.][0-9]+)?$' THEN 1 END) AS sales_valid_numeric_rows, COUNT(CASE WHEN TRIM(`Profit`) REGEXP '^-?[0-9]+([.][0-9]+)?$' THEN 1 END) AS profit_valid_numeric_rows, MIN(CAST(TRIM(`Sales`) AS DECIMAL(18,4))) AS min_sales, MAX(CAST(TRIM(`Sales`) AS DECIMAL(18,4))) AS max_sales, MIN(CAST(TRIM(`Profit`) AS DECIMAL(18,4))) AS min_profit, MAX(CAST(TRIM(`Profit`) AS DECIMAL(18,4))) AS max_profit FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 5.h INTEGER NUMERIC FIELD
#
# Field:
# Quantity
#
# Checks:
# - NULL / blank
# - integer-only representation
# - positive value (>0)
# - observed numeric range
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Quantity` IS NULL THEN 1 END) AS quantity_null_rows, COUNT(CASE WHEN TRIM(`Quantity`) = '' THEN 1 END) AS quantity_blank_rows, COUNT(CASE WHEN TRIM(`Quantity`) REGEXP '^[0-9]+$' THEN 1 END) AS quantity_valid_integer_rows, COUNT(CASE WHEN TRIM(`Quantity`) REGEXP '^[0-9]+$' AND CAST(TRIM(`Quantity`) AS UNSIGNED) > 0 THEN 1 END) AS quantity_positive_rows, MIN(CAST(TRIM(`Quantity`) AS UNSIGNED)) AS min_quantity, MAX(CAST(TRIM(`Quantity`) AS UNSIGNED)) AS max_quantity FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 5.i RATIO NUMERIC FIELD
#
# Field:
# Discount
#
# Checks:
# - NULL / blank
# - valid non-negative numeric representation
# - valid business range [0,1]
# - observed range
#
# Discount is represented as a ratio:
# 0.00 = 0%
# 0.20 = 20%
# 1.00 = 100%
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN `Discount` IS NULL THEN 1 END) AS discount_null_rows, COUNT(CASE WHEN TRIM(`Discount`) = '' THEN 1 END) AS discount_blank_rows, COUNT(CASE WHEN TRIM(`Discount`) REGEXP '^[0-9]+([.][0-9]+)?$' THEN 1 END) AS discount_valid_numeric_rows, COUNT(CASE WHEN TRIM(`Discount`) REGEXP '^[0-9]+([.][0-9]+)?$' AND CAST(TRIM(`Discount`) AS DECIMAL(10,4)) BETWEEN 0 AND 1 THEN 1 END) AS discount_valid_range_rows, MIN(CAST(TRIM(`Discount`) AS DECIMAL(10,4))) AS min_discount, MAX(CAST(TRIM(`Discount`) AS DECIMAL(10,4))) AS max_discount FROM raw_superstore;


# ==================================================================================================
# 6) CROSS-FIELD BUSINESS RULES
#
# Objective:
# Individual values can be valid on their own but still be inconsistent when compared
# with other fields in the same business record.
#
# These checks therefore validate relationships between multiple columns.
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 6.a ORDER DATE + SHIP DATE
#
# Rule:
# Ship Date should be on or after Order Date.
#
# Also calculate shipping delay in days and inspect the observed min/max delay.
# Negative delay would indicate an invalid date relationship.
# --------------------------------------------------------------------------------------------------

WITH date_check AS (SELECT DATEDIFF(STR_TO_DATE(TRIM(`Ship Date`), '%m/%d/%Y'), STR_TO_DATE(TRIM(`Order Date`), '%m/%d/%Y')) AS shipping_delay FROM raw_superstore) SELECT COUNT(CASE WHEN shipping_delay < 0 THEN 1 END) AS order_ship_date_issues, MIN(shipping_delay) AS min_shipping_delay, MAX(shipping_delay) AS max_shipping_delay FROM date_check;


# --------------------------------------------------------------------------------------------------
# 6.b SALES + PROFIT
#
# Profit may legitimately be negative, zero or positive.
#
# Diagnostic rule:
# Investigate rows where Profit > Sales because this may be economically suspicious.
# Sales and Profit are explicitly CAST from TEXT to DECIMAL before comparison.
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN CAST(TRIM(`Sales`) AS DECIMAL(18,4)) < CAST(TRIM(`Profit`) AS DECIMAL(18,4)) THEN 1 END) AS profit_greater_than_sales_issues FROM raw_superstore;


# --------------------------------------------------------------------------------------------------
# 6.c SALES + QUANTITY
#
# Since Sales and Quantity have already been validated as positive values,
# Sales / Quantity should also be positive.
#
# sales_per_unit is used as a sanity metric.
# Extreme values are investigated but are not automatically treated as errors.
# --------------------------------------------------------------------------------------------------

WITH sales_ratio_check AS (SELECT CAST(TRIM(`Sales`) AS DECIMAL(18,4)) / CAST(TRIM(`Quantity`) AS UNSIGNED) AS sales_per_unit FROM raw_superstore) SELECT MIN(sales_per_unit) AS min_sales_per_unit, MAX(sales_per_unit) AS max_sales_per_unit FROM sales_ratio_check;


# --------------------------------------------------------------------------------------------------
# 6.d ORDER-LEVEL SHIPPING / LOCATION CONSISTENCY
#
# Fields:
# Order ID + City + State + Postal Code
#
# Hypothesis:
# An Order should normally refer to one consistent shipping destination.
#
# This is treated as a diagnostic hypothesis rather than an automatic error rule,
# because split-destination Orders could theoretically exist.
#
# Given the previous completeness checks, a consistent Order has:
# 1 Postal Code + 1 City + 1 State = total distinct-location count of 3.
#
# Any total above 3 therefore indicates that at least one destination component varies
# inside the same Order.
# --------------------------------------------------------------------------------------------------

WITH order_destination_check AS (SELECT COUNT(DISTINCT `Postal Code`) AS unique_postal_per_order, COUNT(DISTINCT `City`) AS unique_cities_per_order, COUNT(DISTINCT `State`) AS unique_states_per_order, `Order ID` FROM raw_superstore GROUP BY `Order ID`) SELECT `Order ID` FROM order_destination_check WHERE unique_postal_per_order + unique_cities_per_order + unique_states_per_order > 3;


# ==================================================================================================
# END OF AUDIT
#
# Completed:
# ✓ Ingestion / source reconciliation
# ✓ Grain and cardinality
# ✓ Entity consistency / functional dependencies
# ✓ Technical and business-key investigation
# ✓ Duplicate-candidate investigation
# ✓ Individual field-validity controls
# ✓ Cross-field business-rule controls
#
# ==================================================================================================
# 7) CLEANING DECISIONS + TARGET GRAIN
#
# TARGET OUTPUT:
#   clean_superstore_sql
#
# TARGET GRAIN:
#   one row per Order ID + Product ID + Product Name
#
# WHY THIS GRAIN:
# - The raw source contains 9,994 transaction-line rows.
# - The audit found repeated Order ID + Product ID + Product Name combinations.
# - Downstream Python analysis is built on an order x product analytical base.
# - Aggregating repeated source lines to this grain produces the previously validated 9,986-row base.
#
# IMPORTANT DUPLICATE DECISION:
# - Repeated business-key rows are NOT deleted simply because they look duplicated.
# - The audit found both repeated lines with different measures and one exact-business duplicate candidate.
# - Without an external source-of-truth we do not delete economic records arbitrarily.
# - Instead, all repeated rows are consolidated to the target Order x Product grain and economic measures are summed.
# - This preserves the raw source Sales / Profit totals and keeps the downstream Python baseline reproducible.
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 7.1 FORMAL EXACT-BUSINESS-DUPLICATE CHECK
#
# This check fingerprints every business field except the technical Row ID.
# If multiple raw rows receive the same fingerprint, they are identical after TRIM on all business fields.
# The result is diagnostic only: it documents exact duplicate candidates but does not delete them automatically.
# --------------------------------------------------------------------------------------------------

WITH exact_business_fingerprint AS (
    SELECT CAST(TRIM(`Row ID`) AS UNSIGNED) AS row_id, SHA2(CONCAT_WS('||', COALESCE(TRIM(`Order ID`), '<NULL>'), COALESCE(TRIM(`Order Date`), '<NULL>'), COALESCE(TRIM(`Ship Date`), '<NULL>'), COALESCE(TRIM(`Ship Mode`), '<NULL>'), COALESCE(TRIM(`Customer ID`), '<NULL>'), COALESCE(TRIM(`Customer Name`), '<NULL>'), COALESCE(TRIM(`Segment`), '<NULL>'), COALESCE(TRIM(`Country`), '<NULL>'), COALESCE(TRIM(`City`), '<NULL>'), COALESCE(TRIM(`State`), '<NULL>'), COALESCE(TRIM(`Postal Code`), '<NULL>'), COALESCE(TRIM(`Region`), '<NULL>'), COALESCE(TRIM(`Product ID`), '<NULL>'), COALESCE(TRIM(`Category`), '<NULL>'), COALESCE(TRIM(`Sub-Category`), '<NULL>'), COALESCE(TRIM(`Product Name`), '<NULL>'), COALESCE(TRIM(`Sales`), '<NULL>'), COALESCE(TRIM(`Quantity`), '<NULL>'), COALESCE(TRIM(`Discount`), '<NULL>'), COALESCE(TRIM(`Profit`), '<NULL>')), 256) AS business_fingerprint FROM raw_superstore
)
SELECT business_fingerprint, COUNT(*) AS occurrences, GROUP_CONCAT(row_id ORDER BY row_id) AS source_row_ids FROM exact_business_fingerprint GROUP BY business_fingerprint HAVING COUNT(*) > 1;


# --------------------------------------------------------------------------------------------------
# 7.2 DISCOUNT CONSISTENCY INSIDE THE TARGET GRAIN
#
# Sales, Quantity and Profit are additive measures and will be SUMMED when repeated source lines are consolidated.
# Discount is a rate, so it must NOT be summed.
# Before using MAX(discount) in the clean table, verify that repeated Order x Product groups do not contain
# more than one distinct Discount value.
#
# EXPECTED RESULT: 0 rows.
# --------------------------------------------------------------------------------------------------

SELECT TRIM(`Order ID`) AS order_id, TRIM(`Product ID`) AS product_id, TRIM(`Product Name`) AS product_name, COUNT(DISTINCT CAST(TRIM(`Discount`) AS DECIMAL(10,4))) AS distinct_discount_values FROM raw_superstore GROUP BY TRIM(`Order ID`), TRIM(`Product ID`), TRIM(`Product Name`) HAVING COUNT(DISTINCT CAST(TRIM(`Discount`) AS DECIMAL(10,4))) > 1;


# ==================================================================================================
# 8) CREATE TYPED CLEAN DATASET
#
# The raw layer intentionally stored every field as TEXT so ingestion could not silently coerce or reject values.
# The audit has now validated formats, domains, ranges and cross-field rules, so the clean layer can assign
# explicit analytical datatypes.
#
# PYTHON COMPATIBILITY:
# - The output table name matches the downstream Python handoff: clean_superstore_sql.
# - Column names are converted to snake_case to match the existing Python analysis.
# - The output contains the same 21 logical fields expected by the Python loader.
# - row_id is retained for compatibility by taking the minimum source Row ID in each consolidated group.
#   It remains unique in the clean table, but should be interpreted as a representative source-line identifier.
# ==================================================================================================

DROP TABLE IF EXISTS clean_superstore_sql;

CREATE TABLE clean_superstore_sql (
    row_id INT UNSIGNED NOT NULL,
    order_id VARCHAR(14) NOT NULL,
    order_date DATE NOT NULL,
    ship_date DATE NOT NULL,
    ship_mode VARCHAR(30) NOT NULL,
    customer_id VARCHAR(8) NOT NULL,
    customer_name VARCHAR(120) NOT NULL,
    segment VARCHAR(30) NOT NULL,
    country VARCHAR(60) NOT NULL,
    city VARCHAR(120) NOT NULL,
    state VARCHAR(120) NOT NULL,
    postal_code CHAR(5) NOT NULL,
    region VARCHAR(20) NOT NULL,
    product_id VARCHAR(15) NOT NULL,
    category VARCHAR(50) NOT NULL,
    sub_category VARCHAR(50) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    sales DECIMAL(18,4) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    discount DECIMAL(10,4) NOT NULL,
    profit DECIMAL(18,4) NOT NULL,
    PRIMARY KEY (row_id),
    UNIQUE KEY uq_clean_order_product (order_id, product_id, product_name)
) DEFAULT CHARACTER SET utf8mb4;


# --------------------------------------------------------------------------------------------------
# 8.1 TRANSFORM RAW -> CLEAN
#
# GROUP BY defines the final analytical grain:
#   Order ID + Product ID + Product Name
#
# For fields already proven stable by the entity-consistency audit, MAX() is used only as a deterministic
# collapse of repeated identical values. It is NOT being used to hide conflicts: those conflicts were checked earlier.
#
# Additive measures:
#   Sales, Quantity, Profit -> SUM
#
# Non-additive rate:
#   Discount -> MAX after the pre-clean consistency check confirms one value per target-grain group.
#
# Postal Code:
#   LPAD(..., 5, '0') restores the leading zero lost upstream for four-character US ZIP codes.
#   The clean field remains CHAR(5), because Postal Code is an identifier rather than a numeric measure.
# --------------------------------------------------------------------------------------------------

INSERT INTO clean_superstore_sql (row_id, order_id, order_date, ship_date, ship_mode, customer_id, customer_name, segment, country, city, state, postal_code, region, product_id, category, sub_category, product_name, sales, quantity, discount, profit)
SELECT MIN(CAST(TRIM(`Row ID`) AS UNSIGNED)) AS row_id, TRIM(`Order ID`) AS order_id, MAX(STR_TO_DATE(TRIM(`Order Date`), '%m/%d/%Y')) AS order_date, MAX(STR_TO_DATE(TRIM(`Ship Date`), '%m/%d/%Y')) AS ship_date, MAX(TRIM(`Ship Mode`)) AS ship_mode, MAX(TRIM(`Customer ID`)) AS customer_id, MAX(TRIM(`Customer Name`)) AS customer_name, MAX(TRIM(`Segment`)) AS segment, MAX(TRIM(`Country`)) AS country, MAX(TRIM(`City`)) AS city, MAX(TRIM(`State`)) AS state, LPAD(MAX(TRIM(`Postal Code`)), 5, '0') AS postal_code, MAX(TRIM(`Region`)) AS region, TRIM(`Product ID`) AS product_id, MAX(TRIM(`Category`)) AS category, MAX(TRIM(`Sub-Category`)) AS sub_category, TRIM(`Product Name`) AS product_name, SUM(CAST(TRIM(`Sales`) AS DECIMAL(18,4))) AS sales, SUM(CAST(TRIM(`Quantity`) AS UNSIGNED)) AS quantity, MAX(CAST(TRIM(`Discount`) AS DECIMAL(10,4))) AS discount, SUM(CAST(TRIM(`Profit`) AS DECIMAL(18,4))) AS profit FROM raw_superstore GROUP BY TRIM(`Order ID`), TRIM(`Product ID`), TRIM(`Product Name`);


# ==================================================================================================
# 9) POST-CLEAN QC + RECONCILIATION
#
# Cleaning is not complete until the clean layer is reconciled back to the raw baseline.
# Every change in row count must be explained by the grain transformation, while entity counts and additive
# economic totals should remain consistent with the validated source baseline.
# ==================================================================================================


# --------------------------------------------------------------------------------------------------
# 9.1 CLEAN DATASET BASELINE
#
# Expected project baseline:
# - clean rows: 9,986
# - distinct orders: 5,009
# - distinct customers: 793
# - distinct Product IDs: 1,862
# - distinct Product ID + Product Name identities: 1,894
# - total Sales and Profit preserved from the 9,994-row raw source
# --------------------------------------------------------------------------------------------------

SELECT COUNT(*) AS clean_rows, COUNT(DISTINCT row_id) AS unique_clean_row_ids, COUNT(DISTINCT order_id) AS clean_orders, COUNT(DISTINCT customer_id) AS clean_customers, COUNT(DISTINCT product_id) AS clean_product_ids, COUNT(DISTINCT product_id, product_name) AS clean_product_id_name_pairs, SUM(sales) AS clean_total_sales, SUM(profit) AS clean_total_profit FROM clean_superstore_sql;


# --------------------------------------------------------------------------------------------------
# 9.2 TARGET-GRAIN UNIQUENESS
#
# The clean table must contain exactly one row per Order ID + Product ID + Product Name.
# EXPECTED RESULT: 0 rows.
# --------------------------------------------------------------------------------------------------

SELECT order_id, product_id, product_name, COUNT(*) AS occurrences FROM clean_superstore_sql GROUP BY order_id, product_id, product_name HAVING COUNT(*) > 1;


# --------------------------------------------------------------------------------------------------
# 9.3 RAW VS CLEAN RECONCILIATION
#
# Row count is expected to fall from 9,994 to 9,986 because repeated raw lines are consolidated to the
# target Order x Product grain. Distinct Orders / Customers / Products and additive Sales / Profit totals
# should remain unchanged.
# --------------------------------------------------------------------------------------------------

WITH raw_qc AS (SELECT COUNT(*) AS rows_count, COUNT(DISTINCT TRIM(`Order ID`)) AS orders_count, COUNT(DISTINCT TRIM(`Customer ID`)) AS customers_count, COUNT(DISTINCT TRIM(`Product ID`)) AS product_ids_count, COUNT(DISTINCT TRIM(`Product ID`), TRIM(`Product Name`)) AS product_id_name_pairs, SUM(CAST(TRIM(`Sales`) AS DECIMAL(18,4))) AS total_sales, SUM(CAST(TRIM(`Profit`) AS DECIMAL(18,4))) AS total_profit FROM raw_superstore), clean_qc AS (SELECT COUNT(*) AS rows_count, COUNT(DISTINCT order_id) AS orders_count, COUNT(DISTINCT customer_id) AS customers_count, COUNT(DISTINCT product_id) AS product_ids_count, COUNT(DISTINCT product_id, product_name) AS product_id_name_pairs, SUM(sales) AS total_sales, SUM(profit) AS total_profit FROM clean_superstore_sql) SELECT raw_qc.rows_count AS raw_rows, clean_qc.rows_count AS clean_rows, raw_qc.rows_count - clean_qc.rows_count AS rows_consolidated, raw_qc.orders_count AS raw_orders, clean_qc.orders_count AS clean_orders, raw_qc.customers_count AS raw_customers, clean_qc.customers_count AS clean_customers, raw_qc.product_ids_count AS raw_product_ids, clean_qc.product_ids_count AS clean_product_ids, raw_qc.product_id_name_pairs AS raw_product_id_name_pairs, clean_qc.product_id_name_pairs AS clean_product_id_name_pairs, raw_qc.total_sales AS raw_total_sales, clean_qc.total_sales AS clean_total_sales, raw_qc.total_sales - clean_qc.total_sales AS sales_difference, raw_qc.total_profit AS raw_total_profit, clean_qc.total_profit AS clean_total_profit, raw_qc.total_profit - clean_qc.total_profit AS profit_difference FROM raw_qc CROSS JOIN clean_qc;


# --------------------------------------------------------------------------------------------------
# 9.4 POSTAL-CODE CLEANING QC
#
# After LPAD correction, all non-null Postal Codes should be five characters long.
# EXPECTED RESULT: min length = 5, max length = 5.
# --------------------------------------------------------------------------------------------------

SELECT MIN(CHAR_LENGTH(postal_code)) AS min_postal_code_length, MAX(CHAR_LENGTH(postal_code)) AS max_postal_code_length FROM clean_superstore_sql;


# --------------------------------------------------------------------------------------------------
# 9.5 FINAL DATE / SHIPPING RULE RECHECK
#
# EXPECTED RESULT: 0 violations.
# --------------------------------------------------------------------------------------------------

SELECT COUNT(CASE WHEN ship_date < order_date THEN 1 END) AS clean_ship_before_order_issues, MIN(DATEDIFF(ship_date, order_date)) AS min_shipping_delay, MAX(DATEDIFF(ship_date, order_date)) AS max_shipping_delay FROM clean_superstore_sql;


# --------------------------------------------------------------------------------------------------
# 9.6 FINAL PYTHON / NOTEBOOK FEED
#
# Objective:
# Produce a portable CSV that can be used by the Python script AND by the notebook without requiring
# a live MySQL connection.
#
# Why an export-safe copy is created:
# MySQL Workbench's Result Grid CSV export can fail when a text value contains a literal double quote (").
# Example source value:
#   Wilson Jones Hanging View Binder, White, 1"
#
# A standards-compliant CSV represents a literal quote inside a quoted field as two quotes ("").
# We therefore create a TEMPORARY export copy and double literal quote characters only in that copy.
# The analytical clean table clean_superstore_sql is NOT modified.
#
# When Workbench wraps the export value in outer CSV quotes, the doubled quote is interpreted correctly
# by pandas and is read back as the original single literal quote. No business value is changed in Python.
#
# IMPORTANT:
# - Export the final Result Grid using Workbench's normal/default CSV format (comma-separated).
# - Save it as: clean_superstore_csv_export.csv
# - The uploaded Workbench export is UTF-8, so Python should read it with encoding='utf-8'.
# - Do NOT use sep=';' for this export; comma is the actual delimiter.
#
# Python / notebook loader:
#   df = pd.read_csv(SQL_CLEAN_CSV_PATH, encoding='utf-8')
#
# The .pkl creation later in the Python pipeline remains unchanged.
# --------------------------------------------------------------------------------------------------

DROP TEMPORARY TABLE IF EXISTS clean_superstore_csv_export;

CREATE TEMPORARY TABLE clean_superstore_csv_export AS SELECT * FROM clean_superstore_sql;

# Escape literal double quotes for standards-compliant CSV serialization without changing the clean table.
UPDATE clean_superstore_csv_export SET product_name = REPLACE(product_name, '"', '""');

# Export THIS final Result Grid from MySQL Workbench as clean_superstore_csv_export.csv.
SELECT * FROM clean_superstore_csv_export ORDER BY row_id;


# ==================================================================================================
# END OF COMPLETE SQL PIPELINE
#
# FINAL FLOW:
# raw CSV -> raw_superstore -> audit -> cleaning decisions -> clean_superstore_sql -> QC -> export-safe CSV -> Python / notebook
#
# Expected clean analytical base:
#   9,986 rows at Order ID + Product ID + Product Name grain.
# ==================================================================================================
