.PHONY: deploy-dev deploy-pre deploy-prod status logs open

deploy-dev:
	vercel deploy

deploy-pre:
	vercel deploy

deploy-prod:
	vercel deploy --prod

status:
	vercel ls

logs:
	vercel logs $(URL)

open:
	vercel open
