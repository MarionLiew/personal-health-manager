# Radiation dose

Device records and estimates are separate. Missing DLP produces an uncertainty, never a precise mSv.
SSDE requires patient-size data. Effective-dose calculation must persist coefficient, region, age
group, source/version and uncertainty. CTDIvol values are not accumulated across examinations; MRI
and ultrasound are recorded as non-ionizing and excluded.

Alerts prompt review of repeats, overlapping ranges, multiphase acquisition, missing dose records,
total-versus-series DLP, PET/SPECT radiopharmaceutical separation, and machine-versus-estimate
confusion. Alerts do not block medically necessary care.

Version 0.2 exposes list/show/acquisition, period/lifetime summary, by-region, missing-data,
possible-duplicate and doctor-summary commands. It reports source quality and completeness. No mSv
is produced unless a future version supplies a versioned region/age conversion method and uncertainty.
