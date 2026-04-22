VERCEL = vercel --cwd frontend --yes

.PHONY: deploy-dev deploy-pre deploy-prod status logs open

deploy-dev:
	$(VERCEL) pull --environment=preview
	$(VERCEL) deploy

deploy-pre:
	$(VERCEL) pull --environment=preview
	$(VERCEL) deploy

deploy-prod:
	$(VERCEL) pull --environment=production
	$(VERCEL) deploy --prod

status:
	cd frontend && vercel ls

logs:
	cd frontend && vercel logs $(URL)

open:
	cd frontend && vercel open
