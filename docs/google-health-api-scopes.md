# Google Health API — available scopes

Reference list of all `googlehealth.*` scopes offered on the OAuth consent
screen's Data Access page (22 total, readonly + writeonly pairs per data
category). Captured 2026-08-04 while setting up the `strides` GCP project.

## Enabled for this project

| Scope | Description |
|---|---|
| `.../auth/googlehealth.activity_and_fitness.readonly` | See your Google Health activity and fitness data |

This is the **only** scope the backend requests — see `HEALTH_SCOPE` in
`backend/services/auth_service.py`. Anything else enabled on the consent
screen but never requested in code is unused surface area.

## Full list (not enabled, for reference)

| Scope | Description |
|---|---|
| `.../auth/googlehealth.health_metrics_and_measurements.readonly` | See your Google Health health metrics and measurement data |
| `.../auth/googlehealth.location.readonly` | See exercise GPS location data in Google Health |
| `.../auth/googlehealth.nutrition.readonly` | See your Google Health nutrition data |
| `.../auth/googlehealth.sleep.readonly` | See your Google Health sleep data |
| `.../auth/googlehealth.reproductive_health.readonly` | See your Google Health reproductive health data |
| `.../auth/googlehealth.logged_symptoms.readonly` | See your Google Health logged symptoms data |
| `.../auth/googlehealth.mindfulness.readonly` | See your Google Health mindfulness data |
| `.../auth/googlehealth.activity_and_fitness.writeonly` | Add activity and fitness data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.health_metrics_and_measurements.writeonly` | Add health metric and measurements data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.location.writeonly` | Add exercise GPS location data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.nutrition.writeonly` | Add nutrition data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.sleep.writeonly` | Add sleep data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.reproductive_health.writeonly` | Add reproductive health data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.logged_symptoms.writeonly` | Add logged symptoms data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.mindfulness.writeonly` | Add mindfulness data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.profile.readonly` | See your Google Health profile data |
| `.../auth/googlehealth.profile.writeonly` | Add profile data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.settings.readonly` | See your Google Health settings |
| `.../auth/googlehealth.settings.writeonly` | Add settings data to Google Health, and edit or delete the data it adds |
| `.../auth/googlehealth.irn.readonly` | See your Google Health Irregular Rhythm Notifications data |
| `.../auth/googlehealth.ecg.readonly` | See your Google Health ECG data |

## Identity scopes (separate flow, not from this API)

`openid`, `email`, `profile` — requested by the app-login flow
(`IDENTITY_SCOPE` in `auth_service.py`), unrelated to Google Health API
enablement.
