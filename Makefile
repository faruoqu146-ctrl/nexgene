.PHONY: test run docker-up clean

test:
	TESTING=1 DATABASE_URL=sqlite:////tmp/nexgene.db CLINICAL_DATABASE_URL=sqlite:////tmp/nexgene_clinical.db CLINICAL_PROVIDER_KEY=test-provider-key python -m pytest backend/tests/ -v --tb=short

run:
	TESTING=0 uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

docker-up:
	docker compose up --build

clean:
	rm -f *.db /tmp/nexgene*.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
