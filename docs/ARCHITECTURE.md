# Architecture boundary

The nutrition calculator is organized as a modular core so it can later be
embedded in the management system or deployed as an independent HTTP service.

## Dependency direction

```text
Flask/API/UI/batch job
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
```

The domain calculator must not import Flask, an ORM, a database driver, or an
Excel library. Infrastructure code converts external data into domain objects.

## Public integration contract

External callers should depend on `NutritionCalculationService.calculate`, not
on Excel cell coordinates or internal calculation functions. Requests and
responses carry `contract_version: nutrition.calculation.v1`. A future breaking
change gets a new contract version while v1 can remain available during system
migration.

Calculated results and reviewed/published results should be stored separately.
Every persisted calculation should also record the SOP version, nutrient-data
version, rule version, timestamp, and reviewer/publisher identity.
