# PRICEBOOK.ALLCOUNTY.BUILD.1 — candidate configuration packet

## Safety and authority

- Starting protected authority: `428dcbddd7d072b5b8d9edff489efcd4373960b5`.
- Candidate configuration: `all-county-price-book-candidate-1`.
- Activation state: **NOT ACTIVATED**.
- Preview and Production are outside this program's mutation boundary.
- Original evidence remains in the owner-controlled source directory and is not
  copied into repository or frontend bundles.

The canonical machine packet is
`all-county-build-1.configuration.json`. It records every derived row, source
worksheet and row identity, source digest, labor classification, aggregate
material-cost evidence, candidate prices, review state, and activation state.
The deterministic builder is `scripts/pricebook_allcounty_build.py`.

## Source accounting

| Source identity | SHA-256 | Classification | Disposition |
|---|---|---|---|
| `All_County_Flat_Rate_Price_Book.xlsx` | `8dd5afbfba930cc88d32cc6ff7fd3e25525215593b2003c1471f8e6e0759cb45` | OWNER_PRICING_SOURCE | Candidate service/labor/aggregate material/price evidence; never auto-activate |
| `All_County_Parts_Markup_Schedule.xlsx` | `b4a838b4c490f5da6526549544acf76c3db9c5dbea9900e4a8df4a3a48327d71` | OWNER_RECOMMENDATION | Versioned candidate policy; review required |
| `All_County_Membership_Brochure.pdf` | `191245abf31e4fc9981008b438c3900af3dfe3d1d8de49cbbef11f7006508e63` | OWNER_CUSTOMER_FACING_SOURCE | Customer-facing membership evidence; reconcile in Service Agreements |
| `All_County_Pinellas_Pricing_Recommendation.docx` | `6c919b518828c47e5930745b1d66772c8a37e1ec37abb4ae65a1570a69fcfa19` | OWNER_RECOMMENDATION | Illustrative economics and recommendations; not policy |
| `All_County_Sales_Script.docx` | `ffd08762bad5b9307231b94e40c9246afd5beb199f599c4424e95a3e3f7a5baf` | OWNER_RECOMMENDATION | Presentation/workflow evidence; not legal or pricing authority |
| `pricebook_materials_template.numbers` | `487afcbbce7584471c691507616c2f87464ee2959105b1b03bfe41eee03e92a9` | OWNER_OPERATIONAL_SOURCE | 361 provider-neutral material candidates; vendor identity remains source-required |
| `All_County_Water_Heater_Sales_Script.docx` | `c9e815becc8011764e1c8f8752d218358c53d89d62c0fe70f7cc5e5bd4abf317` | OWNER_RECOMMENDATION | Scope/options reconciliation evidence; example economics do not override workbook prices |

Additional documents in the owner directory were inspected only for source
relationships. They are not promoted into the seven-source authority set.

## Flat-rate workbook controls

The workbook contains 22 worksheets, 16 operating category sheets, 218 service
rows, named references for the item table, code list, markup schedule, minimum
job, selling rate, member discounts and after-hours multiplier, plus formula
links from category sheets through Quick Reference, All Items and Quote Builder.

- Categories: Service Calls 10; Drain Cabling 13; Hydro-Jet & Camera 11; Sewer
  Repair 15; Water Heater Install 16; Tankless 7; Water Heater Repair 16;
  Toilets 20; Faucets & Showers 27; Disposals 11; Water Service 18; Leak
  Detection 13; Outdoor & Backflow 11; Sump & Ejector 10; Repipe 10; Gas 10.
- Candidate services: 218; duplicate codes: 0.
- Formula-derived prices: 208; explicit workbook overrides: 10.
- Configured-estimate labor: 218 rows; zero-hour rows: 10. These are never
  represented as measured Job duration or Employee pay.
- Aggregate parts-cost evidence: 194 rows; no component cost: 24 rows.
- Every tax classification is `OWNER_ACCOUNTANT_REVIEW_REQUIRED`.
- Every candidate is `READY_FOR_OWNER_REVIEW` and `NOT_ACTIVATED`.
- Water Heater/Tankless candidate family: 39 services. The dedicated script is
  scope-consistent with standard, premium and tankless options already present.
  Its generic price examples conflict with size/fuel-specific workbook amounts,
  and its line-item economics are illustrative assumptions; neither overrides
  a workbook candidate.

