# Architecture boundary

The nutrition calculator is organized as a modular core so it can later be
embedded in the management system or deployed as an independent HTTP service.

## Dependency direction

```text
Web API/UI/batch job
        |
        v
NutritionCalculationService (versioned contract)
        |
        v
Domain models + calculation rules
        ^
        |
Nutrient repository interface/data adapter

Excel SOP parser ---> domain Recipe
CSV/database     ---> NutrientRepository
Domain result    ---> JSON/CSV/database publisher
             \---> storefront-template export adapter
```

The domain calculator must not import Flask, an ORM, a database driver, or an
Excel library. Infrastructure code converts external data into domain objects.

## Public integration contract

External callers should depend on `NutritionCalculationService.calculate`, not
on Excel cell coordinates or internal calculation functions. Requests and
responses carry `contract_version: nutrition.calculation.v3` and the response
includes `calculation_rule_version`. Version 3 exposes provisional results when
reported nutrients are missing: those fields are temporarily summed as zero,
remain marked in `missing_nutrients`, and force `review` status. Unmatched
ingredients and parsing gaps remain `incomplete`. Per-piece weight estimates
are only applied when a configured food has an explicit count. See
`calculation_rules.md` for the current policy and data file.

Calculated results and reviewed/published results should be stored separately.
Every persisted calculation should also record the SOP version, nutrient-data
version, rule version, timestamp, and reviewer/publisher identity.

The storefront workbook is a presentation adapter, not a calculation source.
It starts from the supplied 15-column template, clears example rows, and fills
only column A (product name, e.g. A(1)菜名) and column E (eight-nutrient
detail). Primary and secondary recipes are written to separate 小学标准 and
中学标准 sheets; all other columns stay blank. Incomplete recipes stay visible
in the review UI and are excluded from the upload workbook.

## Deployment boundary

`wsgi:app` is the production entrypoint. Gunicorn listens on `0.0.0.0:8300`
when ECS security-group access to port `8300` is required. Restrict the
security-group source range to trusted office IPs, or put HTTPS reverse proxy
in front of the service for public access. The core package remains independent
from Flask and deployment concerns.
