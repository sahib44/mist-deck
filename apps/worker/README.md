The worker entry point is `python -m mist.worker`. Its implementation lives in
`apps/api/mist/worker.py` so API and worker use the same Python package, models,
validation, and mock provider. Compose runs it as a separate service.