Workbook price display is not taken on faith. The builder follows the workbook's
named settings and category formulas, distinguishes overrides, applies its
12-tier cost lookup, rounds to the workbook's five-dollar increment, and retains
the exact source sheet/row for replay.

## Parts-markup evidence

The markup workbook has a 12-tier cost schedule, calculator, common-parts
examples, customer-supplied-parts proposals and comparison examples. Its common
part costs explicitly describe themselves as illustrative and are therefore not
vendor cost authority. The tier table, customer-supplied labor adjustments,
special-order surcharge and freight language are preserved as
`OWNER_REVIEW_REQUIRED`; no material-cost change can change a customer price.

## Vendor-material import

The Numbers source contains one sheet, one table, 362 physical rows including
the header, and 19 columns. Its contract supports category plus ten subcategory
levels; the supplied dataset populates four hierarchy levels:
`Plumbing / Parts / Residential / Parts`. All 361 data rows have a source part
number, description, cost, taxable flag, `Each` unit and markup-enabled flag.
No row supplies a customer price, vendor name, manufacturer, manufacturer part
number, pack quantity or effective date.

Provider-neutral reconciliation produced 361 candidates and 360 unique source
identities. Source part number `828627` is duplicated exactly at rows 43 and 64;
both copies are `DUPLICATE_CANDIDATE` and cannot overwrite one another. The 359
remaining rows are `SOURCE_REQUIRED` until the vendor identity is supplied.
Hierarchy and source row provenance are retained independently of ACP's
user-facing category depth. No candidate creates a Price Book service or moves
Inventory.

## Water Heater reconciliation

The native 39-service family comprises six standard tank-install choices, four
premium tank-install choices, seven Tankless choices, sixteen repair/add-on
choices, and six other install choices. The script's Standard/Premium/Tankless
presentation is `CONSISTENT` with native option-group composition. Its generic
Standard, Premium and Tankless figures are `CONFLICTING` with the workbook's
fuel/capacity-specific candidate values and remain `RECOMMENDATION`. The
line-item cost breakdown is `ILLUSTRATIVE_ASSUMPTION`; warranty, permit and code
claims are `OWNER_RECOMMENDATION` pending applicable policy/legal authority.

## Product and domain boundaries

The native Price Book already owns categories, service items, immutable price
versions, labor/material components, option groups, activation/supersession,
commercial snapshots, audit history and Company/Branch authorization. The
Product Home now adds responsive search, lifecycle filtering, readiness totals,
missing-price visibility and owner-review visibility without exposing UUID
mechanics.

- Estimate composition continues to consume immutable commercial snapshots;
  later Price Book changes cannot rewrite accepted Estimate evidence.
- Service Agreements owns tier, entitlement, benefits, billing and renewal.
  Price Book may consume an approved discount entitlement but does not create a
  parallel membership engine.
- Vendor catalog, Inventory, Purchasing cost, estimated service material and
  actual Job consumption remain distinct authorities. Aggregate workbook parts
  dollars are not transformed into inventory movements.
- Workbook Good/Better/Best and add-on language is presentation evidence.
  Native option groups support source-justified choices; no service is forced
  into three options and scripts are not encoded as rules.
- Planned labor/material contribution is not profit and is not actual Job
  economics. No overhead or accounting cost is invented.
- HCP remains reference-only and cannot overwrite native Price Book authority.
- Beacon/Luminary/LIA may explain deterministic review evidence but cannot set,
  change or activate prices.

## Review and activation readiness

The machine packet supports group review by source, category, pricing state,
material mapping and tax-review state. Current group classification is:

- `READY_FOR_OWNER_REVIEW`: 218
- `READY_FOR_ACTIVATION`: 0
- `OWNER_ACCOUNTANT_REVIEW_REQUIRED`: 218
- `MATERIAL_MAPPING_REQUIRED`: 194
- `SOURCE_REQUIRED`: 359 vendor-material candidates missing vendor identity
- `DUPLICATE_CANDIDATE`: 2 rows sharing one source part number

No row disappears: all 218 workbook service rows have a candidate disposition
and provenance identity. Activation requires a later explicit owner-authorized
operation after tax, membership, materials and source conflicts are resolved.
